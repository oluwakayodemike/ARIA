import os
import sys
import threading
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.orchestrator import Orchestrator
from core.state import TechniqueState


class TestOrchestrator(unittest.TestCase):
    def setUp(self):
        self.mock_splunk = MagicMock()
        self.mock_gap = MagicMock()
        self.mock_mitre = MagicMock()
        self.orchestrator = Orchestrator(
            splunk_client=self.mock_splunk,
            gap_agent=self.mock_gap,
            mitre_loader=self.mock_mitre,
        )

    def test_concurrent_runs_blocked(self):
        started = threading.Event()
        proceed = threading.Event()

        def _hold_blue():
            started.set()
            proceed.wait(timeout=1)

        self.orchestrator.blue.run = MagicMock(side_effect=_hold_blue)

        t1 = threading.Thread(target=self.orchestrator.run)
        t1.start()
        started.wait(timeout=1)

        # try to start a second run on the main thread
        with self.assertRaises(RuntimeError, msg="An ARIA run is already in progress."):
            self.orchestrator.run()

        proceed.set()
        t1.join()

    def test_approve_rule_calls_splunk_and_updates_state(self):
        """human-in-the-loop deployment."""
        self.orchestrator.state.techniques["T1059"] = TechniqueState(
            technique_id="T1059",
            technique_name="Command and Scripting Interpreter",
            verdict="GAP",
            pending_approval=True,
            generated_rule="search index=*",
            rule_explanation="test",
        )
        self.mock_splunk.create_saved_search.return_value = True

        result = self.orchestrator.approve_rule("T1059")

        self.assertTrue(result)
        self.mock_splunk.create_saved_search.assert_called_once()
        self.assertFalse(self.orchestrator.state.techniques["T1059"].pending_approval)
        self.assertTrue(self.orchestrator.state.techniques["T1059"].approved)
        self.assertTrue(self.orchestrator.state.techniques["T1059"].deployed)

        self.mock_splunk.save_rule_memory.assert_called_once()
        persisted_kwargs = self.mock_splunk.save_rule_memory.call_args.kwargs
        self.assertIn("rule_provider", persisted_kwargs)
        self.assertIn("rule_provider_trace", persisted_kwargs)

    def test_demo_run_strictly_honors_gap_limit(self):
        payload = {
            "phase": "idle",
            "coverage_score": 0.0,
            "total_techniques": 3,
            "covered_count": 0,
            "partial_count": 0,
            "gap_count": 3,
            "generation_durations_sec": [1.1, 1.2, 1.3],
            "techniques": {
                "T1001": {
                    "technique_id": "T1001",
                    "technique_name": "One",
                    "verdict": "GAP",
                    "tactics": ["command-and-control"],
                    "generated_rule": "search index=one",
                    "pending_approval": True,
                },
                "T1002": {
                    "technique_id": "T1002",
                    "technique_name": "Two",
                    "verdict": "GAP",
                    "tactics": ["execution"],
                    "generated_rule": "search index=two",
                    "pending_approval": True,
                },
                "T1003": {
                    "technique_id": "T1003",
                    "technique_name": "Three",
                    "verdict": "GAP",
                    "tactics": ["impact"],
                    "generated_rule": "search index=three",
                    "pending_approval": True,
                },
            },
        }

        orchestrator = Orchestrator(
            splunk_client=self.mock_splunk,
            gap_agent=self.mock_gap,
            mitre_loader=self.mock_mitre,
            demo_mode=True,
            demo_simulate_run_sec=4,
        )
        orchestrator.set_demo_seed_payload(payload)

        with patch("agents.orchestrator.time.sleep"):
            state = orchestrator.run_demo(gap_limit=1)

        pending = state.get_pending_approvals()
        self.assertEqual(len(pending), 1)
        self.assertEqual(state.rules_generated, 1)
        self.assertEqual(state.generation_durations_sec, [1.1])

        log_messages = [entry["message"] for entry in state.reasoning_log]
        self.assertTrue(any("Profiled T1001" in message for message in log_messages))
        self.assertTrue(
            any("Starting rule generation - 1 techniques queued." in message for message in log_messages)
        )
