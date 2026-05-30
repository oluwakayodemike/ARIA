import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import unittest
from unittest.mock import MagicMock, patch, call
from pydantic import ValidationError

from agents.gap_agent import GapAgent, SPLRule
from core.state import ARIAState, TechniqueState

def _mock_splunk(valid=True, error=None, normalized="search index=* | head 10"):
    """Return a mock SplunkClient with a fixed validate_spl response."""
    client = MagicMock()
    client.validate_spl.return_value = {
        "valid"     : valid,
        "error"     : error,
        "normalized": normalized,
    }
    return client

def _make_agent(splunk_client=None) -> GapAgent:
    """Instantiate GapAgent without hitting the real Gemini API or sleeping."""
    with patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"}):
        with patch("agents.gap_agent.genai.Client"):
            with patch("agents.gap_agent.time.sleep"):
                return GapAgent(splunk_client or _mock_splunk())


def _make_spl_rule(
    rule        = "search index=* sourcetype=syslog | head 10",
    explanation = "Detects suspicious activity.",
    confidence  = 0.85,
) -> SPLRule:
    return SPLRule(rule=rule, explanation=explanation, confidence=confidence)


def _make_gap(tid="T1566", name="Phishing", tactics=None) -> TechniqueState:
    """GAP technique with a fully populated attack_profile."""
    t = TechniqueState(
        technique_id   = tid,
        technique_name = name,
        verdict        = "GAP",
        tactics        = tactics or ["initial-access"],
        description    = "Adversaries send phishing emails with malicious links.",
        detection      = "Monitor for unusual outbound email patterns.",
    )
    t.attack_profile = {
        "technique_id"  : tid,
        "technique_name": name,
        "tactics"       : tactics or ["initial-access"],
        "severity"      : "high",
        "keywords"      : ["phishing", "email", "attachment", "link"],
        "log_hints"     : ["web", "proxy", "authentication"],
        "description"   : "Adversaries send phishing emails with malicious links.",
        "detection_hint": "Monitor for unusual outbound email patterns.",
    }
    return t


def _state(*techniques) -> ARIAState:
    state = ARIAState()
    for t in techniques:
        state.techniques[t.technique_id] = t
    state.gap_count = sum(1 for t in techniques if t.verdict == "GAP")
    return state


class TestSPLRuleSchema(unittest.TestCase):
    def test_valid_rule_accepted(self):
        rule = SPLRule(
            rule        = "search index=* sourcetype=WinEventLog | head 10",
            explanation = "Detects login events.",
            confidence  = 0.9,
        )
        self.assertEqual(rule.confidence, 0.9)

    def test_confidence_above_one_is_clamped(self):
        rule = SPLRule(rule="search index=*", explanation="x", confidence=1.5)
        self.assertEqual(rule.confidence, 1.0)

    def test_confidence_below_zero_is_clamped(self):
        rule = SPLRule(rule="search index=*", explanation="x", confidence=-0.3)
        self.assertEqual(rule.confidence, 0.0)

    def test_confidence_is_rounded_to_two_decimal_places(self):
        rule = SPLRule(rule="search index=*", explanation="x", confidence=0.856789)
        self.assertEqual(rule.confidence, 0.86)

    def test_non_float_confidence_raises_validation_error(self):
        with self.assertRaises(ValidationError):
            SPLRule(rule="search index=*", explanation="x", confidence="high")

    def test_missing_rule_field_raises_validation_error(self):
        with self.assertRaises(ValidationError):
            SPLRule(explanation="x", confidence=0.5)

    def test_string_number_confidence_is_coerced_to_float(self):
        rule = SPLRule(rule="search index=*", explanation="x", confidence="0.85") # passed as string
        self.assertEqual(rule.confidence, 0.85) # validated as float
        self.assertIsInstance(rule.confidence, float)


class TestGapAgentInit(unittest.TestCase):
    def test_raises_without_api_key(self):
        env = {k: v for k, v in os.environ.items() if k != "GEMINI_API_KEY"}
        with patch.dict(os.environ, env, clear=True):
            with self.assertRaises(ValueError, msg="GEMINI_API_KEY env not set."):
                with patch("agents.gap_agent.genai.Client"):
                    GapAgent(_mock_splunk())

    def test_initialises_with_valid_key(self):
        agent = _make_agent()
        self.assertEqual(agent.model_name, "gemini-2.5-flash")
        self.assertEqual(agent.MAX_RETRIES, 2)

