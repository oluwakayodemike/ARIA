import os
import time
import textwrap
from google import genai
from google.genai import types
from pydantic import BaseModel, Field, field_validator
from core.state import ARIAState, TechniqueState
from core.splunk_client import SplunkClient

# strict schema for AI response validation and parsing
class SPLRule(BaseModel):
    rule: str = Field(description="The actual Splunk search string (e.g., `index=* sourcetype=WinEventLog:Security`)")
    explanation: str = Field(description="A 1-2 sentence explanation of how this SPL works")
    confidence: float = Field(description="A float between 0.0 and 1.0 representing confidence")

    @field_validator("confidence")
    @classmethod
    def clamp_confidence(cls, v: float) -> float:
        return round(max(0.0, min(1.0, v)), 2)

class GapAgent:
    """
    SPL Detection Engineer Agent.
    Takes attack profiles from the Red Agent, generates SPL detection rules,
    validates them against Splunk, and stages validated rules for human approval.
    Uses iterative refinement — validation errors are fed back to the model.
    """

    MAX_RETRIES   = 2    # fix attempts after the initial generation
    REQUEST_DELAY = 0.5

    def __init__(self, splunk_client: SplunkClient, model_name: str = "gemini-2.5-flash"):
        self.splunk     = splunk_client
        self.model_name = model_name

        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY env is not set.")
        self.ai = genai.Client(api_key=api_key)

    def run(self, state: ARIAState, limit: int = 5) -> ARIAState:
        state.phase = "generating"

        candidates = [
            t for t in state.get_gaps()
            if t.attack_profile and not t.generated_rule
        ]

        if not candidates:
            state.log("GapAgent", "No profiled gaps available for rule generation.", level="info")
            return state

        # slice the candidate list to respect the limit
        candidates_to_process = candidates[:limit]

        state.log("GapAgent", f"Starting rule generation - {len(candidates_to_process)} techniques queued.")

        succeeded = 0
        failed    = 0

        for technique in candidates_to_process:
            try:
                self._process_technique(technique, state)
                succeeded += 1
            except Exception as e:
                failed += 1
                state.log(
                    "GapAgent",
                    f"Unrecoverable failure for {technique.technique_id}: {e}",
                    level="error"
                )
            finally:
                time.sleep(self.REQUEST_DELAY)

        state.log("GapAgent", f"Rule generation complete - {succeeded} succeeded, {failed} failed.")
        return state

    def _process_technique(self, technique: TechniqueState, state: ARIAState):
        """full lifecycle: generate → validate → retry with error context → stage."""
        state.log("GapAgent", f"Generating rule for {technique.technique_id} - {technique.technique_name}")

        profile        = technique.attack_profile
        previous_error = None

        for attempt in range(1, self.MAX_RETRIES + 2): 
            payload: SPLRule = self._call_ai(profile, previous_error)

            rule_spl    = payload.rule.strip()
            explanation = payload.explanation.strip()
            confidence  = payload.confidence

            if not rule_spl:
                raise ValueError("AI returned an empty SPL rule.")

            validation = self.splunk.validate_spl(rule_spl)

            if validation["valid"]:
                technique.generated_rule   = validation["normalized"]
                technique.rule_explanation = explanation
                technique.rule_confidence  = confidence
                technique.pending_approval = True
                state.log(
                    "GapAgent",
                    f"rule validated for {technique.technique_id} "
                    f"(attempt {attempt}, confidence {confidence})"
                )
                return

            previous_error = validation["error"]
            state.log(
                "GapAgent",
                f"SPL invalid for {technique.technique_id} "
                f"(attempt {attempt}): {previous_error}",
                level="warning"
            )

        raise ValueError(
            f"SPL still invalid after {self.MAX_RETRIES + 1} attempts. "
            f"Last error: {previous_error}"
        )

    def _call_ai(self, profile: dict, previous_error: str | None) -> SPLRule:
        """Build the prompt, call Gemini, return strictly typed Pydantic object."""
        prompt   = self._build_prompt(profile, previous_error)
        
        # native schema validation
        response = self.ai.models.generate_content(
            model    = self.model_name,
            contents = prompt,
            config   = types.GenerateContentConfig(
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
            - ID          : {profile.get('technique_id')}
            - Name        : {profile.get('technique_name')}
            - Tactics     : {', '.join(profile.get('tactics', []))}
            - Severity    : {profile.get('severity', 'medium')}
            - Keywords    : {', '.join(profile.get('keywords', []))}
            - Log sources : {', '.join(profile.get('log_hints', []))}
            - Description : {profile.get('description', '')}
            - Detection   : {profile.get('detection_hint', '')}

            ### SPL Requirements
            - Start with a valid generating command: search, tstats, or inputlookup
            - Do NOT use backtick macros — write literal SPL only
            - Target realistic log sources from the log sources listed above
            - Avoid overly broad searches — always include at least one meaningful filter
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