"""Demo mode fixture loading and ARIAState hydration utilities."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from core.state import ARIAState, TechniqueState

DEFAULT_DEMO_PAYLOAD: dict[str, Any] = {
    "phase": "idle",
    "coverage_score": 42.5,
    "total_techniques": 6,
    "covered_count": 2,
    "partial_count": 1,
    "gap_count": 3,
    "coverage_before": 42.5,
    "coverage_after": 42.5,
    "gaps_identified": 3,
    "rules_generated": 2,
    "rules_approved": 0,
    "rules_deployed": 0,
    "generation_durations_sec": [2.4, 2.9],
    "techniques": {
        "T1008": {
            "technique_id": "T1008",
            "technique_name": "Fallback Channels",
            "verdict": "GAP",
            "tactics": ["command-and-control"],
            "total_rules": 0,
            "enabled_rules": 0,
            "enabled_percentage": 0.0,
            "description": "Adversaries use fallback channels to maintain C2.",
            "detection": "Monitor DNS and alternate protocol fallback patterns.",
            "generated_rule": "search index=dns sourcetype=bind query_length>60 | stats count by query",
            "rule_explanation": "Flags suspicious long DNS query patterns used as fallback C2.",
            "rule_confidence": 0.8,
            "rule_provider": "splunk_ai_assistant_mcp",
            "rule_provider_trace": ["saia_generate_spl", "saia_optimize_spl"],
            "pending_approval": True,
            "approved": False,
            "rejected": False,
            "deployed": False,
        },
        "T1566": {
            "technique_id": "T1566",
            "technique_name": "Phishing",
            "verdict": "GAP",
            "tactics": ["initial-access"],
            "total_rules": 0,
            "enabled_rules": 0,
            "enabled_percentage": 0.0,
            "description": "Adversaries send phishing content.",
            "detection": "Watch for unusual sender/reply behaviors.",
            "generated_rule": "search index=email (subject=*invoice* OR subject=*payment*) | stats count by sender",
            "rule_explanation": "Highlights suspicious invoice-themed phishing bursts.",
            "rule_confidence": 0.76,
            "rule_provider": "gemini",
            "rule_provider_trace": ["gemini_generate_content"],
            "pending_approval": True,
            "approved": False,
            "rejected": False,
            "deployed": False,
        },
        "T1059": {
            "technique_id": "T1059",
            "technique_name": "Command and Scripting Interpreter",
            "verdict": "COVERED",
            "tactics": ["execution"],
            "total_rules": 4,
            "enabled_rules": 3,
            "enabled_percentage": 75.0,
            "pending_approval": False,
            "approved": False,
            "rejected": False,
            "deployed": False,
        },
    },
    "reasoning_log": [
        {
            "timestamp": "2026-01-01T00:00:00+00:00",
            "agent": "Orchestrator",
            "level": "info",
            "message": "Demo baseline loaded.",
        }
    ],
}


def load_demo_payload(path: str) -> dict[str, Any]:
    fixture_path = Path(path)
    if not fixture_path.exists():
        return DEFAULT_DEMO_PAYLOAD.copy()

    with fixture_path.open("r", encoding="utf-8") as f:
        parsed = json.load(f)

    if not isinstance(parsed, dict):
        return DEFAULT_DEMO_PAYLOAD.copy()

    merged = DEFAULT_DEMO_PAYLOAD.copy()
    merged.update(parsed)
    return merged


def state_from_demo_payload(payload: dict[str, Any]) -> ARIAState:
    state = ARIAState()

    with state.locked():
        state.phase = str(payload.get("phase", "idle"))
        state.coverage_score = float(payload.get("coverage_score", 0.0))
        state.total_techniques = int(payload.get("total_techniques", 0))
        state.covered_count = int(payload.get("covered_count", 0))
        state.partial_count = int(payload.get("partial_count", 0))
        state.gap_count = int(payload.get("gap_count", 0))

        state.coverage_before = float(
            payload.get("coverage_before", state.coverage_score)
        )
        state.coverage_after = float(
            payload.get("coverage_after", state.coverage_score)
        )
        state.gaps_identified = int(payload.get("gaps_identified", state.gap_count))
        state.rules_generated = int(payload.get("rules_generated", 0))
        state.rules_approved = int(payload.get("rules_approved", 0))
        state.rules_deployed = int(payload.get("rules_deployed", 0))

        raw_durations = payload.get("generation_durations_sec", [])
        if isinstance(raw_durations, list):
            state.generation_durations_sec = [
                float(item) for item in raw_durations if isinstance(item, (int, float))
            ]

        state.reasoning_log = list(payload.get("reasoning_log", []))
        state.errors = [e for e in state.reasoning_log if e.get("level") == "error"]

        state.techniques.clear()
        techniques = payload.get("techniques", {})
        if isinstance(techniques, dict):
            for tid, raw in techniques.items():
                if not isinstance(raw, dict):
                    continue

                technique = TechniqueState(
                    technique_id=str(raw.get("technique_id", tid)).upper(),
                    technique_name=str(raw.get("technique_name", tid)),
                    verdict=str(raw.get("verdict", "GAP")),
                    tactics=list(raw.get("tactics", [])),
                    total_rules=int(raw.get("total_rules", 0)),
                    enabled_rules=int(raw.get("enabled_rules", 0)),
                    enabled_percentage=float(raw.get("enabled_percentage", 0.0)),
                    description=str(raw.get("description", "")),
                    detection=str(raw.get("detection", "")),
                )

                technique.attack_profile = raw.get("attack_profile")
                technique.generated_rule = raw.get("generated_rule")
                technique.rule_explanation = raw.get("rule_explanation")
                technique.rule_confidence = raw.get("rule_confidence")
                technique.rule_provider = raw.get("rule_provider")

                trace = raw.get("rule_provider_trace", [])
                if isinstance(trace, list):
                    technique.rule_provider_trace = [str(item) for item in trace]

                technique.pending_approval = bool(raw.get("pending_approval", False))
                technique.approved = bool(raw.get("approved", False))
                technique.rejected = bool(raw.get("rejected", False))
                technique.deployed = bool(raw.get("deployed", False))

                state.techniques[technique.technique_id] = technique

    return state