class TestGapAgentRun(unittest.TestCase):
    def test_phase_set_to_generating(self):
        state = ARIAState()
        agent = _make_agent()
        agent.run(state)
        self.assertEqual(state.phase, "generating")

    def test_no_candidates_returns_early(self):
        """Techniques without attack_profile must be skipped."""
        gap = TechniqueState(
            technique_id="T1566", technique_name="Phishing",
            verdict="GAP", tactics=["initial-access"]
        )
        # attack_profile is None - not eligible
        state = _state(gap)
        agent = _make_agent()
        agent.run(state)

        self.assertIsNone(state.techniques["T1566"].generated_rule)
        log_messages = [e["message"] for e in state.reasoning_log]
        self.assertTrue(any("No profiled gaps" in m for m in log_messages))

    def test_already_generated_techniques_are_skipped(self):
        """Techniques that already have a generated_rule must not be reprocessed."""
        gap = _make_gap("T1566")
        gap.generated_rule = "search index=* existing_rule"
        state = _state(gap)

        agent = _make_agent()
        with patch.object(agent, "_call_ai") as mock_call:
            agent.run(state)
            mock_call.assert_not_called()

    def test_limit_parameter_restricts_processing(self):
        """Only the first N candidates should be processed when limit is set."""
        gaps = [_make_gap(f"T{1000 + i}", f"Technique {i}") for i in range(5)]
        state = _state(*gaps)

        agent = _make_agent()
        with patch.object(agent, "_call_ai", return_value=_make_spl_rule()):
            agent.run(state, limit=2)

        processed = [t for t in state.techniques.values() if t.generated_rule is not None]
        self.assertEqual(len(processed), 2)

    def test_successful_rule_staged_for_approval(self):
        gap   = _make_gap("T1566")
        state = _state(gap)

        agent = _make_agent(_mock_splunk(
            valid      = True,
            normalized = "search index=main sourcetype=proxy phishing"
        ))
        with patch.object(agent, "_call_ai", return_value=_make_spl_rule(
            rule        = "search index=main sourcetype=proxy phishing",
            explanation = "Detects phishing via proxy logs.",
            confidence  = 0.9,
        )):
            agent.run(state)

        t = state.techniques["T1566"]
        self.assertEqual(t.generated_rule,   "search index=main sourcetype=proxy phishing")
        self.assertEqual(t.rule_explanation, "Detects phishing via proxy logs.")
        self.assertEqual(t.rule_confidence,  0.9)
        self.assertTrue(t.pending_approval)

    def test_failed_technique_does_not_block_next_technique(self):
        """An unrecoverable failure on one technique must not stop the pipeline."""
        gap1 = _make_gap("T1566", "Phishing")
        gap2 = _make_gap("T1059", "Command Script", ["execution"])
        state = _state(gap1, gap2)

        agent = _make_agent(_mock_splunk(valid=True))

        call_count = 0
        def side_effect(profile, previous_error):
            nonlocal call_count
            call_count += 1
            if profile["technique_id"] == "T1566":
                raise RuntimeError("Simulated AI failure")
            return _make_spl_rule()

        with patch.object(agent, "_call_ai", side_effect=side_effect):
            agent.run(state)

        self.assertIsNone(state.techniques["T1566"].generated_rule)
        self.assertIsNotNone(state.techniques["T1059"].generated_rule)

    def test_final_log_reports_correct_counts(self):
        gap1 = _make_gap("T1566", "Phishing")
        gap2 = _make_gap("T1059", "Command Script", ["execution"])
        state = _state(gap1, gap2)

        agent = _make_agent(_mock_splunk(valid=True))

        def side_effect(profile, previous_error):
            if profile["technique_id"] == "T1566":
                raise RuntimeError("Simulated failure")
            return _make_spl_rule()

        with patch.object(agent, "_call_ai", side_effect=side_effect):
            agent.run(state)

        final_log = state.reasoning_log[-1]["message"]
        self.assertIn("1 succeeded", final_log)
        self.assertIn("1 failed",    final_log)

    def test_error_logged_on_unrecoverable_failure(self):
        gap   = _make_gap("T1566")
        state = _state(gap)
        agent = _make_agent()

        with patch.object(agent, "_call_ai", side_effect=RuntimeError("boom")):
            agent.run(state)

        error_entries = [e for e in state.reasoning_log if e["level"] == "error"]
        self.assertGreater(len(error_entries), 0)
        self.assertTrue(any("T1566" in e["message"] for e in error_entries))

