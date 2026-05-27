import os
import sys
from dotenv import load_dotenv
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


from core.splunk_client import SplunkClient
from core.mitre_loader import MitreLoader
from agents.blue_agent import BlueAgent


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


if __name__ == "__main__":
    main()