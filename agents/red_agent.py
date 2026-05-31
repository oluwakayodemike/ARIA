from core.state import ARIAState, TechniqueState


class RedAgent:
    """
    Attack profile generator.
    Takes GAP techniques from ARIAState and produces structured
    attack profiles describing what malicious activity would look
    like in Splunk logs. No AI, pure structured knowledge extraction
    from the MITRE ATT&CK data already loaded in each TechniqueState.
    """

    def __init__(self, anthropic_client=None):
        # anthropic_client injected for future AI-enhanced profiling
        # not used in v1 — profiles are built from ATT&CK data directly
        self.client = anthropic_client

    def run(self, state: ARIAState) -> ARIAState:
        """
        Generate attack profiles for every GAP technique in state.
        Updates state in place via Orchestrator convention.
        Returns state for chaining.
        """
        gaps = state.get_gaps()

        state.log("RedAgent", f"Starting attack profiling — {len(gaps)} techniques to profile")
        state.set_phase("profiling")

        if not gaps:
            state.log("RedAgent", "No gaps found — nothing to profile", level="info")
            return state

        profiled    = 0
        failed      = 0

        for technique in gaps:
            try:
                profile = self._build_profile(technique)
                with state.locked():
                    technique.attack_profile = profile
                profiled += 1
                state.log(
                    "RedAgent",
                    f"Profiled {technique.technique_id} — {technique.technique_name} "
                    f"[{', '.join(technique.tactics)}]"
                )
            except Exception as e:
                failed += 1
                state.log(
                    "RedAgent",
                    f"Failed to profile {technique.technique_id}: {e}",
                    level="error"
                )

        state.log(
            "RedAgent",
            f"Profiling complete — {profiled} succeeded, {failed} failed"
        )

        return state

    def _build_profile(self, technique: TechniqueState) -> dict:
        """
        Build a structured attack profile from ATT&CK technique data.
        This is what the Gap Agent uses to write a targeted SPL rule.
        """
        keywords  = self._extract_keywords(technique)
        log_hints = self._extract_log_hints(technique)
        severity  = self._assess_severity(technique)

        return {
            "technique_id"  : technique.technique_id,
            "technique_name": technique.technique_name,
            "tactics"       : technique.tactics,
            "severity"      : severity,
            "keywords"      : keywords,
            "log_hints"     : log_hints,
            "description"   : self._get_description(technique),
            "detection_hint": self._get_detection_hint(technique),
        }

    def _extract_keywords(self, technique: TechniqueState) -> list[str]:
        """
        Extract searchable keywords from technique name and description.
        Gap Agent embeds these into generated SPL rules.
        """
        name_words = [
            w.strip("(),.'\"").lower()
            for w in technique.technique_name.split()
            if len(w) > 3
        ]

        desc_words = []
        if technique.description:
            desc_words = [
                w.strip("(),.'\"").lower()
                for w in technique.description.split()
                if len(w) > 4 and w.isalpha()
            ]

        combined = name_words + desc_words
        return list(dict.fromkeys(combined))[:10]   # dedupe, cap at 10

    def _get_description(self, technique: TechniqueState) -> str:
        """Return MITRE description, falling back to technique name."""
        return technique.description or technique.technique_name

    def _get_detection_hint(self, technique: TechniqueState) -> str:
        """Return MITRE detection guidance if available."""
        return technique.detection or ""

    def _extract_log_hints(self, technique: TechniqueState) -> list[str]:
        """
        Map tactic names to the Splunk data sources most likely
        to contain evidence of this attack technique.
        """
        tactic_to_sources = {
            "initial-access"       : ["web", "firewall", "proxy", "authentication"],
            "execution"            : ["process", "endpoint", "sysmon", "powershell"],
            "persistence"          : ["registry", "scheduled_task", "startup", "service"],
            "privilege-escalation" : ["process", "authentication", "endpoint"],
            "defense-evasion"      : ["process", "endpoint", "registry"],
            "credential-access"    : ["authentication", "endpoint", "lsass"],
            "discovery"            : ["process", "network", "endpoint"],
            "lateral-movement"     : ["authentication", "network", "smb", "rdp"],
            "collection"           : ["endpoint", "file", "email"],
            "command-and-control"  : ["network", "dns", "proxy", "firewall"],
            "exfiltration"         : ["network", "dns", "proxy", "firewall"],
            "impact"               : ["endpoint", "backup", "service"],
            "reconnaissance"       : ["web", "network", "dns"],
        }

        hints = []
        for tactic in technique.tactics:
            hints.extend(tactic_to_sources.get(tactic, ["endpoint"]))

        # dedupe while preserving order
        return list(dict.fromkeys(hints))

    def _assess_severity(self, technique: TechniqueState) -> str:
        """
        Assign severity based on tactic stage.
        Later-stage tactics represent higher-impact attacks.
        """
        high_severity_tactics = {
            "impact",
            "exfiltration",
            "credential-access",
            "lateral-movement",
            "privilege-escalation",
        }
        medium_severity_tactics = {
            "execution",
            "persistence",
            "defense-evasion",
            "command-and-control",
            "collection",
        }

        for tactic in technique.tactics:
            if tactic in high_severity_tactics:
                return "high"

        for tactic in technique.tactics:
            if tactic in medium_severity_tactics:
                return "medium"

        return "low"