class TestProcessTechniqueRetry(unittest.TestCase):
    def test_retries_on_invalid_spl_and_succeeds(self):
        """
        First call returns SPL that fails validation.
        Second call (with error context) returns valid SPL.
        Technique must be staged after the second attempt.
        """
        gap   = _make_gap("T1566")
        state = _state(gap)

        splunk = MagicMock()
        splunk.validate_spl.side_effect = [
            {"valid": False, "error": "Unknown command 'badcmd'.", "normalized": None},
            {"valid": True,  "error": None, "normalized": "search index=* phishing"},
        ]
        agent = _make_agent(splunk)

        with patch.object(agent, "_call_ai", return_value=_make_spl_rule()):
            agent._process_technique(gap, state)

        self.assertEqual(splunk.validate_spl.call_count, 2)
        self.assertIsNotNone(gap.generated_rule)
        self.assertTrue(gap.pending_approval)

    def test_previous_error_passed_on_retry(self):
        """The validation error from attempt N must be passed to _call_ai on attempt N+1."""
        gap   = _make_gap("T1566")
        state = _state(gap)

        splunk = MagicMock()
        splunk.validate_spl.side_effect = [
            {"valid": False, "error": "Bad command.", "normalized": None},
            {"valid": True,  "error": None, "normalized": "search index=* phishing"},
        ]
        agent = _make_agent(splunk)

        call_args = []
        def capture(*args, **kwargs):
            call_args.append(args)
            return _make_spl_rule()

        with patch.object(agent, "_call_ai", side_effect=capture):
            agent._process_technique(gap, state)

        # first call: no previous error
        self.assertIsNone(call_args[0][1])
        # second call: error from first validation
        self.assertEqual(call_args[1][1], "Bad command.")

    def test_raises_after_all_retries_exhausted(self):
        """If every attempt fails validation, ValueError must be raised."""
        gap    = _make_gap("T1566")
        state  = _state(gap)
        splunk = _mock_splunk(valid=False, error="Persistent syntax error.")
        agent  = _make_agent(splunk)

        with patch.object(agent, "_call_ai", return_value=_make_spl_rule()):
            with self.assertRaises(ValueError, msg="SPL still invalid after"):
                agent._process_technique(gap, state)

        # initial + MAX_RETRIES attempts
        self.assertEqual(splunk.validate_spl.call_count, agent.MAX_RETRIES + 1)

    def test_raises_immediately_on_empty_spl(self):
        """Empty rule string must raise ValueError before hitting the validator."""
        gap    = _make_gap("T1566")
        state  = _state(gap)
        splunk = _mock_splunk()
        agent  = _make_agent(splunk)

        with patch.object(agent, "_call_ai", return_value=_make_spl_rule(rule="   ")):
            with self.assertRaises(ValueError, msg="AI returned an empty SPL rule"):
                agent._process_technique(gap, state)

        splunk.validate_spl.assert_not_called()

    def test_warning_logged_on_failed_validation_attempt(self):
        """Each failed validation attempt must produce a warning log entry."""
        gap   = _make_gap("T1566")
        state = _state(gap)

        splunk = MagicMock()
        splunk.validate_spl.side_effect = [
            {"valid": False, "error": "Bad command.", "normalized": None},
            {"valid": True,  "error": None, "normalized": "search index=* phishing"},
        ]
        agent = _make_agent(splunk)

        with patch.object(agent, "_call_ai", return_value=_make_spl_rule()):
            agent._process_technique(gap, state)

        warnings = [e for e in state.reasoning_log if e["level"] == "warning"]
        self.assertEqual(len(warnings), 1)
        self.assertIn("T1566", warnings[0]["message"])


