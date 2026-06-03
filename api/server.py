"""FastAPI server for ARIA state, approvals, and WebSocket updates."""

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Optional, Set

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from agents.gap_agent import GapAgent
from agents.orchestrator import Orchestrator
from core.mitre_loader import MitreLoader
from core.splunk_client import SplunkClient

load_dotenv()

_orchestrator: Optional[Orchestrator] = None
_ws_clients: Set[WebSocket] = set()
_broadcast_task: Optional[asyncio.Task] = None


async def _broadcast_loop():
    while True:
        try:
            if _orchestrator and _ws_clients:
                payload = _orchestrator.get_summary()
                dead = set()

                for ws in list(_ws_clients):
                    try:
                        await ws.send_json(payload)
                    except Exception:
                        dead.add(ws)

                _ws_clients.difference_update(dead)
        except Exception:
            logging.exception("Broadcast loop tick failed")

        await asyncio.sleep(0.5)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _orchestrator, _broadcast_task

    splunk = SplunkClient()
    connected = splunk.connect()
    if not connected:
        raise RuntimeError(
            "Splunk connection failed. Ensure Splunk is running on localhost:8089."
        )

    mitre = MitreLoader()
    gap_agent = GapAgent(splunk_client=splunk)

    _orchestrator = Orchestrator(
        splunk_client=splunk,
        gap_agent=gap_agent,
        mitre_loader=mitre,
    )

    _broadcast_task = asyncio.create_task(_broadcast_loop())
    print("ARIA API started. Splunk connected, orchestrator ready.")

    yield

    if _broadcast_task:
        _broadcast_task.cancel()
        try:
            await _broadcast_task
        except asyncio.CancelledError:
            pass


app = FastAPI(
    title="ARIA - Autonomous Red-Blue Intelligence Agent",
    description="Backend API for the ARIA security coverage platform.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class RunRequest(BaseModel):
    gap_limit: int = 10


class RejectRequest(BaseModel):
    reason: str = ""


def _require_orchestrator() -> Orchestrator:
    """Return the initialized orchestrator or fail fast."""
    if _orchestrator is None:
        raise HTTPException(status_code=503, detail="Orchestrator not initialised.")
    return _orchestrator


@app.get("/api/health")
async def health():
    """health and run status."""
    orch = _require_orchestrator()
    summary = orch.get_summary()
    return {
        "status": "ok",
        "is_running": orch.is_running,
        "phase": summary["phase"],
    }


@app.get("/api/state")
async def get_state():
    return _require_orchestrator().get_summary()


@app.get("/api/techniques")
async def get_techniques(verdict: Optional[str] = None):
    orch = _require_orchestrator()
    techniques = orch.get_all_techniques()

    if verdict:
        verdict = verdict.upper()
        techniques = [t for t in techniques if t["verdict"] == verdict]

    return {"techniques": techniques, "total": len(techniques)}


@app.get("/api/techniques/{technique_id}")
async def get_technique(technique_id: str):
    orch = _require_orchestrator()
    t = orch.get_technique(technique_id.upper())

    if not t:
        raise HTTPException(
            status_code=404,
            detail=f"Technique {technique_id} not found in current run.",
        )
    return t


@app.get("/api/pending")
async def get_pending():
    orch = _require_orchestrator()
    pending = orch.get_pending_approvals()
    return {"pending": pending, "count": len(pending)}


@app.post("/api/run")
async def start_run(body: RunRequest):
    """Run the pipeline in a background thread."""
    orch = _require_orchestrator()

    if orch.is_running:
        raise HTTPException(
            status_code=409,
            detail="A run is already in progress. Wait for it to complete.",
        )

    loop = asyncio.get_running_loop()
    loop.run_in_executor(None, orch.run, body.gap_limit)

    return {"status": "started", "gap_limit": body.gap_limit}


@app.post("/api/approve/{technique_id}")
async def approve_rule(technique_id: str):
    orch = _require_orchestrator()
    normalized_id = technique_id.upper()

    success = orch.approve_rule(normalized_id)
    if success:
        return {"status": "approved", "technique_id": normalized_id}

    # if still pending after an attempted approval, deployment likely failed(e.g., Splunk rejected the saved search payload).
    t = orch.get_technique(normalized_id)
    if t and t.get("pending_approval"):
        raise HTTPException(
            status_code=502,
            detail=f"Failed to deploy rule for {normalized_id} to Splunk.",
        )

    raise HTTPException(
        status_code=404,
        detail=f"No pending rule found for {normalized_id}.",
    )


@app.post("/api/reject/{technique_id}")
async def reject_rule(technique_id: str, body: RejectRequest):
    orch = _require_orchestrator()
    success = orch.reject_rule(technique_id.upper(), body.reason)

    if not success:
        raise HTTPException(
            status_code=404, detail=f"No pending rule found for {technique_id}."
        )

    return {"status": "rejected", "technique_id": technique_id.upper()}


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """Stream state snapshots to the client."""
    await websocket.accept()
    _ws_clients.add(websocket)

    try:
        if _orchestrator:
            await websocket.send_json(_orchestrator.get_summary())

        while True:
            await websocket.receive_text()

    except WebSocketDisconnect:
        pass
    finally:
        _ws_clients.discard(websocket)
