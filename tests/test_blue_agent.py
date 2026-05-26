import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.blue_agent import BlueAgent


class MockSplunkClient:
    def __init__(self, rows=None):
        self.rows = rows

    def run_search(self, query, max_results=1000):
        print("   [mock] returning fake Splunk data...")
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


def run_tests():
    print("=" * 60)
    print("BLUE AGENT TEST SUITE")
    print("=" * 60)

    passed = 0
    failed = 0

    def assert_test(condition, name, detail=""):
        nonlocal passed, failed
        if condition:
            print(f"  ✅ PASS — {name}")
            passed += 1
        else:
            print(f"  ❌ FAIL — {name}: {detail}")
            failed += 1

    print("\n[1] Standard verdict classification")
    blue   = BlueAgent(MockSplunkClient(STANDARD_ROWS))
    result = blue.run()
    cmap   = result["coverage_map"]

    assert_test(cmap["T1059"]["verdict"] == "COVERED",
                "T1059 is COVERED (enabled rules exist)")
    assert_test(cmap["T1078"]["verdict"] == "PARTIAL",
                "T1078 is PARTIAL (rules exist but disabled)")
    assert_test(cmap["T1003"]["verdict"] == "GAP",
                "T1003 is GAP (no rules at all)")

    print("\n[2] Duplicate technique ID resolution")
    assert_test("T1059" in cmap and len([k for k in cmap if k == "T1059"]) == 1,
                "T1059 appears exactly once in coverage map")
    assert_test(cmap["T1059"]["verdict"] == "COVERED",
                "T1059 keeps best verdict (COVERED) when duplicate found")

    print("\n[3] Coverage score calculation")
    score = result["score"]
    assert_test(score["score"] == 50.0,
                f"Score is 50.0% (got {score['score']}%)")
    assert_test(score["covered"] == 1, "Covered count is 1")
    assert_test(score["partial"] == 1, "Partial count is 1")
    assert_test(score["gaps"]    == 1, "Gap count is 1")
    assert_test(score["total"]   == 3, "Total count is 3")

    print("\n[4] Gap and partial accessors")
    gaps     = blue.get_gaps(cmap)
    partials = blue.get_partials(cmap)

    assert_test(len(gaps) == 1 and gaps[0]["technique_id"] == "T1003",
                "get_gaps() returns exactly T1003")
    assert_test(len(partials) == 1 and partials[0]["technique_id"] == "T1078",
                "get_partials() returns exactly T1078")

    print("\n[5] Empty lookup table")
    blue_empty = BlueAgent(MockSplunkClient([]))
    result_empty = blue_empty.run()
    assert_test(result_empty["score"]["score"] == 0,
                "Score is 0% when no data returned")
    assert_test(result_empty["coverage_map"] == {},
                "Coverage map is empty dict when no data")

    print("\n[6] Dirty and malformed data")
    dirty_rows = [
        {"technique_id": "",          "count": "1", "enabled_count": "1"},
        {"technique_id": "T1012,T1078","count": "1", "enabled_count": "1"},
        {"technique_id": "INVALID",   "count": "1", "enabled_count": "1"},
        {},  # completely empty row
    ]
    blue_dirty = BlueAgent(MockSplunkClient(dirty_rows))
    result_dirty = blue_dirty.run()

    assert_test(result_dirty["coverage_map"] == {},
                "All unrecoverable malformed rows are skipped, coverage map is empty")

    print("\n[7] Non-numeric count handling")
    bad_count_rows = [
        {"technique_id": "T9999", "technique_name": "Test",
         "count": "abc", "enabled_count": "xyz", "enabled_percentage": "??"}
    ]
    blue_bad = BlueAgent(MockSplunkClient(bad_count_rows))
    result_bad = blue_bad.run()
    assert_test(result_bad["coverage_map"]["T9999"]["verdict"] == "GAP",
                "Non-numeric counts treated as 0, technique becomes GAP")

    print(f"\n{'='*60}")
    print(f"Results: {passed} passed, {failed} failed")
    if failed == 0:
        print("ALL TESTS PASSED 🎉")
    else:
        print(f"{failed} TEST(S) FAILED ❌")
    print("=" * 60)


if __name__ == "__main__":
    run_tests()