class TestCallAi(unittest.TestCase):
    def test_raises_on_empty_response(self):
        agent = _make_agent()

        mock_response      = MagicMock()
        mock_response.text = None
        agent.ai.models.generate_content = MagicMock(return_value=mock_response)

        with self.assertRaises(ValueError, msg="Gemini returned an empty response"):
            agent._call_ai({"technique_id": "T1566"}, None)

    def test_returns_spl_rule_on_valid_response(self):
        agent = _make_agent()

        mock_response      = MagicMock()
        mock_response.text = '{"rule": "search index=*", "explanation": "test", "confidence": 0.8}'
        agent.ai.models.generate_content = MagicMock(return_value=mock_response)

        result = agent._call_ai({"technique_id": "T1566", "technique_name": "Phishing",
                                  "tactics": [], "severity": "high", "keywords": [],
                                  "log_hints": [], "description": "", "detection_hint": ""}, None)

        self.assertIsInstance(result, SPLRule)
        self.assertEqual(result.confidence, 0.8)

class TestBuildPrompt(unittest.TestCase):
    def setUp(self):
        self.agent   = _make_agent()
        self.profile = {
            "technique_id"  : "T1566",
            "technique_name": "Phishing",
            "tactics"       : ["initial-access"],
            "severity"      : "high",
            "keywords"      : ["phishing", "email"],
            "log_hints"     : ["web", "proxy"],
            "description"   : "Adversaries send phishing emails.",
            "detection_hint": "Monitor email patterns.",
        }

    def test_prompt_contains_technique_id(self):
        prompt = self.agent._build_prompt(self.profile, None)
        self.assertIn("T1566", prompt)

    def test_prompt_contains_technique_name(self):
        prompt = self.agent._build_prompt(self.profile, None)
        self.assertIn("Phishing", prompt)

    def test_prompt_contains_keywords(self):
        prompt = self.agent._build_prompt(self.profile, None)
        self.assertIn("phishing", prompt)
        self.assertIn("email", prompt)

    def test_prompt_contains_log_hints(self):
        prompt = self.agent._build_prompt(self.profile, None)
        self.assertIn("web", prompt)
        self.assertIn("proxy", prompt)

    def test_prompt_has_no_correction_section_without_error(self):
        prompt = self.agent._build_prompt(self.profile, None)
        self.assertNotIn("Correction Required", prompt)

    def test_prompt_has_correction_section_with_error(self):
        prompt = self.agent._build_prompt(self.profile, "Unknown command 'badcmd'.")
        self.assertIn("Correction Required",            prompt)
        self.assertIn("Unknown command 'badcmd'.",      prompt)

    def test_correction_section_separated_from_main_prompt(self):
        """Must have a blank line between the main prompt and correction section."""
        prompt = self.agent._build_prompt(self.profile, "Some error.")
        self.assertIn("\n\n", prompt,
                      "Correction section must be separated by a blank line")

    def test_correction_section_not_concatenated_directly(self):
        """The last char of main prompt and first char of correction must not touch."""
        prompt = self.agent._build_prompt(self.profile, "Some error.")
        # after the last requirement line, there must be whitespace before ###
        self.assertNotIn("filter### Correction", prompt)
        self.assertNotIn("filter\n### Correction", prompt)

    def test_prompt_has_no_leading_indentation(self):
        """textwrap.dedent must strip method indentation from all lines."""
        prompt = self.agent._build_prompt(self.profile, None)
        for line in prompt.splitlines():
            if line:  # skip blank lines
                self.assertFalse(
                    line.startswith("    "),
                    f"Line has leading indentation: {repr(line)}"
                )

    def test_prompt_contains_spl_requirements(self):
        prompt = self.agent._build_prompt(self.profile, None)
        self.assertIn("backtick macros", prompt)
        self.assertIn("generating command", prompt)

    def test_prompt_survives_empty_attack_profile(self):
        """Must not raise errors if attack profile is missing data fields."""
        sparse_profile = {"technique_id": "T1234"}
        prompt = self.agent._build_prompt(sparse_profile, None)
        self.assertIn("T1234", prompt)
        self.assertIn("Severity    : medium", prompt) # test the default fallback


if __name__ == "__main__":
    unittest.main()