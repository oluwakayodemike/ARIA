import json
import os
import re
import textwrap
import time

from google import genai
from google.genai import types
from pydantic import BaseModel, Field, field_validator

from config import (
    SPLUNK_AI_PRIMARY,
    SPLUNK_MCP_TOOL_EXPLAIN,
    SPLUNK_MCP_TOOL_GENERATE,
    SPLUNK_MCP_TOOL_OPTIMIZE,
)
from core.splunk_client import SplunkClient
from core.splunk_mcp_client import SplunkMCPClient
from core.state import ARIAState, TechniqueState


# strict schema for AI response validation and parsing
class SPLRule(BaseModel):
    rule: str = Field(
        description="The actual Splunk search string (e.g., `index=* sourcetype=WinEventLog:Security`)"
    )
    explanation: str = Field(
        description="A 1-2 sentence explanation of how this SPL works"
    )
    confidence: float = Field(
        description="A float between 0.0 and 1.0 representing confidence"
    )

    @field_validator("confidence")
    @classmethod
    def clamp_confidence(cls, v: float) -> float:
        return round(max(0.0, min(1.0, v)), 2)


class GapAgent:
    """
    SPL Detection Engineer Agent.
    Takes attack profiles from the Red Agent, generates SPL detection rules,
    validates them against Splunk, and stages validated rules for human approval.

    Primary brain: Splunk AI Assistant via Splunk MCP Server.
    Fallback brain: Gemini (only when MCP path is unavailable/fails).
    """

    MAX_RETRIES = 2  # fix attempts after the initial generation
    REQUEST_DELAY = 0.5

    def __init__(
        self,
        splunk_client: SplunkClient,
        model_name: str = "gemini-3.5-flash",
        mcp_client: SplunkMCPClient | None = None,
        ai_primary: bool = SPLUNK_AI_PRIMARY,
    ):
        self.splunk = splunk_client
        self.model_name = model_name
        self.ai_primary = ai_primary
        self.mcp = mcp_client or SplunkMCPClient()

        api_key = os.getenv("GEMINI_API_KEY")
        self.ai = genai.Client(api_key=api_key) if api_key else None

        if self.ai is None and not self.mcp.is_configured():
            raise ValueError(
                "GEMINI_API_KEY env is not set and Splunk MCP is not configured."
            )

    def run(self, state: ARIAState, limit: int = 5) -> ARIAState:
        state.set_phase("generating")

        candidates = [
            t for t in state.get_gaps() if t.attack_profile and not t.generated_rule
        ]

        if not candidates:
            state.log(
                "GapAgent",
                "No profiled gaps available for rule generation.",
                level="info",
            )
            return state

        # slice the candidate list to respect the limit
        candidates_to_process = candidates[:limit]

        state.log(
            "GapAgent",
            f"Starting rule generation - {len(candidates_to_process)} techniques queued.",
        )

        succeeded = 0
        failed = 0

        for technique in candidates_to_process:
            try:
                self._process_technique(technique, state)
                succeeded += 1
            except Exception as e:
                failed += 1
                state.log(
                    "GapAgent",
                    f"Unrecoverable failure for {technique.technique_id}: {e}",
                    level="error",
                )

                # auth/session failures should fail-fast to avoid wasting
                # additional model calls on remaining techniques.
                if self._is_auth_error_message(str(e)):
                    state.log(
                        "GapAgent",
                        "Aborting remaining techniques due to Splunk authentication/session failure.",
                        level="error",
                    )
                    break
            finally:
                time.sleep(self.REQUEST_DELAY)

        state.log(
            "GapAgent",
            f"Rule generation complete - {succeeded} succeeded, {failed} failed.",
        )
        return state

    def _process_technique(self, technique: TechniqueState, state: ARIAState):
        """full lifecycle: generate → validate → retry with error context → stage."""
        started_at = time.perf_counter()

        state.log(
            "GapAgent",
            f"Generating rule for {technique.technique_id} - {technique.technique_name}",
        )

        profile = technique.attack_profile
        if not profile:
            raise ValueError("Technique is missing attack profile context.")

        previous_error = None

        for attempt in range(1, self.MAX_RETRIES + 2):
            payload = self._generate_rule_payload(profile, previous_error, state)

            rule_spl = payload["rule"].strip()
            explanation = payload["explanation"].strip()
            confidence = payload["confidence"]
            provider = payload["provider"]

            if not rule_spl:
                raise ValueError("AI returned an empty SPL rule.")

            regex_error = self._check_regex_sanity(rule_spl)
            if regex_error:
                previous_error = regex_error
                state.log(
                    "GapAgent",
                    f"SPL invalid for {technique.technique_id} "
                    f"(attempt {attempt}): {previous_error}",
                    level="warning",
                )
                continue

            validation = self.splunk.validate_spl(rule_spl)

            if validation["valid"]:
                with state.locked():
                    technique.generated_rule = validation["normalized"]
                    technique.rule_explanation = explanation
                    technique.rule_confidence = confidence
                    technique.rule_provider = provider
                    technique.rule_provider_trace = payload.get("provider_trace", [])
                    technique.pending_approval = True
                elapsed_sec = round(time.perf_counter() - started_at, 2)
                with state.locked():
                    state.generation_durations_sec.append(elapsed_sec)

                state.log(
                    "GapAgent",
                    f"rule validated for {technique.technique_id} "
                    f"(attempt {attempt}, provider {provider}, confidence {confidence if confidence is not None else 'n/a'}, {elapsed_sec}s)",
                )
                return

            previous_error = validation["error"]

            if self._is_auth_error_message(previous_error):
                state.log(
                    "GapAgent",
                    f"Splunk session expired while validating {technique.technique_id}; reconnecting...",
                    level="warning",
                )

                if not self.splunk.connect():
                    raise RuntimeError(
                        "Splunk session expired and reconnect failed. "
                        "Check Splunk credentials/session health."
                    )

                retry_validation = self.splunk.validate_spl(rule_spl)
                if retry_validation["valid"]:
                    with state.locked():
                        technique.generated_rule = retry_validation["normalized"]
                        technique.rule_explanation = explanation
                        technique.rule_confidence = confidence
                        technique.rule_provider = provider
                        technique.rule_provider_trace = payload.get(
                            "provider_trace", []
                        )
                        technique.pending_approval = True
                    elapsed_sec = round(time.perf_counter() - started_at, 2)
                    with state.locked():
                        state.generation_durations_sec.append(elapsed_sec)

                    state.log(
                        "GapAgent",
                        f"rule validated for {technique.technique_id} "
                        f"after session reconnect (attempt {attempt}, provider {provider}, confidence {confidence if confidence is not None else 'n/a'}, {elapsed_sec}s)",
                    )
                    return

                previous_error = retry_validation.get("error") or previous_error

            state.log(
                "GapAgent",
                f"SPL invalid for {technique.technique_id} "
                f"(attempt {attempt}): {previous_error}",
                level="warning",
            )

        raise ValueError(
            f"SPL still invalid after {self.MAX_RETRIES + 1} attempts. "
            f"Last error: {previous_error}"
        )

    def _generate_rule_payload(
        self, profile: dict, previous_error: str | None, state: ARIAState
    ) -> dict:
        """
        Generate a candidate SPL payload using MCP-first strategy.
        Falls back to Gemini only when MCP is unavailable/fails.
        """
        if self.ai_primary:
            try:
                mcp_payload = self._call_mcp_ai(profile, previous_error)
                state.log(
                    "GapAgent",
                    f"SPL candidate generated via Splunk MCP ({', '.join(mcp_payload['provider_trace'])})",
                )
                return mcp_payload
            except Exception as mcp_error:
                if self.ai is None:
                    raise RuntimeError(
                        "Splunk MCP generation failed and Gemini fallback is unavailable. "
                        f"MCP error: {mcp_error}"
                    ) from mcp_error

                state.log(
                    "GapAgent",
                    f"Splunk MCP generation unavailable, falling back to Gemini: {mcp_error}",
                    level="warning",
                )

        if self.ai is None:
            raise RuntimeError(
                "Gemini fallback is unavailable because GEMINI_API_KEY is not set."
            )

        payload: SPLRule = self._call_ai(profile, previous_error)
        return {
            "rule": payload.rule,
            "explanation": payload.explanation,
            "confidence": payload.confidence,
            "provider": "gemini",
            "provider_trace": ["gemini_generate_content"],
        }

    def _call_mcp_ai(self, profile: dict, previous_error: str | None) -> dict:
        if not self.mcp.is_configured():
            raise RuntimeError("Splunk MCP is not configured (URL/token missing).")

        generate_tool = self.mcp.find_tool(
            SPLUNK_MCP_TOOL_GENERATE,
            "saia_generate_spl",
            "generate_spl",
        )
        optimize_tool = self.mcp.find_tool(
            SPLUNK_MCP_TOOL_OPTIMIZE,
            "saia_optimize_spl",
            "optimize_spl",
        )
        explain_tool = self.mcp.find_tool(
            SPLUNK_MCP_TOOL_EXPLAIN,
            "saia_explain_spl",
            "explain_spl",
        )

        if not generate_tool:
            raise RuntimeError(
                "Could not find SPL generation tool in MCP (expected saia_generate_spl)."
            )

        request_text = self._build_mcp_generation_request(profile, previous_error)
        generated = self._invoke_text_tool(generate_tool, request_text)
        generated_text = self.mcp.extract_text(generated)
        generated_spl = self._extract_spl_from_text(generated_text)

        provider_trace = [generate_tool]

        optimized_spl = generated_spl
        if optimize_tool:
            try:
                optimized = self._invoke_spl_tool(
                    optimize_tool,
                    generated_spl,
                    instruction=(
                        "Optimize this SPL for accuracy and performance while preserving "
                        "detection intent for the described ATT&CK technique."
                    ),
                )
                optimized_text = self.mcp.extract_text(optimized)
                optimized_spl = self._extract_spl_from_text(optimized_text)
                provider_trace.append(optimize_tool)
            except Exception:
                # Keep generated SPL if optimize step fails.
                optimized_spl = generated_spl

        explanation = "Generated by Splunk AI Assistant via MCP."
        if explain_tool:
            try:
                explained = self._invoke_spl_tool(explain_tool, optimized_spl)
                explanation_text = self.mcp.extract_text(explained).strip()
                if explanation_text:
                    explanation = explanation_text
                    provider_trace.append(explain_tool)
            except Exception:
                pass

        return {
            "rule": optimized_spl,
            "explanation": explanation,
            "confidence": None,
            "provider": "splunk_ai_assistant_mcp",
            "provider_trace": provider_trace,
        }

    def _invoke_text_tool(self, tool_name: str, text: str) -> dict:
        # Prefer prompt-shaped args for Splunk AI Assistant tools.
        candidate_args = [
            {"prompt": text, "configs": {}},
            {"prompt": text},
            {"query": text},
            {"question": text},
            {"input": text},
            {"request": text},
            {"text": text},
        ]

        errors: list[str] = []
        for args in candidate_args:
            try:
                return self.mcp.call_tool(tool_name, args)
            except Exception as e:
                errors.append(f"args={list(args.keys())}: {e}")

        joined = " | ".join(errors)
        raise RuntimeError(
            f"MCP tool '{tool_name}' rejected all text argument variants: {joined}"
        )

    def _invoke_spl_tool(
        self, tool_name: str, spl: str, instruction: str | None = None
    ) -> dict:
        prompt_body = spl
        if instruction:
            prompt_body = f"{instruction}\n\nSPL:\n{spl}"

        base_args = [
            {"prompt": prompt_body, "configs": {}},
            {"prompt": prompt_body},
            {"spl": spl},
            {"query": spl},
            {"search": spl},
            {"spl_query": spl},
        ]

        candidate_args = []
        for args in base_args:
            candidate_args.append(args)
            if instruction and "prompt" not in args:
                candidate_args.append({**args, "instruction": instruction})
                candidate_args.append({**args, "context": instruction})

        errors: list[str] = []
        for args in candidate_args:
            try:
                return self.mcp.call_tool(tool_name, args)
            except Exception as e:
                errors.append(f"args={list(args.keys())}: {e}")

        joined = " | ".join(errors)
        raise RuntimeError(
            f"MCP tool '{tool_name}' rejected all SPL argument variants: {joined}"
        )

    def _build_mcp_generation_request(
        self, profile: dict, previous_error: str | None
    ) -> str:
        base = textwrap.dedent(
            f"""
            Generate a production-quality Splunk SPL detection for this ATT&CK technique.

            Technique ID: {profile.get("technique_id")}
            Technique Name: {profile.get("technique_name")}
            Tactics: {", ".join(profile.get("tactics", []))}
            Severity: {profile.get("severity", "medium")}
            Keywords: {", ".join(profile.get("keywords", []))}
            Suggested data sources: {", ".join(profile.get("log_hints", []))}
            Description: {profile.get("description", "")}
            Detection guidance: {profile.get("detection_hint", "")}

            Requirements:
            - Return valid SPL only.
            - Start with a generating command (search, tstats, or inputlookup).
            - No backtick macros.
            - Include meaningful filters; avoid broad wildcard-only searches.
            - Avoid regex unless necessary.
            """
        ).strip()

        if not previous_error:
            return base

        correction = textwrap.dedent(
            f"""

            Previous attempt failed Splunk validation with:
            {previous_error}

            Rewrite to resolve this exact validation issue.
            """
        ).strip()
        return f"{base}\n\n{correction}"

    def _extract_spl_from_text(self, text: str) -> str:
        if not text or not text.strip():
            raise ValueError("AI returned empty content")

        candidate = text.strip()

        # If the response is JSON, prefer common SPL keys and reject error payloads.
        try:
            parsed = json.loads(candidate)
            if isinstance(parsed, dict):
                err = parsed.get("error")
                if isinstance(err, str) and err.strip():
                    raise ValueError(f"AI tool returned error payload: {err.strip()}")

                for key in ("spl", "query", "search", "optimized_spl", "rule"):
                    value = parsed.get(key)
                    if isinstance(value, str) and value.strip():
                        return value.strip()
        except ValueError:
            raise
        except Exception:
            pass

        # Extract from fenced code block if present.
        fenced = re.findall(r"```(?:spl)?\s*(.*?)```", candidate, flags=re.S | re.I)
        if fenced:
            block = fenced[0].strip()
            if block:
                return block

        lower = candidate.lower()
        if "local variable" in lower and "referenced before assignment" in lower:
            raise ValueError(f"AI tool returned runtime error text: {candidate}")
        if lower.startswith('{"error"') or lower.startswith("{'error'"):
            raise ValueError(f"AI tool returned error payload: {candidate}")

        return candidate

    def _call_ai(self, profile: dict, previous_error: str | None) -> SPLRule:
        """Build the prompt, call Gemini, return strictly typed Pydantic object."""
        if self.ai is None:
            raise ValueError(
                "Gemini client is unavailable (GEMINI_API_KEY is not set)."
            )

        prompt = self._build_prompt(profile, previous_error)

        # native schema validation
        response = self.ai.models.generate_content(
            model=self.model_name,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=SPLRule,
                temperature=0.2,
            ),
        )
        if not response.text:
            raise ValueError("Gemini returned an empty response.")
        return SPLRule.model_validate_json(response.text)

    def _build_prompt(self, profile: dict, previous_error: str | None) -> str:
        prompt = textwrap.dedent(f"""
            You are an expert Splunk Detection Engineer.
            Write a functional Splunk SPL detection rule for the MITRE ATT&CK technique below.

            ### Technique Profile
            - ID          : {profile.get("technique_id")}
            - Name        : {profile.get("technique_name")}
            - Tactics     : {", ".join(profile.get("tactics", []))}
            - Severity    : {profile.get("severity", "medium")}
            - Keywords    : {", ".join(profile.get("keywords", []))}
            - Log sources : {", ".join(profile.get("log_hints", []))}
            - Description : {profile.get("description", "")}
            - Detection   : {profile.get("detection_hint", "")}

            ### SPL Requirements
            - Start with a valid generating command: search, tstats, or inputlookup
            - Do NOT use backtick macros — write literal SPL only
            - Target realistic log sources from the log sources listed above
            - Avoid overly broad searches — always include at least one meaningful filter
            - Avoid regex unless absolutely necessary; prefer field=value or field IN (...) filters
            - If regex is required, ensure balanced parentheses and escape backslashes
        """).strip()

        if previous_error:
            correction = textwrap.dedent(f"""
                ### Correction Required
                Your previous SPL was rejected by Splunk with this error:
                  {previous_error}
                Rewrite the rule to fix this exact error. Do not repeat the same mistake.
            """).strip()
            prompt += f"\n\n{correction}"

        return prompt

    def _check_regex_sanity(self, rule_spl: str) -> str | None:
        lower = rule_spl.lower()
        if "regex" not in lower:
            return None

        if rule_spl.count("(") != rule_spl.count(")"):
            return "Regex has unbalanced parentheses. Avoid regex or fix the pattern."

        return None

    def _is_auth_error_message(self, message: str | None) -> bool:
        if not message:
            return False

        if hasattr(self.splunk, "is_session_error_message"):
            try:
                result = self.splunk.is_session_error_message(message)
                if isinstance(result, bool):
                    return result
            except Exception:
                pass

        text = str(message).lower()
        indicators = [
            "session is not logged in",
            "not logged in",
            "unauthorized",
            "authentication",
            "forbidden",
            "not connected to splunk",
        ]
        return any(token in text for token in indicators)
