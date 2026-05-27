import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import unittest
from agents.blue_agent import BlueAgent

class MockSplunkClient:
    def __init__(self, rows=None):
        self.rows = rows if rows is not None else []

    def run_search(self, query, max_results=1000):
        return self.rows

class MockMitreLoader:
    def __init__(self, techniques=None):
        self.techniques = techniques if techniques is not None else []
        
    def load(self):
        return self.techniques

# MOCK DATA FOR TESTING
def _make_technique(tid, name, tactics):
    return {
        "technique_id": tid,
        "name"        : name,
        "tactics"     : tactics,
        "platforms"   : [],
        "description" : "",
        "detection"   : "",
        "url"         : f"https://attack.mitre.org/techniques/{tid}/",
    }

STANDARD_ROWS = [
    {"technique_id": "T1059", "technique_name": "Command Line Interface", "count": "5", "enabled_count": "5", "enabled_percentage": "100"},
    {"technique_id": "T1078", "technique_name": "Valid Accounts", "count": "2", "enabled_count": "0", "enabled_percentage": "0"},
    {"technique_id": "T1003", "technique_name": "Credential Dumping", "count": "0", "enabled_count": "0", "enabled_percentage": "0"},
    {"technique_id": "T1059", "technique_name": "Command Line Interface", "count": "1", "enabled_count": "0", "enabled_percentage": "0"}, # duplicate
]

STANDARD_MITRE = [
    _make_technique("T1059", "Command Line Interface", ["execution"]),
    _make_technique("T1078", "Valid Accounts",         ["initial-access"]),
    _make_technique("T1003", "Credential Dumping",     ["credential-access"]),
]

