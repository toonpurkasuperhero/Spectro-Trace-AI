import time
import asyncio
import json
import logging
from typing import Dict, Any, Optional, AsyncGenerator
from api.core.schema import JobResult, Finding

logger = logging.getLogger(__name__)

# In-memory job repository (backed by SQLite/Postgres in full deployment)
_jobs: Dict[str, JobResult] = {}
# SSE subscribers per job
_subscribers: Dict[str, list[asyncio.Queue]] = {}
# Heartbeat timestamps
_heartbeats: Dict[str, float] = {}

STAGE_TIMEOUTS = {
    "queued": 60,
    "encoding": 60,
    "measuring": 90,
    "vision": 60,
    "publishing": 60
}

def create_or_get_job(job_id: str, module: str, cld_public_id: str) -> JobResult:
    if job_id in _jobs:
        return _jobs[job_id]

    job = JobResult(
        job_id=job_id,
        module=module,
        status="queued",
        stage="queued",
        assets={"raw": {"public_id": cld_public_id}}
    )
    _jobs[job_id] = job
    _heartbeats[job_id] = time.time()
    return job

def get_job(job_id: str) -> Optional[JobResult]:
    return _jobs.get(job_id)

def list_jobs(limit: int = 50) -> list[JobResult]:
    return list(_jobs.values())[-limit:]

def update_job_stage(job_id: str, stage: str, status: Optional[str] = None):
    job = _jobs.get(job_id)
    if not job:
        return

    job.stage = stage
    job.status = status or stage
    _heartbeats[job_id] = time.time()

    # Broadcast stage change to SSE clients
    notify_job_update(job_id, {"stage": stage, "status": job.status})

def finish_job(
    job_id: str,
    status: str = "done",
    summary: str = "",
    error: Optional[str] = None
):
    job = _jobs.get(job_id)
    if not job:
        return

    job.status = status
    job.stage = "finished"
    job.summary = summary
    job.error = error
    _heartbeats[job_id] = time.time()

    notify_job_update(job_id, {
        "status": status,
        "stage": "finished",
        "summary": summary,
        "error": error,
        "findings_count": len(job.findings),
        "risk_level": job.risk_level,
        "risk_score": job.risk_score
    })

def notify_job_update(job_id: str, data: Dict[str, Any]):
    if job_id in _subscribers:
        payload = json.dumps(data)
        for q in _subscribers[job_id]:
            try:
                q.put_nowait(payload)
            except asyncio.QueueFull:
                pass

async def job_event_generator(job_id: str) -> AsyncGenerator[str, None]:
    """
    Yields Server-Sent Events (SSE) for job lifecycle events.
    """
    queue: asyncio.Queue = asyncio.Queue(maxsize=50)
    if job_id not in _subscribers:
        _subscribers[job_id] = []
    _subscribers[job_id].append(queue)

    # Yield current state immediately
    job = get_job(job_id)
    if job:
        yield f"data: {json.dumps({'stage': job.stage, 'status': job.status, 'job_id': job.job_id})}\n\n"

    try:
        while True:
            # Send heartbeat keepalive or wait for update
            try:
                msg = await asyncio.wait_for(queue.get(), timeout=15.0)
                yield f"data: {msg}\n\n"
                data = json.loads(msg)
                if data.get("status") in ("done", "done_partial", "done_no_vision", "failed"):
                    break
            except asyncio.TimeoutError:
                # SSE ping comment
                yield ": ping\n\n"
    finally:
        if job_id in _subscribers and queue in _subscribers[job_id]:
            _subscribers[job_id].remove(queue)

def check_stuck_jobs(timeout_seconds: int = 120):
    now = time.time()
    for job_id, job in list(_jobs.items()):
        if job.status not in ("done", "done_partial", "done_no_vision", "failed"):
            last_hb = _heartbeats.get(job_id, now)
            stage_limit = STAGE_TIMEOUTS.get(job.stage, timeout_seconds)
            if now - last_hb > stage_limit:
                logger.warning(f"Job {job_id} timed out in stage {job.stage} after {int(now - last_hb)}s.")
                job.status = "failed"
                job.error = f"Stage {job.stage} timed out."
                notify_job_update(job_id, {"status": "failed", "error": job.error})
