import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _run_id() -> str:
    """Unique run ID — timestamp + short UUID suffix to avoid same-second collisions."""
    ts    = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    short = uuid.uuid4().hex[:6]
    return f"{ts}_{short}"


@dataclass
class TechniqueState:
    """Represents ARIA's full knowledge about one ATT&CK technique."""
    technique_id      : str
    technique_name    : str
    verdict           : str                      # COVERED | PARTIAL | GAP
    tactics           : list  = field(default_factory=list)
    total_rules       : int   = 0
    enabled_rules     : int   = 0
    enabled_percentage: float = 0.0

    # MITRE source data populated by Blue Agent and read by Red Agent
    description       : str   = ""
    detection         : str   = ""

    attack_profile    : Optional[dict] = None

    generated_rule    : Optional[str]  = None
    rule_explanation  : Optional[str]  = None
    rule_confidence   : Optional[float] = None   # None = not yet scored, 0.0 = very low

    pending_approval  : bool = False
    approved          : bool = False
    rejected          : bool = False
    deployed          : bool = False

    def to_dict(self) -> dict:
        """JSON-serializable representation. Used by API and state persistence."""
        return {
            "technique_id"      : self.technique_id,
            "technique_name"    : self.technique_name,
            "verdict"           : self.verdict,
            "tactics"           : self.tactics,
            "total_rules"       : self.total_rules,
            "enabled_rules"     : self.enabled_rules,
            "enabled_percentage": self.enabled_percentage,
            "description"       : self.description,
            "detection"         : self.detection,
            "attack_profile"    : self.attack_profile,
            "generated_rule"    : self.generated_rule,
            "rule_explanation"  : self.rule_explanation,
            "rule_confidence"   : self.rule_confidence,
            "pending_approval"  : self.pending_approval,
            "approved"          : self.approved,
            "rejected"          : self.rejected,
            "deployed"          : self.deployed,
        }


@dataclass
class ARIAState:
    """
    Single source of truth for the entire ARIA pipeline.
    Orchestrator owns this. All agents receive it and return updates.
    Never mutated directly by agents, only the Orchestrator writes to it.
    """
    run_id          : str  = field(default_factory=_run_id)
    started_at      : str  = field(default_factory=_utcnow)
    completed_at    : Optional[str] = None

    techniques      : dict[str, TechniqueState] = field(default_factory=dict)
    coverage_score  : float = 0.0
    total_techniques: int   = 0
    covered_count   : int   = 0
    partial_count   : int   = 0
    gap_count       : int   = 0

    phase           : str   = "idle"  # idle | auditing | profiling | generating | awaiting_approval | done
    errors          : list  = field(default_factory=list)

    reasoning_log   : list  = field(default_factory=list)

    def log(self, agent: str, message: str, level: str = "info"):
        """
        append a reasoning log entry.
        level='error' also appends to self.errors for fast error checking.
        """
        entry = {
            "timestamp": _utcnow(),
            "agent"    : agent,
            "level"    : level,
            "message"  : message,
        }
        self.reasoning_log.append(entry)

        if level == "error":
            self.errors.append(entry.copy())

        print(f"  [{agent}] {message}")

    def update_from_blue(self, coverage_map: dict, score: dict):
        """Orchestrator calls this after Blue Agent runs."""
        self.coverage_score   = score["score"]
        self.total_techniques = score["total"]
        self.covered_count    = score["covered"]
        self.partial_count    = score["partial"]
        self.gap_count        = score["gaps"]

        self.techniques.clear()

        for tid, data in coverage_map.items():
            self.techniques[tid] = TechniqueState(
                technique_id       = data["technique_id"],
                technique_name     = data["technique_name"],
                tactics            = data.get("tactics") or [],
                verdict            = data["verdict"],
                total_rules        = data["total_rules"],
                enabled_rules      = data["enabled_rules"],
                enabled_percentage = data["enabled_percentage"],
                description        = data.get("description", ""),
                detection          = data.get("detection", ""),
            )

    def mark_complete(self):
        """Orchestrator calls this when the full pipeline finishes."""
        self.completed_at = _utcnow()
        self.phase        = "done"

    def get_gaps(self) -> list[TechniqueState]:
        """All GAP techniques - fed to Red Agent then Gap Agent."""
        return [t for t in self.techniques.values() if t.verdict == "GAP"]

    def get_partials(self) -> list[TechniqueState]:
        """Techniques with rules that exist but are all disabled."""
        return [t for t in self.techniques.values() if t.verdict == "PARTIAL"]

    def get_pending_approvals(self) -> list[TechniqueState]:
        """Rules staged by Gap Agent, awaiting human approval."""
        return [t for t in self.techniques.values() if t.pending_approval]

    def to_summary(self) -> dict:
        """Lightweight snapshot the API broadcasts to the frontend."""
        return {
            "run_id"           : self.run_id,
            "phase"            : self.phase,
            "coverage_score"   : self.coverage_score,
            "total_techniques" : self.total_techniques,
            "covered_count"    : self.covered_count,
            "partial_count"    : self.partial_count,
            "gap_count"        : self.gap_count,
            "pending_approvals": len(self.get_pending_approvals()),
            "error_count"      : len(self.errors),
            "reasoning_log"    : [e.copy() for e in self.reasoning_log[-20:]],
        }

    def to_dict(self) -> dict:
        """Full JSON-serializable state dump. Used for persistence and debugging."""
        return {
            "run_id"          : self.run_id,
            "started_at"      : self.started_at,
            "completed_at"    : self.completed_at,
            "phase"           : self.phase,
            "coverage_score"  : self.coverage_score,
            "total_techniques": self.total_techniques,
            "covered_count"   : self.covered_count,
            "partial_count"   : self.partial_count,
            "gap_count"       : self.gap_count,
            "errors"          : [e.copy() for e in self.errors],
            "reasoning_log"   : [e.copy() for e in self.reasoning_log],
            "techniques"      : {tid: t.to_dict()
                                 for tid, t in self.techniques.items()},
        }