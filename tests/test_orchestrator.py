import os
import sys
import threading
import unittest
from unittest.mock import MagicMock

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
