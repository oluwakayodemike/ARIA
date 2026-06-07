import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import unittest

from core.state import ARIAState

SAMPLE_COVERAGE = {
    "T1059": {
        "technique_id": "T1059",
        "technique_name": "Command Line",
        "tactics": ["execution"],
        "verdict": "COVERED",
        "total_rules": 5,
        "enabled_rules": 5,
        "enabled_percentage": 100.0,
    },
    "T1078": {
        "technique_id": "T1078",
        "technique_name": "Valid Accounts",
        "tactics": ["initial-access"],
        "verdict": "PARTIAL",
        "total_rules": 2,
        "enabled_rules": 0,
        "enabled_percentage": 0.0,
    },
    "T1566": {
        "technique_id": "T1566",
        "technique_name": "Phishing",
        "tactics": ["initial-access"],
        "verdict": "GAP",
        "total_rules": 0,
        "enabled_rules": 0,
        "enabled_percentage": 0.0,
    },
}

SAMPLE_SCORE = {"score": 50.0, "covered": 1, "partial": 1, "gaps": 1, "total": 3}


class TestARIAState(unittest.TestCase):
    def test_update_from_blue_populates_techniques(self):
        state = ARIAState()
        state.update_from_blue(SAMPLE_COVERAGE, SAMPLE_SCORE)

        self.assertEqual(len(state.techniques), 3)
        self.assertEqual(state.coverage_score, 50.0)
        self.assertEqual(state.gap_count, 1)
        self.assertEqual(state.partial_count, 1)
        self.assertEqual(state.covered_count, 1)
        self.assertEqual(state.techniques["T1059"].verdict, "COVERED")
        self.assertEqual(state.techniques["T1059"].tactics, ["execution"])
        self.assertEqual(state.techniques["T1059"].enabled_percentage, 100.0)

    def test_get_gaps_returns_only_gap_techniques(self):
        state = ARIAState()
        state.update_from_blue(SAMPLE_COVERAGE, SAMPLE_SCORE)

        gaps = state.get_gaps()
        self.assertEqual(len(gaps), 1)
        self.assertEqual(gaps[0].technique_id, "T1566")

    def test_get_partials_returns_only_partial_techniques(self):
        state = ARIAState()
        state.update_from_blue(SAMPLE_COVERAGE, SAMPLE_SCORE)

        partials = state.get_partials()
        self.assertEqual(len(partials), 1)
        self.assertEqual(partials[0].technique_id, "T1078")

    def test_log_appends_to_reasoning_log(self):
        state = ARIAState()
        state.log("BlueAgent", "Coverage audit complete")
        state.log("RedAgent", "Attack profiles generated", level="info")

        self.assertEqual(len(state.reasoning_log), 2)
        self.assertEqual(state.reasoning_log[0]["agent"], "BlueAgent")
        self.assertEqual(state.reasoning_log[1]["agent"], "RedAgent")
        self.assertIn("timestamp", state.reasoning_log[0])

    def test_to_summary_returns_lightweight_snapshot(self):
        state = ARIAState()
        state.update_from_blue(SAMPLE_COVERAGE, SAMPLE_SCORE)
        summary = state.to_summary()

        self.assertIn("run_id", summary)
        self.assertIn("coverage_score", summary)
        self.assertIn("phase", summary)
        self.assertIn("reasoning_log", summary)
        self.assertEqual(summary["coverage_score"], 50.0)
        self.assertEqual(summary["gap_count"], 1)

    def test_pending_approvals_queue(self):
        state = ARIAState()
        state.update_from_blue(SAMPLE_COVERAGE, SAMPLE_SCORE)

        state.techniques["T1566"].pending_approval = True
        state.techniques["T1566"].generated_rule = "search index=* phishing"

        pending = state.get_pending_approvals()
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0].technique_id, "T1566")
        self.assertEqual(pending[0].generated_rule, "search index=* phishing")

    def test_run_id_is_unique_per_instance(self):
        state1 = ARIAState()
        state2 = ARIAState()
        self.assertNotEqual(state1.run_id, state2.run_id)

    def test_error_log_also_appends_to_errors_list(self):
        state = ARIAState()
        state.log("Orchestrator", "something broke", level="error")
        state.log("Orchestrator", "this is fine", level="info")

        self.assertEqual(len(state.reasoning_log), 2)
        self.assertEqual(len(state.errors), 1)
        self.assertEqual(state.errors[0]["message"], "something broke")

    def test_to_dict_is_json_serializable(self):
        import json

        state = ARIAState()
        state.update_from_blue(SAMPLE_COVERAGE, SAMPLE_SCORE)
        state.log("BlueAgent", "audit complete")

        payload = state.to_dict()

        try:
            json.dumps(payload)
        except TypeError as e:
            self.fail(f"to_dict() is not JSON serializable: {e}")

        self.assertIn("techniques", payload)
        self.assertIn("T1059", payload["techniques"])
        self.assertIn("verdict", payload["techniques"]["T1059"])
        self.assertIn("rule_provider", payload["techniques"]["T1059"])
        self.assertIn("rule_provider_trace", payload["techniques"]["T1059"])

    def test_to_summary_reasoning_log_is_a_copy(self):
        state = ARIAState()
        state.log("BlueAgent", "original message")

        summary = state.to_summary()
        self.assertIsNot(summary["reasoning_log"], state.reasoning_log)
        summary["reasoning_log"][0]["message"] = "mutated"

        self.assertEqual(
            state.reasoning_log[0]["message"],
            "original message",
            "Summary log entries must be copies, not live references",
        )

    def test_mark_complete_sets_phase_and_timestamp(self):
        state = ARIAState()
        self.assertIsNone(state.completed_at)
        state.mark_complete()
        self.assertEqual(state.phase, "done")
        self.assertIsNotNone(state.completed_at)

    def test_update_from_blue_called_twice_replaces_state(self):
        state = ARIAState()
        state.update_from_blue(SAMPLE_COVERAGE, SAMPLE_SCORE)
        self.assertIn("T1566", state.techniques)

        # second call with completely different data
        new_coverage = {
            "T1110": {
                "technique_id": "T1110",
                "technique_name": "Brute Force",
                "tactics": ["credential-access"],
                "verdict": "GAP",
                "total_rules": 0,
                "enabled_rules": 0,
                "enabled_percentage": 0.0,
            }
        }
        new_score = {"score": 0.0, "covered": 0, "partial": 0, "gaps": 1, "total": 1}
        state.update_from_blue(new_coverage, new_score)

        self.assertNotIn("T1566", state.techniques, "Stale techniques must be cleared")
        self.assertIn("T1110", state.techniques)
        self.assertEqual(state.gap_count, 1)

    def test_provider_metadata_defaults(self):
        state = ARIAState()
        state.update_from_blue(SAMPLE_COVERAGE, SAMPLE_SCORE)

        t = state.techniques["T1059"]
        self.assertIsNone(t.rule_provider)
        self.assertEqual(t.rule_provider_trace, [])


if __name__ == "__main__":
    unittest.main()
