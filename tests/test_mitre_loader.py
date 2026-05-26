import json
import os
import sys
import tempfile
import unittest

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.mitre_loader import MitreLoader


class TestMitreLoader(unittest.TestCase):
    def setUp(self):
        self.temp_files = []

    def tearDown(self):
        for path in self.temp_files:
            if os.path.exists(path):
                os.remove(path)

    def _write_bundle(self, bundle: dict) -> str:
        handle = tempfile.NamedTemporaryFile(
            mode="w",
            delete=False,
            suffix=".json",
            encoding="utf-8",
        )
        json.dump(bundle, handle)
        handle.close()
        self.temp_files.append(handle.name)
        return handle.name

    def _make_loader(self, bundle: dict) -> MitreLoader:
        return MitreLoader(self._write_bundle(bundle))

    def test_filters_and_parses_core_techniques(self):
        loader = self._make_loader(
            {
                "objects": [
                    {
                        "type": "attack-pattern",
                        "name": "Phishing",
                        "description": "x" * 2000, 
                        "external_references": [
                            {"source_name": "mitre-attack", "external_id": "T1566"}
                        ],
                        "kill_chain_phases": [
                            {"kill_chain_name": "mitre-attack", "phase_name": "initial-access"},
                            {"kill_chain_name": "mitre-attack", "phase_name": "persistence"},
                        ],
                        "x_mitre_platforms": ["Windows", "Linux"],
                        "x_mitre_detection": "Detect phishing" + ("y" * 1200),
                    },
                    {
                        "type": "attack-pattern",
                        "name": "Sub-technique should be skipped",
                        "external_references": [
                            {"source_name": "mitre-attack", "external_id": "T1566.001"}
                        ],
                        "x_mitre_is_subtechnique": True,
                    },
                    {
                        "type": "attack-pattern",
                        "name": "Deprecated technique should be skipped",
                        "external_references": [
                            {"source_name": "mitre-attack", "external_id": "T0001"}
                        ],
                        "x_mitre_deprecated": True,
                    },
                    {
                        "type": "course-of-action",
                        "name": "Non-technique object should be skipped",
                    },
                ]
            }
        )

        techniques = loader.load()

        self.assertEqual(len(techniques), 1)
        self.assertEqual(techniques[0]["technique_id"], "T1566")
        self.assertEqual(techniques[0]["name"], "Phishing")
        self.assertEqual(techniques[0]["tactics"], ["initial-access", "persistence"])
        self.assertEqual(techniques[0]["platforms"], ["Windows", "Linux"])
        self.assertLessEqual(len(techniques[0]["description"]), 1500)
        self.assertLessEqual(len(techniques[0]["detection"]), 1000)
        self.assertTrue(techniques[0]["url"].endswith("/T1566/"))

    def test_lookup_helpers_are_case_insensitive(self):
        loader = self._make_loader(
            {
                "objects": [
                    {
                        "type": "attack-pattern",
                        "name": "Valid Accounts",
                        "external_references": [
                            {"source_name": "mitre-attack", "external_id": "T1078"}
                        ],
                        "kill_chain_phases": [
                            {"kill_chain_name": "mitre-attack", "phase_name": "initial-access"},
                            {"kill_chain_name": "mitre-attack", "phase_name": "lateral-movement"},
                        ],
                    },
                    {
                        "type": "attack-pattern",
                        "name": "Command and Scripting Interpreter",
                        "external_references": [
                            {"source_name": "mitre-attack", "external_id": "T1059"}
                        ],
                        "kill_chain_phases": [
                            {"kill_chain_name": "mitre-attack", "phase_name": "execution"},
                        ],
                    },
                ]
            }
        )

        self.assertEqual(loader.get_by_id("t1078")["name"], "Valid Accounts")
        self.assertEqual(len(loader.get_by_tactic("INITIAL-ACCESS")), 1)
        self.assertEqual(len(loader.get_by_tactic("lateral-movement")), 1)
        self.assertEqual(loader.get_all_tactics(), ["execution", "initial-access", "lateral-movement"])

    def test_priority_techniques_follow_expected_order(self):
        loader = self._make_loader(
            {
                "objects": [
                    {
                        "type": "attack-pattern",
                        "name": "Exploit Public-Facing Application",
                        "external_references": [
                            {"source_name": "mitre-attack", "external_id": "T1190"}
                        ],
                        "kill_chain_phases": [
                            {"kill_chain_name": "mitre-attack", "phase_name": "initial-access"},
                        ],
                    },
                    {
                        "type": "attack-pattern",
                        "name": "Phishing",
                        "external_references": [
                            {"source_name": "mitre-attack", "external_id": "T1566"}
                        ],
                        "kill_chain_phases": [
                            {"kill_chain_name": "mitre-attack", "phase_name": "initial-access"},
                        ],
                    },
                    {
                        "type": "attack-pattern",
                        "name": "System Network Connections Discovery",
                        "external_references": [
                            {"source_name": "mitre-attack", "external_id": "T1049"}
                        ],
                        "kill_chain_phases": [
                            {"kill_chain_name": "mitre-attack", "phase_name": "discovery"},
                        ],
                    },
                ]
            }
        )

        priority_ids = [t["technique_id"] for t in loader.get_priority_techniques(limit=3)]

        self.assertEqual(priority_ids, ["T1566", "T1190"])

    def test_get_by_id_returns_none_for_unknown(self):
        loader = self._make_loader({"objects": []})
        self.assertIsNone(loader.get_by_id("T9999"), "Should return None for non-existent techniques")

    def test_load_caches_result(self):
        """load() called twice should return the exact same list object in memory."""
        loader = self._make_loader({"objects": []})
        first  = loader.load()
        second = loader.load()
        self.assertIs(first, second, "Should return cached list, not reload from disk")

if __name__ == "__main__":
    unittest.main()