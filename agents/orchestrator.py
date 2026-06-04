import logging
import threading
from typing import Callable, Optional

from agents.blue_agent import BlueAgent
from agents.gap_agent import GapAgent
from agents.red_agent import RedAgent
from core.mitre_loader import MitreLoader
from core.splunk_client import SplunkClient
from core.state import ARIAState


class Orchestrator:
    """
    Coordinates the full ARIA pipeline: Blue Agent → Red Agent → Gap Agent.

    Owns the ARIAState and is the only component allowed to write to it
    (outside of agents which receive it as a parameter).

    Thread model:
      - run() is blocking and designed to be called from a background thread.
      - approve_rule() and reject_rule() are thread-safe and can be called
        concurrently from the FastAPI request thread while a run is in progress.
      - All state reads from the API layer go through get_summary() / get_technique().
    """

    def __init__(
        self,
        splunk_client: SplunkClient,
        gap_agent: GapAgent,
        mitre_loader: Optional[MitreLoader] = None,
        on_state_change: Optional[Callable[[dict], None]] = None,
    ):
        self.splunk = splunk_client
        self.mitre = mitre_loader or MitreLoader()
        self.gap_agent = gap_agent
        self.on_state_change = on_state_change

        self.blue = BlueAgent(splunk_client, self.mitre)
        self.red = RedAgent()

        self.state = ARIAState()
        self._lock = threading.Lock()
        self.is_running = False

    def run(self, gap_limit: int = 10) -> ARIAState:
        """
        Execute the full ARIA pipeline synchronously.
        Designed to be called from a background thread via FastAPI's thread pool.
        Raises RuntimeError if a run is already in progress.
        """
        with self._lock:
            if self.is_running:
                raise RuntimeError("An ARIA run is already in progress.")
            self.is_running = True
            self.state = ARIAState()

        try:
            self._run_blue()
            self._run_red()
            self._run_gap(gap_limit)

            self.state.mark_complete()
            self.state.log("Orchestrator", "Pipeline complete.")

        except Exception as e:
            self.state.log("Orchestrator", f"Pipeline failed: {e}", level="error")
            self.state.set_phase("error")

        finally:
            with self._lock:
                self.is_running = False
            self._notify()

        return self.state

    def approve_rule(self, technique_id: str) -> bool:
        """
        Approve a staged rule and mark it as ready for deployment.
        Thread-safe - can be called from the API layer during a live run.
        Returns False if the technique does not exist or is not pending approval.
        """
        with self.state.locked():
            technique = self.state.techniques.get(technique_id)
            if not technique or not technique.pending_approval:
                self.state.log(
                    "Orchestrator",
                    f"Approve requested for {technique_id} but it is not pending approval",
                    level="info",
                )
                return False

            rule = technique.generated_rule
            explanation = technique.rule_explanation or ""
            technique_name = technique.technique_name

            # reserve the approval to prevent double-deploys from concurrent requests.
            technique.pending_approval = False

        if not rule:
            self.state.log(
                "Orchestrator",
                f"Rule approval failed for {technique_id} - missing rule body",
                level="error",
            )
            with self.state.locked():
                technique = self.state.techniques.get(technique_id)
                if technique:
                    technique.pending_approval = True
            return False

        deployed = self.splunk.create_saved_search(
            name=f"ARIA - {technique_id}: {technique_name}",
            query=rule,
            description=explanation,
        )

        if not deployed:
            self.state.log(
                "Orchestrator",
                f"Splunk deployment failed for {technique_id}",
                level="error",
            )
            with self.state.locked():
                technique = self.state.techniques.get(technique_id)
                if technique:
                    technique.pending_approval = True
            return False

        with self.state.locked():
            technique = self.state.techniques.get(technique_id)
            if not technique:
                return False

            previous_verdict = technique.verdict

            technique.approved = True
            technique.deployed = True
            technique.rejected = False

            # Immediate in-memory reconciliation so UI reflects deployment in realtime.
            technique.verdict = "COVERED"
            technique.enabled_rules = max(1, technique.enabled_rules + 1)
            technique.total_rules = max(
                technique.total_rules + 1, technique.enabled_rules
            )
            technique.enabled_percentage = round(
                (technique.enabled_rules / technique.total_rules) * 100, 1
            )

            if previous_verdict == "GAP":
                self.state.gap_count = max(0, self.state.gap_count - 1)
                self.state.covered_count += 1
            elif previous_verdict == "PARTIAL":
                self.state.partial_count = max(0, self.state.partial_count - 1)
                self.state.covered_count += 1

            self._recompute_coverage_score_locked()

            self.state.log(
                "Orchestrator",
                f"Rule deployed and approved for {technique_id} - {technique.technique_name}",
            )

            persisted = self.splunk.save_rule_memory(
                technique_id=technique.technique_id,
                technique_name=technique.technique_name,
                generated_rule=technique.generated_rule,
                rule_explanation=technique.rule_explanation,
                rule_confidence=technique.rule_confidence,
                pending_approval=technique.pending_approval,
                approved=technique.approved,
                rejected=technique.rejected,
                deployed=technique.deployed,
            )
            if not persisted:
                self.state.log(
                    "Orchestrator",
                    f"Warning: failed to persist rule memory for {technique_id}",
                    level="warning",
                )

        self._notify()
        return True

    def reject_rule(self, technique_id: str, reason: str = "") -> bool:
        """
        Reject a staged rule and clear it from the queue.
        The generated_rule is wiped so the Gap Agent can retry on the next run.
        Thread-safe - can be called from the API layer during a live run.
        Returns False if the technique does not exist or is not pending approval.
        """
        with self.state.locked():
            technique = self.state.techniques.get(technique_id)
            if not technique or not technique.pending_approval:
                return False

            technique.pending_approval = False
            technique.rejected = True
            technique.generated_rule = None
            technique.rule_explanation = None
            technique.rule_confidence = None

            message = f"Rule rejected for {technique_id}"
            if reason:
                message += f" - reason: {reason}"
            self.state.log("Orchestrator", message)

            persisted = self.splunk.save_rule_memory(
                technique_id=technique.technique_id,
                technique_name=technique.technique_name,
                generated_rule=technique.generated_rule,
                rule_explanation=technique.rule_explanation,
                rule_confidence=technique.rule_confidence,
                pending_approval=technique.pending_approval,
                approved=technique.approved,
                rejected=technique.rejected,
                deployed=technique.deployed,
            )
            if not persisted:
                self.state.log(
                    "Orchestrator",
                    f"Warning: failed to persist rule memory for {technique_id}",
                    level="warning",
                )

        self._notify()
        return True

    def get_summary(self) -> dict:
        """Lightweight snapshot for the WebSocket broadcast and /api/state."""
        return self.state.to_summary()

    def get_technique(self, technique_id: str) -> Optional[dict]:
        """Full detail for a single technique. Returns None if not found."""
        with self.state.locked():
            t = self.state.techniques.get(technique_id)
            return t.to_dict() if t else None

    def get_all_techniques(self) -> list[dict]:
        """All techniques as dicts - used by /api/techniques."""
        with self.state.locked():
            return [t.to_dict() for t in self.state.techniques.values()]

    def get_pending_approvals(self) -> list[dict]:
        """Techniques awaiting human approval - used by /api/pending."""
        with self.state.locked():
            return [
                t.to_dict()
                for t in self.state.techniques.values()
                if t.pending_approval
            ]

    def bootstrap_state_from_splunk(self) -> bool:
        """
        Startup baseline load: run Blue Agent once and hydrate persisted
        rule memory so UI has immediately useful state after server restart.
        """
        with self._lock:
            if self.is_running:
                return False
            self.state = ARIAState()

        try:
            result = self.blue.run()
            if "error" in result:
                self.state.log(
                    "Orchestrator",
                    f"Startup baseline load failed: {result['error']}",
                    level="error",
                )
                self.state.set_phase("error")
                return False

            self.state.update_from_blue(result["coverage_map"], result["score"])
            hydrated = self._hydrate_rule_memory_from_kv()
            self.state.set_phase("idle")
            self.state.log(
                "Orchestrator",
                f"Startup baseline ready - {self.state.total_techniques} techniques, hydrated {hydrated} persisted rules",
            )
            self._notify()
            return True

        except Exception as e:
            self.state.log(
                "Orchestrator",
                f"Startup baseline load failed: {e}",
                level="error",
            )
            self.state.set_phase("error")
            self._notify()
            return False

    def _run_blue(self):
        self.state.set_phase("auditing")
        self.state.log(
            "Orchestrator", "Starting Blue Agent - auditing Splunk coverage..."
        )
        self._notify()

        result = self.blue.run()

        if "error" in result:
            raise RuntimeError(f"Blue Agent failed: {result['error']}")

        self.state.update_from_blue(result["coverage_map"], result["score"])
        hydrated = self._hydrate_rule_memory_from_kv()
        self.state.log(
            "Orchestrator",
            f"Blue Agent complete - {self.state.gap_count} gaps detected, "
            f"score {self.state.coverage_score}%"
            + (f", hydrated {hydrated} persisted rules" if hydrated else ""),
        )
        self._notify()

    def _run_red(self):
        self.state.log(
            "Orchestrator", "Starting Red Agent - building attack profiles..."
        )
        self._notify()

        self.red.run(self.state)

        with self.state.locked():
            profiled = sum(
                1
                for t in self.state.techniques.values()
                if t.attack_profile is not None
            )
        self.state.log(
            "Orchestrator", f"Red Agent complete - {profiled} attack profiles generated"
        )
        self._notify()

    def _run_gap(self, gap_limit: int):
        self._preflight_gap_phase()

        self.state.log(
            "Orchestrator",
            f"Starting Gap Agent - generating SPL rules for up to {gap_limit} gaps...",
        )
        self._notify()

        self.gap_agent.run(self.state, limit=gap_limit)

        with self.state.locked():
            generated = sum(
                1
                for t in self.state.techniques.values()
                if t.generated_rule is not None
            )
        self.state.set_phase("awaiting_approval")
        self.state.log(
            "Orchestrator",
            f"Gap Agent complete - {generated} rules staged for approval",
        )
        self._notify()

    def _preflight_gap_phase(self):
        """
        Ensure Splunk session is valid before invoking expensive AI generation.
        This prevents burning model calls when Splunk auth/session has expired.
        """
        validation = self.splunk.validate_spl("search index=* | head 1")
        if validation.get("valid"):
            return

        error = str(validation.get("error") or "Unknown Splunk validation error")
        if hasattr(
            self.splunk, "is_session_error_message"
        ) and self.splunk.is_session_error_message(error):
            raise RuntimeError(
                "Splunk authentication/session failed before Gap Agent phase. "
                "Please reconnect Splunk and retry."
            )

        raise RuntimeError(
            f"Splunk preflight check failed before Gap Agent phase: {error}"
        )

    def _hydrate_rule_memory_from_kv(self) -> int:
        """
        Hydrate persisted rule lifecycle fields from Splunk KV store into
        the in-memory ARIA state after Blue coverage is rebuilt.
        Returns number of techniques hydrated.
        """
        records = self.splunk.get_rule_memory_map()
        if not isinstance(records, dict) or not records:
            return 0

        hydrated = 0
        with self.state.locked():
            for tid, row in records.items():
                technique = self.state.techniques.get(tid)
                if not technique:
                    continue

                technique.generated_rule = row.get("generated_rule")
                technique.rule_explanation = row.get("rule_explanation")
                technique.rule_confidence = row.get("rule_confidence")
                technique.pending_approval = bool(row.get("pending_approval", False))
                technique.approved = bool(row.get("approved", False))
                technique.rejected = bool(row.get("rejected", False))
                technique.deployed = bool(row.get("deployed", False))
                hydrated += 1

        return hydrated

    def _recompute_coverage_score_locked(self):
        """Recompute state.coverage_score. Caller must hold state lock."""
        total = self.state.total_techniques
        if total <= 0:
            self.state.coverage_score = 0.0
            return

        score = (
            (self.state.covered_count + (self.state.partial_count * 0.5)) / total
        ) * 100
        self.state.coverage_score = round(score, 1)

    def _notify(self):
        """
        Push state summary to the on_state_change callback.
        Errors in the callback never crash the pipeline.
        """
        if self.on_state_change:
            try:
                self.on_state_change(self.get_summary())
            except Exception:
                logging.exception("State change callback failed")
