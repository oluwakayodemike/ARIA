from core.splunk_client import SplunkClient

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

    def __init__(self, splunk_client: SplunkClient):
        self.client = splunk_client

    def run(self) -> dict:
        print("\n Blue Agent - starting coverage audit...")
        try:
            raw          = self._fetch_lookup()
            coverage_map = self._build_coverage_map(raw)
            score        = self._compute_score(coverage_map)
        except Exception as e:
            print(f"   Blue Agent failed: {e}")
            return {"coverage_map": {}, "score": {"score": 0, "covered": 0, "partial": 0, "gaps": 0, "total": 0}, "error": str(e)}

        print(f"   Techniques audited : {score['total']}")
        print(f"   Covered         : {score['covered']}")
        print(f"   Partial         : {score['partial']}")
        print(f"   Gaps             : {score['gaps']}")
        print(f"   Coverage Score   : {score['score']}%")

        return {"coverage_map": coverage_map, "score": score}

    def _fetch_lookup(self) -> list:
        print("   querying MITRE ATT&CK compliance lookup...")
        rows = self.client.run_search(
            "| inputlookup mitre_all_rule_compliance_lookup.csv",
            max_results=1000
        )

        rows = rows or []

        print(f"   raw rows returned: {len(rows)}")
        return rows

    def _build_coverage_map(self, rows: list) -> dict:
        coverage_map = {}

        for row in rows:
            # silently skip any rows that aren't dicts or don't have the expected fields
            if not isinstance(row, dict):
                continue
            tid  = row.get("technique_id", "").strip().rstrip(",").strip()
            name = row.get("technique_name", "").strip()

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

            # determine Verdict
            if enabled_rules > 0:
                verdict = self.COVERED
            elif total_rules > 0:
                verdict = self.PARTIAL
            else:
                verdict = self.GAP

            # duplicate conflict resolution - if the same technique appears multiple times, keep the one with the highest verdict
            if tid in coverage_map:
                existing_verdict = coverage_map[tid]["verdict"]
                if self.VERDICT_WEIGHT[verdict] <= self.VERDICT_WEIGHT[existing_verdict]:
                    continue

            coverage_map[tid] = {
                "technique_id"      : tid,
                "technique_name"    : name,
                "verdict"           : verdict,
                "total_rules"       : total_rules,
                "enabled_rules"     : enabled_rules,
                "enabled_percentage": enabled_pct,
            }

        return coverage_map

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