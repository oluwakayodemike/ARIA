from core.splunk_client import SplunkClient
from core.mitre_loader import MitreLoader

class BlueAgent:
    """
    Deterministic coverage auditor.
    Queries Splunk's MITRE ATT&CK compliance lookup and produces
    a verdict for every technique based on the number of existing rules covering that technique:
    """

    COVERED = "COVERED"
    PARTIAL = "PARTIAL"
    GAP     = "GAP"

    # keys are the string values of the coverage verdicts, values are their relative weights for scoring purposes.
    # must stay in sync if constants are changed.
    VERDICT_WEIGHT = {
        COVERED: 3,
        PARTIAL: 2,
        GAP: 1
    }

    def __init__(self, splunk_client: SplunkClient, mitre_loader: MitreLoader = None):
        self.client = splunk_client
        self.mitre = mitre_loader or MitreLoader()

    def run(self) -> dict:
        print("\nBlue Agent - starting coverage audit...")
        try:
            all_techniques   = self._load_all_techniques()
            splunk_coverage  = self._fetch_lookup()
            coverage_map     = self._build_coverage_map(all_techniques, splunk_coverage)
            score            = self._compute_score(coverage_map)
        except Exception as e:
            print(f"   Blue Agent failed: {e}")
            return {
                "coverage_map": {}, 
                "score": {"score": 0, "covered": 0, "partial": 0, "gaps": 0, "total": 0}, 
                "error": str(e)
            }

        print(f"   Techniques audited : {score['total']}")
        print(f"   Covered         : {score['covered']}")
        print(f"   Partial         : {score['partial']}")
        print(f"   Gaps             : {score['gaps']}")
        print(f"   Coverage Score   : {score['score']}%")

        return {"coverage_map": coverage_map, "score": score}

    def _load_all_techniques(self) -> dict:
        """Load every known ATT&CK technique. These are the ground truth."""
        print("   Loading full ATT&CK technique list...")
        techniques = self.mitre.load()
        # keyed by technique_id for fast lookup
        return {t["technique_id"]: t for t in techniques}
    
    def _fetch_lookup(self) -> dict:
        """
        fetch what Splunk currently knows about.
        returns a dict keyed by technique_id.
        """
        print("   Querying MITRE ATT&CK compliance lookup...")
        rows = self.client.run_search(
            "| inputlookup mitre_all_rule_compliance_lookup.csv",
            max_results=1000
        )
        rows = rows or []
        print(f"   Splunk lookup rows returned: {len(rows)}")

        splunk_map = {}
        for row in rows:
            if not isinstance(row, dict):
                continue

            tid = row.get("technique_id", "").strip().rstrip(",").strip().upper()
            if not tid or not tid.startswith("T") or "," in tid:
                continue

            try:
                total_rules   = int(row.get("count", 0))
                enabled_rules = int(row.get("enabled_count", 0))
                enabled_pct   = float(row.get("enabled_percentage", 0))
            except (ValueError, TypeError):
                total_rules = enabled_rules = 0
                enabled_pct = 0.0

            enabled_rules = min(enabled_rules, total_rules)
            if total_rules > 0:
                enabled_pct = round((enabled_rules / total_rules) * 100, 1)
            else:
                enabled_pct = 0.0

            # keep best verdict if duplicate
            if tid in splunk_map:
                existing = splunk_map[tid]
                
                new_verdict = self._verdict(enabled_rules, total_rules)
                old_verdict = self._verdict(existing["enabled_rules"], existing["total_rules"])

                # rank by verdict weight, then enabled rules, then total rules
                new_score = (self.VERDICT_WEIGHT.get(new_verdict, 1), enabled_rules, total_rules)
                old_score = (self.VERDICT_WEIGHT.get(old_verdict, 1), existing["enabled_rules"], existing["total_rules"])

                if new_score <= old_score:
                    continue

            splunk_map[tid] = {
                "total_rules"       : total_rules,
                "enabled_rules"     : enabled_rules,
                "enabled_percentage": enabled_pct,
            }

        return splunk_map

    def _build_coverage_map(self, all_techniques: dict, splunk_coverage: dict) -> dict:
        """
        Merge ALL ATT&CK techniques with Splunk's coverage data.
        Techniques absent from Splunk become TRUE GAPS.
        """
        coverage_map = {}

        for tid, technique in all_techniques.items():
            splunk_data   = splunk_coverage.get(tid)

            if splunk_data:
                total_rules   = splunk_data["total_rules"]
                enabled_rules = splunk_data["enabled_rules"]
                enabled_pct   = splunk_data["enabled_percentage"]
            else:
                total_rules = enabled_rules = 0
                enabled_pct = 0.0

            verdict = self._verdict(enabled_rules, total_rules)

            coverage_map[tid] = {
                "technique_id"      : tid,
                "technique_name"    : technique["name"],
                "tactics"           : technique["tactics"],
                "verdict"           : verdict,
                "total_rules"       : total_rules,
                "enabled_rules"     : enabled_rules,
                "enabled_percentage": enabled_pct,
                "description"       : technique.get("description", ""),
                "detection"         : technique.get("detection", ""), 
            }

        return coverage_map

    def _verdict(self, enabled_rules: int, total_rules: int) -> str:
        if enabled_rules > 0:
            return self.COVERED
        if total_rules > 0:
            return self.PARTIAL
        return self.GAP

    def _compute_score(self, coverage_map: dict) -> dict:
        total = len(coverage_map)
        if total == 0:
            return {"score": 0, "covered": 0, "partial": 0, "gaps": 0, "total": 0}

        covered = sum(1 for v in coverage_map.values() if v["verdict"] == self.COVERED)
        partial = sum(1 for v in coverage_map.values() if v["verdict"] == self.PARTIAL)
        gaps    = sum(1 for v in coverage_map.values() if v["verdict"] == self.GAP)
        
        score = ((covered + (partial * 0.5)) / total) * 100

        return {
            "score"  : round(score, 1),
            "covered": covered,
            "partial": partial,
            "gaps"   : gaps,
            "total"  : total,
        }

    def get_gaps(self, coverage_map: dict) -> list:
        return [v for v in coverage_map.values() if v["verdict"] == self.GAP]

    def get_partials(self, coverage_map: dict) -> list:
        return [v for v in coverage_map.values() if v["verdict"] == self.PARTIAL]