import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.blue_agent import BlueAgent

class MockSplunkClient:
    def run_search(self, query, max_results=1000):
        """Simulates Splunk returning the MITRE lookup table."""
        print("   [mock] returning fake Splunk data...")
        return [
            # T1059 has rules and they are turned on - COVERED
            {"technique_id": "T1059", "technique_name": "Command Line", "count": "5", "enabled_count": "5"},
            
            # T1078 has rules but they are turned OFF - PARTIAL
            {"technique_id": "T1078", "technique_name": "Valid Accounts", "count": "2", "enabled_count": "0"},
            
            # T1003 has zero rules - GAPS
            {"technique_id": "T1003", "technique_name": "Credential Dumping", "count": "0", "enabled_count": "0"},
            
            # Edge case: T1059 has rules but enabled_count is not a number - should be treated as 0 -> PARTIAL
            {"technique_id": "T1059", "technique_name": "Command Line", "count": "1", "enabled_count": "0"}
        ]

def run_tests():
    print("="*60)
    print("BLUE AGENT TESTS")
    print("="*60)
    
    # inject the fake client into the real agent
    mock_client = MockSplunkClient()
    blue = BlueAgent(mock_client)
    
    # run agent
    result = blue.run()
    coverage = result["coverage_map"]
    
    try:
        assert coverage["T1059"]["verdict"] == "COVERED", "T1059 failed. Should be COVERED."
        assert coverage["T1078"]["verdict"] == "PARTIAL", "T1078 failed. Should be PARTIAL."
        assert coverage["T1003"]["verdict"] == "GAP", "T1003 failed. Should be GAP."

        # test math
        assert result["score"]["score"] == 50.0, f"math failed. expected 50.0%, got {result['score']['score']}%"
        
        print("\nALL TESTS PASSED! 🎉")
    except AssertionError as e:
        print(f"\nTEST FAILED: {e}")

if __name__ == "__main__":
    run_tests()