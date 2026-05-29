import os
import sys
from dotenv import load_dotenv
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


from core.splunk_client import SplunkClient
from core.mitre_loader import MitreLoader
from agents.blue_agent import BlueAgent
from agents.red_agent import RedAgent
from core.state import ARIAState

def main():
    load_dotenv()
    client = SplunkClient()
    if not client.connect():
        print("ERROR: could not connect to Splunk. run test_connection.py to debug.")
        return

    print("\n" + "=" * 55)
    print("MITRE ATT&CK loader")
    print("=" * 55)

    loader     = MitreLoader()
    techniques = loader.load()

    print(f"  Total techniques : {len(techniques)}")
    print(f"  Tactics found    : {len(loader.get_all_tactics())}")
    print(f"\n  Priority techniques (top 5):")
    for t in loader.get_priority_techniques(5):
        print(f"  {t['technique_id']} | {t['name']} | {t['tactics']}")

    print("\n" + "=" * 55)
    print("Blue Agent - LIVE audit against real Splunk")
    print("=" * 55)

    blue   = BlueAgent(client, mitre_loader=loader)
    result = blue.run()
    cmap   = result["coverage_map"]

    print("\n  Sample entries (first 10):")
    for tid, data in list(cmap.items())[:10]:
        verdict = data["verdict"]
        label   = f"[{verdict}]"
        print(f"  {tid:<10} {data['technique_name']:<45} {label}")

    gaps     = blue.get_gaps(cmap)
    partials = blue.get_partials(cmap)

    print(f"\n  Gaps     : {len(gaps)}")
    print(f"  Partials : {len(partials)}")
    print(f"  Score    : {result['score']['score']}%")
    print("=" * 55)


    print("\n" + "=" * 55)
    print("Red Agent — live profile generation (5 techniques)")
    print("=" * 55)

    # build state from real Blue Agent output
    state = ARIAState()
    state.update_from_blue(result["coverage_map"], result["score"])

    # run Red Agent on just the first 5 gaps to inspect output
    gaps = state.get_gaps()[:5]
    limited_state = ARIAState()
    for t in gaps:
        limited_state.techniques[t.technique_id] = t

    RedAgent().run(limited_state)

    for t in limited_state.get_gaps():
        p = t.attack_profile
        print(f"\n  {p['technique_id']} — {p['technique_name']}")
        print(f"  Severity    : {p['severity']}")
        print(f"  Tactics     : {p['tactics']}")
        print(f"  Keywords    : {p['keywords']}")
        print(f"  Log hints   : {p['log_hints']}")
        print(f"  Description : {p['description'][:120]}...")


if __name__ == "__main__":
    main()