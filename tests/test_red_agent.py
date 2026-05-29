import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import unittest
from agents.red_agent import RedAgent
from core.state import ARIAState, TechniqueState


def _make_gap(tid, name, tactics, description="", detection=""):
    t = TechniqueState(
        technique_id   = tid,
        technique_name = name,
        verdict        = "GAP",
        tactics        = tactics,
        description    = description,
        detection      = detection,
    )
    return t


def _state_with_gaps(*techniques):
    state = ARIAState()
    for t in techniques:
        state.techniques[t.technique_id] = t
    state.gap_count = len(techniques)
    return state


class TestRedAgent(unittest.TestCase):

    def test_profiles_all_gap_techniques(self):
        state = _state_with_gaps(
            _make_gap("T1566", "Phishing",       ["initial-access"]),
            _make_gap("T1059", "Command Script",  ["execution"]),
        )
        RedAgent().run(state)

        for t in state.get_gaps():
            self.assertIsNotNone(t.attack_profile, f"{t.technique_id} should have a profile")

    def test_profile_has_required_fields(self):
        state = _state_with_gaps(_make_gap("T1566", "Phishing", ["initial-access"]))
        RedAgent().run(state)

        profile = state.techniques["T1566"].attack_profile
        for field in ["technique_id", "technique_name", "tactics", "severity", "keywords", "log_hints"]:
            self.assertIn(field, profile, f"Profile missing field: {field}")

    def test_severity_high_for_impact_tactic(self):
        state = _state_with_gaps(_make_gap("T1486", "Data Encrypted", ["impact"]))
        RedAgent().run(state)
        self.assertEqual(state.techniques["T1486"].attack_profile["severity"], "high")

    def test_severity_medium_for_execution_tactic(self):
        state = _state_with_gaps(_make_gap("T1059", "Command Script", ["execution"]))
        RedAgent().run(state)
        self.assertEqual(state.techniques["T1059"].attack_profile["severity"], "medium")

    def test_severity_low_for_reconnaissance_tactic(self):
        state = _state_with_gaps(_make_gap("T1595", "Active Scanning", ["reconnaissance"]))
        RedAgent().run(state)
        self.assertEqual(state.techniques["T1595"].attack_profile["severity"], "low")

    def test_log_hints_match_tactic(self):
        state = _state_with_gaps(_make_gap("T1110", "Brute Force", ["credential-access"]))
        RedAgent().run(state)
        hints = state.techniques["T1110"].attack_profile["log_hints"]
        self.assertIn("authentication", hints)

    def test_no_gaps_returns_state_unchanged(self):
        state = ARIAState()
        result = RedAgent().run(state)
        self.assertEqual(result.phase, "profiling")
        self.assertEqual(len(state.reasoning_log), 2)

    def test_phase_set_to_profiling(self):
        state = _state_with_gaps(_make_gap("T1566", "Phishing", ["initial-access"]))
        RedAgent().run(state)
        self.assertEqual(state.phase, "profiling")

    def test_reasoning_log_has_entries(self):
        state = _state_with_gaps(_make_gap("T1566", "Phishing", ["initial-access"]))
        RedAgent().run(state)
        agents = [e["agent"] for e in state.reasoning_log]
        self.assertTrue(all(a == "RedAgent" for a in agents))

    def test_covered_techniques_not_profiled(self):
        state = ARIAState()
        covered = TechniqueState(
            technique_id   = "T1059",
            technique_name = "Command Script",
            verdict        = "COVERED",
            tactics        = ["execution"],
        )
        state.techniques["T1059"] = covered
        RedAgent().run(state)
        self.assertIsNone(
            state.techniques["T1059"].attack_profile,
            "COVERED techniques must not be profiled"
        )

    def test_description_flows_into_profile(self):
        """Description must come from TechniqueState and not attack_profile."""
        state = _state_with_gaps(_make_gap("T1566", "Phishing", ["initial-access"], description="Adversaries send emails with malicious attachments."))
        RedAgent().run(state)
        profile = state.techniques["T1566"].attack_profile
        self.assertEqual(
            profile["description"],
            "Adversaries send emails with malicious attachments.",
            "Profile description must use technique.description, not fall back to name"
        )

    def test_description_falls_back_to_name_when_empty(self):
        """When description is empty, profile must fall back to technique name."""
        state = _state_with_gaps(_make_gap("T1566", "Phishing", ["initial-access"], description=""))
        RedAgent().run(state)
        self.assertEqual(
            state.techniques["T1566"].attack_profile["description"],
            "Phishing"
        )

    def test_keywords_extracted_from_description(self):
        """Keywords must include words from description, not just technique name."""
        state = _state_with_gaps(_make_gap("T1566", "Phishing", ["initial-access"], description="spearphishing attachment malware delivery victim"))
        RedAgent().run(state)
        keywords = state.techniques["T1566"].attack_profile["keywords"]
        self.assertIn("spearphishing", keywords)

if __name__ == "__main__":
    unittest.main()