class TestBlueAgent(unittest.TestCase):
    
    def test_standard_verdict_classification(self):
        blue = BlueAgent(MockSplunkClient(STANDARD_ROWS), MockMitreLoader(STANDARD_MITRE))
        result = blue.run()
        cmap = result["coverage_map"]

        self.assertEqual(cmap["T1059"]["verdict"], "COVERED", "T1059 should be COVERED")
        self.assertEqual(cmap["T1078"]["verdict"], "PARTIAL", "T1078 should be PARTIAL")
        self.assertEqual(cmap["T1003"]["verdict"], "GAP", "T1003 should be GAP")

    def test_technique_absent_from_splunk_entirely_is_true_gap(self):
        """
        a technique in MITRE but with zero presence in Splunk
        must be a GAP, not just ignored.
        """
        rows = [
            {"technique_id": "T1059", "technique_name": "Command Line", 
             "count": "5", "enabled_count": "5", "enabled_percentage": "100"}
        ]
        mitre_mock = [
            _make_technique("T1059", "Command Line", ["execution"]),
            _make_technique("T1566", "Phishing",     ["initial-access"]),
        ]
        
        blue   = BlueAgent(MockSplunkClient(rows), MockMitreLoader(mitre_mock))
        result = blue.run()
        
        self.assertEqual(result["coverage_map"]["T1059"]["verdict"], "COVERED")
        self.assertEqual(result["coverage_map"]["T1566"]["verdict"], "GAP", "T1566 absent from Splunk entirely - TRUE GAP")
        self.assertEqual(result["score"]["gaps"],    1)
        self.assertEqual(result["score"]["covered"], 1)
        self.assertEqual(result["score"]["total"],   2)

    def test_duplicate_technique_id_resolution(self):
        blue = BlueAgent(MockSplunkClient(STANDARD_ROWS), MockMitreLoader(STANDARD_MITRE))
        result = blue.run()
        cmap = result["coverage_map"]

        self.assertEqual(cmap["T1059"]["verdict"], "COVERED", "Verdict should remain COVERED")
        self.assertEqual(cmap["T1059"]["total_rules"], 5, "Should retain the count from the COVERED row")
        self.assertEqual(cmap["T1059"]["enabled_rules"], 5, "Should retain the enabled_count from the COVERED row")

    def test_coverage_score_calculation(self):
        blue = BlueAgent(MockSplunkClient(STANDARD_ROWS), MockMitreLoader(STANDARD_MITRE))
        result = blue.run()
        score = result["score"]

        # 3 unique techniques: 1 covered, 1 partial, 1 gap
        # score = ((1 + 0.5) / 3) * 100 = 50.0
        self.assertEqual(score["score"], 50.0)
        self.assertEqual(score["total"], 3)
        self.assertEqual(score["covered"], 1)
        self.assertEqual(score["partial"], 1)
        self.assertEqual(score["gaps"], 1)

    def test_gap_and_partial_accessors(self):
        blue = BlueAgent(MockSplunkClient(STANDARD_ROWS), MockMitreLoader(STANDARD_MITRE))
        result = blue.run()
        cmap = result["coverage_map"]

        gaps = blue.get_gaps(cmap)
        partials = blue.get_partials(cmap)

        self.assertEqual(len(gaps), 1)
        self.assertEqual(gaps[0]["technique_id"], "T1003")
        
        self.assertEqual(len(partials), 1)
        self.assertEqual(partials[0]["technique_id"], "T1078")

    def test_empty_lookup_table(self):
        blue = BlueAgent(MockSplunkClient([]), MockMitreLoader(STANDARD_MITRE))
        result = blue.run()
        
        self.assertEqual(result["score"]["score"], 0)
        self.assertEqual(len(result["coverage_map"]), 3)
        self.assertEqual(result["score"]["gaps"], 3)

    def test_dirty_and_malformed_data(self):
        dirty_rows = [
            {"technique_id": "",          "count": "1", "enabled_count": "1"},
            {"technique_id": "T1012,T1078","count": "1", "enabled_count": "1"},
            {"technique_id": "INVALID",   "count": "1", "enabled_count": "1"},
            {},  # completely empty row
        ]
        # mock is empty, so coverage map should be empty
        blue = BlueAgent(MockSplunkClient(dirty_rows), MockMitreLoader([]))
        result = blue.run()

        self.assertEqual(result["coverage_map"], {}, "Malformed rows should be skipped")

    def test_non_numeric_count_handling(self):
        bad_count_rows = [
            {"technique_id": "T9999", "technique_name": "Test", "count": "abc", "enabled_count": "xyz", "enabled_percentage": "??"}
        ]
        mitre_mock = [_make_technique("T9999", "Test", [])]
        
        blue = BlueAgent(MockSplunkClient(bad_count_rows), MockMitreLoader(mitre_mock))
        result = blue.run()
        
        self.assertEqual(result["coverage_map"]["T9999"]["verdict"], "GAP", "Bad numbers should default to 0 (GAP)")

    def test_trailing_comma_id_is_normalized_and_kept(self):
        rows = [{"technique_id": "T1012,", "technique_name": "Query Registry", "count": "2", "enabled_count": "0"}]
        mitre_mock = [_make_technique("T1012", "Query Registry", [])]
        
        blue   = BlueAgent(MockSplunkClient(rows), MockMitreLoader(mitre_mock))
        result = blue.run()
        
        self.assertIn("T1012", result["coverage_map"], "Trailing comma should be stripped and T1012 kept")
        self.assertEqual(result["coverage_map"]["T1012"]["verdict"], "PARTIAL")

    # Splunk failsafe test
    def test_splunk_failure_returns_safe_empty_result(self):
        """When Splunk is unreachable, run() should return a safe empty result."""
        class FailingSplunkClient:
            def run_search(self, *args, **kwargs):
                raise ConnectionError("Splunk is unreachable")
                
        blue   = BlueAgent(FailingSplunkClient(), MockMitreLoader(STANDARD_MITRE))
        result = blue.run()
        
        self.assertEqual(result["coverage_map"], {})
        self.assertEqual(result["score"]["score"], 0)
        self.assertIn("error", result, "Error message should be included in result when Splunk fails")

if __name__ == "__main__":
    unittest.main()