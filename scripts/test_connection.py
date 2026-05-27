import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.splunk_client import SplunkClient

def main():
    client = SplunkClient()
    
    # connect to Splunk
    connected = client.connect()
    if not connected:
        print("Fix your connection before proceeding.")
        return

    print("\nfetching all saved searches...")
    searches = client.get_all_saved_searches()
    print(f"found {len(searches)} saved searches in Splunk\n")

    # print first 5 with their names
    for s in searches[:5]:
        print(f"  → {s['name']}")
        print(f"     Tags: {s['tags']}")
        print(f"     Query preview: {s['query'][:80]}...")
        print()

    print("\nfull content dump of first rule (finding ATT&CK fields):")
    raw = list(client.service.saved_searches)[0]
    for key, val in raw.content.items():
        if val and val != "0" and val != "":
            print(f"  {key}: {str(val)[:120]}")

    print("\n==========================================")
    print("Querying MITRE ATT&CK compliance lookup...")
    print("==========================================")
    try:
        results = client.run_search(
            "| inputlookup mitre_all_rule_compliance_lookup.csv | head 30",
            max_results=30
        )
        print(f"  Rows returned: {len(results)}")
        if results:
            print(f"\n  Column names: {list(results[0].keys())}")
            print(f"\n  Sample rows:")
            for r in results[:5]:
                print(f"    {r}")
        else:
            print("  Empty — trying to find the right lookup name...")
            lookups = client.run_search(
                "| rest /servicesNS/-/-/data/lookup-table-files | table title",
                max_results=50
            )
            print(f"\n  Available lookup tables:")
            for l in lookups:
                print(f"    → {l.get('title', '')}")
    except Exception as e:
        print(f"  Error: {e}")

    # ==========================================
    # SPL VALIDATOR TEST
    # ==========================================
    print("\n==========================================")
    print("Testing SPL validator...")
    print("==========================================")

    r1 = client.validate_spl("index=* | head 10")
    print(f"  Plain filter: {r1}")

    r2 = client.validate_spl("tstats count | head 10")
    print(f"  Generating command: {r2}")

    r3 = client.validate_spl("| inputlookup mitre_all_rule_compliance_lookup.csv")
    print(f"  Pipe command: {r3}")

    r4 = client.validate_spl("index=* | totallyFakeCommand xyz")
    print(f"  Bad SPL: {r4}")

if __name__ == "__main__":
    main()