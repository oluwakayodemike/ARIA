import unittest
from agents.blue_agent import BlueAgent

class MockSplunkClient:
    def __init__(self, rows=None):
        self.rows = rows

    def run_search(self, query, max_results=1000):
        return self.rows

STANDARD_ROWS = [
    # COVERED — rules exist and are enabled
    {"technique_id": "T1059", "technique_name": "Command Line Interface",
     "count": "5", "enabled_count": "5", "enabled_percentage": "100"},

    # PARTIAL — rules exist but all disabled
    {"technique_id": "T1078", "technique_name": "Valid Accounts",
     "count": "2", "enabled_count": "0", "enabled_percentage": "0"},

    # GAP — no rules at all
    {"technique_id": "T1003", "technique_name": "Credential Dumping",
     "count": "0", "enabled_count": "0", "enabled_percentage": "0"},

    # DUPLICATE of T1059 — lower verdict, should be ignored
    {"technique_id": "T1059", "technique_name": "Command Line Interface",
     "count": "1", "enabled_count": "0", "enabled_percentage": "0"},
]

class TestBlueAgent(unittest.TestCase):
    
    def test_standard_verdict_classification(self):
        blue = BlueAgent(MockSplunkClient(STANDARD_ROWS))
        result = blue.run()
        cmap = result["coverage_map"]

        self.assertEqual(cmap["T1059"]["verdict"], "COVERED", "T1059 should be COVERED")
        self.assertEqual(cmap["T1078"]["verdict"], "PARTIAL", "T1078 should be PARTIAL")
        self.assertEqual(cmap["T1003"]["verdict"], "GAP", "T1003 should be GAP")

    def test_duplicate_technique_id_resolution(self):
        blue = BlueAgent(MockSplunkClient(STANDARD_ROWS))
        result = blue.run()
        cmap = result["coverage_map"]

        self.assertEqual(cmap["T1059"]["verdict"], "COVERED", "Verdict should remain COVERED")
        self.assertEqual(cmap["T1059"]["total_rules"], 5, "Should retain the count from the COVERED row")
        self.assertEqual(cmap["T1059"]["enabled_rules"], 5, "Should retain the enabled_count from the COVERED row")

    def test_coverage_score_calculation(self):
        blue = BlueAgent(MockSplunkClient(STANDARD_ROWS))
        result = blue.run()
        score = result["score"]

        # 3 unique techniques: 1 covered, 1 partial, 1 gap
        # score = ((1 + 0.5) / 3) * 100 = 50.0
        self.assertEqual(score["score"], 50.0)
        self.assertEqual(score["covered"], 1)
        self.assertEqual(score["partial"], 1)
        self.assertEqual(score["gaps"], 1)
        self.assertEqual(score["total"], 3)

    def test_gap_and_partial_accessors(self):
        blue = BlueAgent(MockSplunkClient(STANDARD_ROWS))
        result = blue.run()
        cmap = result["coverage_map"]

        gaps = blue.get_gaps(cmap)
        partials = blue.get_partials(cmap)

        self.assertEqual(len(gaps), 1)
        self.assertEqual(gaps[0]["technique_id"], "T1003")
        
        self.assertEqual(len(partials), 1)
        self.assertEqual(partials[0]["technique_id"], "T1078")

    def test_empty_lookup_table(self):
        blue = BlueAgent(MockSplunkClient([]))
        result = blue.run()
        
        self.assertEqual(result["score"]["score"], 0)
        self.assertEqual(result["coverage_map"], {})

    def test_dirty_and_malformed_data(self):
        dirty_rows = [
            {"technique_id": "",          "count": "1", "enabled_count": "1"},
            {"technique_id": "T1012,T1078","count": "1", "enabled_count": "1"},
            {"technique_id": "INVALID",   "count": "1", "enabled_count": "1"},
            {},  # completely empty row
        ]
        blue = BlueAgent(MockSplunkClient(dirty_rows))
        result = blue.run()

        self.assertEqual(result["coverage_map"], {}, "Malformed rows should be skipped")

    def test_non_numeric_count_handling(self):
        bad_count_rows = [
            {"technique_id": "T9999", "technique_name": "Test",
             "count": "abc", "enabled_count": "xyz", "enabled_percentage": "??"}
        ]
        blue = BlueAgent(MockSplunkClient(bad_count_rows))
        result = blue.run()
        
        self.assertEqual(result["coverage_map"]["T9999"]["verdict"], "GAP", "Bad numbers should default to 0 (GAP)")

if __name__ == "__main__":
    unittest.main()