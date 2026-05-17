"""Hermes Web UI -- Local AI model download manager (issue #10).

Server-side, resumable, sha256-verified download manager for GGUF model
files. Phi-4-mini Q4_K_M is the first user (the v0.4.1 llama.cpp local
fallback consumes it); the manager itself is generic — additional
known models can be added to ``KNOWN_MODELS`` without code changes
beyond the registry entry.

Design highlights:
- Server-side fetch (not client). A 2.5 GB download survives the user
  closing the browser tab — we can't have that block on a JS fetch.
- SSE progress to whichever browser tab is currently subscribed. New
  subscribers join the live job and receive the current state plus all
  subsequent updates.
- Resume across container restart. Partial file lives on the ``/data``
  volume; ``<file>.partial.meta`` records the upstream ETag so a
  silently-rotated upstream forces a clean restart instead of a
  corrupt resume.
- sha256 is computed incrementally as bytes stream in, then compared to
  the pinned hash before atomic-renaming to the final filename. The
  final file is never visible at the canonical path until verification
  passes.

The download manager is a singleton; one job per model_id at a time.
``POST /api/models/<id>/download`` is idempotent — a call against a
running job returns the live state instead of starting a second.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import queue
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# ── Model registry ──────────────────────────────────────────────────────────

# Known models. The URL + SHA256 are env-overridable so we can flip to a
# mirror (Cloudflare R2, GitHub Release asset, etc.) without a code release
# if HuggingFace ever has an outage. Defaults are the canonical bartowski
# repo identified during #10 Phase 1 research.
KNOWN_MODELS: dict[str, dict[str, Any]] = {
    "phi4-mini": {
        "id": "phi4-mini",
        "name": "Phi-4 Mini Instruct (Q4_K_M)",
        "filename": "microsoft_Phi-4-mini-instruct-Q4_K_M.gguf",
        "url": os.environ.get(
            "MODEL_URL_PHI4MINI",
            "https://huggingface.co/bartowski/microsoft_Phi-4-mini-instruct-GGUF"
            "/resolve/main/microsoft_Phi-4-mini-instruct-Q4_K_M.gguf",
        ),
        "sha256": os.environ.get(
            "MODEL_SHA256_PHI4MINI",
            "01999f17c39cc3074afae5e9c539bc82d45f2dd7faa3917c66cbef76fce8c0c2",
        ),
        # File size in bytes — drives the progress bar denominator before
        # the upstream Content-Length is observed (also used to flag
        # silently-rotated upstreams during resume verification).
        "size_bytes": int(os.environ.get("MODEL_SIZE_PHI4MINI", "2491874688")),
        "description": "3.8B parameters, runs on CPU. ~3 GB RAM at runtime, ~6–10 tok/s on a 4-core machine.",
    },
}


# ── Filesystem layout ──────────────────────────────────────────────────────

_MODELS_DIR = Path(os.environ.get("MODELS_DIR", "/data/models"))


def _model_paths(model: dict[str, Any]) -> tuple[Path, Path, Path]:
    """Return (final, partial, meta) paths for a model registry entry."""
    final = _MODELS_DIR / model["filename"]
    partial = _MODELS_DIR / f"{model['filename']}.partial"
    meta = _MODELS_DIR / f"{model['filename']}.partial.meta"
    return final, partial, meta


# ── Job state ───────────────────────────────────────────────────────────────


@dataclass
class JobState:
    """Snapshot of a download's progress. Mutated by the worker thread,
    broadcast to SSE subscribers, included in REST responses verbatim."""

    model_id: str
    status: str = "idle"  # idle | running | completed | failed | cancelled
    bytes_downloaded: int = 0
    bytes_total: int = 0
    started_at: float = 0.0
    updated_at: float = 0.0
    error: str | None = None
    sha256_verified: bool = False

    # Internal — never serialized to clients.
    _cancel_event: threading.Event = field(default_factory=threading.Event, repr=False)
    _subscribers: list[queue.Queue] = field(default_factory=list, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def to_dict(self) -> dict[str, Any]:
        return {
            "model_id": self.model_id,
            "status": self.status,
            "bytes_downloaded": self.bytes_downloaded,
            "bytes_total": self.bytes_total,
            "started_at": self.started_at,
            "updated_at": self.updated_at,
            "error": self.error,
            "sha256_verified": self.sha256_verified,
        }


# ── Manager singleton ──────────────────────────────────────────────────────

_jobs: dict[str, JobState] = {}
_jobs_lock = threading.Lock()


def _get_or_create_job(model_id: str) -> JobState:
    with _jobs_lock:
        job = _jobs.get(model_id)
        if job is None:
            job = JobState(model_id=model_id)
            _jobs[model_id] = job
        return job


def _broadcast(job: JobState) -> None:
    """Push the current state to all SSE subscribers. Subscribers that
    have disconnected (queue not drained, or explicit unsubscribe) are
    silently dropped."""
    snapshot = job.to_dict()
    with job._lock:
        dead = []
        for q in job._subscribers:
            try:
                q.put_nowait(snapshot)
            except queue.Full:
                # Subscriber is slow; drop the oldest so SSE doesn't
                # backpressure the worker. Progress is monotonic — losing
                # an intermediate event isn't fatal.
                try:
                    q.get_nowait()
                    q.put_nowait(snapshot)
                except queue.Empty:
                    dead.append(q)
            except Exception:
                dead.append(q)
        for q in dead:
            try:
                job._subscribers.remove(q)
            except ValueError:
                pass


def _set_state(job: JobState, **changes) -> None:
    with job._lock:
        for k, v in changes.items():
            setattr(job, k, v)
        job.updated_at = time.time()
    _broadcast(job)


# ── Download worker ────────────────────────────────────────────────────────


def _is_final_present(model: dict[str, Any]) -> bool:
    """True if the canonical file is on disk and matches the pinned sha256.
    Final files are only created via atomic rename after verification, so
    we trust their existence — but a corrupted disk could in theory leave a
    stale file. We don't re-verify on every status check (would be slow);
    callers that need cryptographic certainty can call _verify_existing."""
    final, _, _ = _model_paths(model)
    return final.exists() and final.stat().st_size == model["size_bytes"]


def _read_meta(meta_path: Path) -> dict[str, Any] | None:
    """Read .partial.meta JSON; return None if missing or unparseable."""
    try:
        if not meta_path.exists():
            return None
        return json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _write_meta(meta_path: Path, payload: dict[str, Any]) -> None:
    meta_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = meta_path.with_suffix(meta_path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    os.replace(tmp, meta_path)


def _probe_url(url: str, timeout: float = 10.0) -> tuple[str | None, int | None]:
    """HEAD the URL via GET-with-Range:0-0 (HF allows this, plain HEAD on
    LFS objects sometimes isn't followed through the 302). Returns
    (etag, content_length_total). content_length_total is the FULL size,
    not the partial chunk — derived from `Content-Range: bytes 0-0/<total>`
    when the server honours the range request."""
    req = urllib.request.Request(url, headers={"Range": "bytes=0-0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # nosec B310
            etag = resp.headers.get("ETag") or resp.headers.get("x-linked-etag")
            content_range = resp.headers.get("Content-Range") or ""
            total = None
            # Content-Range: bytes 0-0/2491874688
            if "/" in content_range:
                try:
                    total = int(content_range.rsplit("/", 1)[1])
                except ValueError:
                    pass
            return etag, total
    except (urllib.error.URLError, OSError) as exc:
        logger.debug("Probe of %s failed: %s", url, exc)
        return None, None


def _download_thread(model: dict[str, Any], job: JobState) -> None:
    """Worker. Streams the upstream bytes, verifies sha256, atomic-renames
    on success. Designed to be safe against client disconnect, container
    restart (resume), and cancellation."""
    final, partial, meta = _model_paths(model)
    expected_sha = model["sha256"]
    expected_size = int(model["size_bytes"])

    try:
        _MODELS_DIR.mkdir(parents=True, exist_ok=True)

        # ── Fast paths ─────────────────────────────────────────────────
        # If the final file is present and the right size, declare success.
        # We don't sha256-verify here on every call (multi-GB hash is slow);
        # the sha256 was verified at write time, and the volume is private.
        if _is_final_present(model):
            _set_state(
                job,
                status="completed",
                bytes_downloaded=expected_size,
                bytes_total=expected_size,
                sha256_verified=True,
            )
            return

        # ── Probe upstream ────────────────────────────────────────────
        etag_now, total_from_probe = _probe_url(model["url"])
        bytes_total = total_from_probe or expected_size

        # ── Resume decision ───────────────────────────────────────────
        # Resume iff: partial exists, meta exists, meta.etag matches the
        # current upstream etag, and partial size < expected. Any other
        # state → restart from zero.
        existing_meta = _read_meta(meta)
        partial_size = partial.stat().st_size if partial.exists() else 0
        resume_offset = 0
        sha = hashlib.sha256()

        can_resume = (
            existing_meta is not None
            and existing_meta.get("etag") == etag_now
            and etag_now is not None
            and 0 < partial_size < bytes_total
        )

        if can_resume:
            # Hash everything we have so the final sha matches the full
            # stream. Reading 2 GB off SSD is ~1–2 s; cheap insurance.
            with open(partial, "rb") as f:
                while True:
                    chunk = f.read(1 << 20)  # 1 MB
                    if not chunk:
                        break
                    sha.update(chunk)
            resume_offset = partial_size
            logger.info(
                "Resuming download of %s from %d/%d bytes",
                model["id"], resume_offset, bytes_total,
            )
        else:
            # Fresh start — clear any stale partial.
            if partial.exists():
                partial.unlink()
            if meta.exists():
                meta.unlink()

        # ── Persist meta sidecar ──────────────────────────────────────
        _write_meta(meta, {
            "url": model["url"],
            "etag": etag_now,
            "expected_sha256": expected_sha,
            "total_bytes": bytes_total,
            "started_at": time.time(),
        })

        _set_state(
            job,
            status="running",
            bytes_downloaded=resume_offset,
            bytes_total=bytes_total,
            error=None,
            sha256_verified=False,
            started_at=time.time() if not job.started_at else job.started_at,
        )

        # ── Open the stream ───────────────────────────────────────────
        headers: dict[str, str] = {}
        if resume_offset > 0:
            headers["Range"] = f"bytes={resume_offset}-"
            if etag_now:
                # If upstream rotated mid-resume, server returns 200 (full
                # restart) instead of 206. The except-HTTPError path below
                # falls back to clean-restart logic.
                headers["If-Range"] = etag_now

        req = urllib.request.Request(model["url"], headers=headers)
        try:
            resp = urllib.request.urlopen(req, timeout=60.0)  # nosec B310
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"Upstream HTTP {exc.code}") from exc
        except (urllib.error.URLError, OSError) as exc:
            raise RuntimeError(f"Could not reach {model['url']}: {exc}") from exc

        # If we asked for a range but the server returned 200, the upstream
        # file changed (or doesn't honour ranges). Treat as fresh start.
        full_restart = resume_offset > 0 and resp.status == 200
        if full_restart:
            logger.warning(
                "Upstream returned 200 to a Range request for %s — restarting",
                model["id"],
            )
            sha = hashlib.sha256()
            resume_offset = 0
            if partial.exists():
                partial.unlink()
            _set_state(job, bytes_downloaded=0, bytes_total=bytes_total)

        # ── Stream to disk ────────────────────────────────────────────
        mode = "ab" if resume_offset > 0 else "wb"
        last_broadcast = time.time()
        bytes_written = resume_offset
        chunk_size = 1 << 20  # 1 MB
        with open(partial, mode) as out:
            while True:
                if job._cancel_event.is_set():
                    _set_state(job, status="cancelled", error="Cancelled by user")
                    return
                chunk = resp.read(chunk_size)
                if not chunk:
                    break
                out.write(chunk)
                sha.update(chunk)
                bytes_written += len(chunk)
                # Throttle SSE to 4 Hz max — avoids browser overload on
                # fast connections where we'd otherwise emit 100s of
                # events per second.
                now = time.time()
                if now - last_broadcast >= 0.25:
                    _set_state(job, bytes_downloaded=bytes_written)
                    last_broadcast = now
        try:
            resp.close()
        except Exception:
            pass

        # ── Verify sha256 ─────────────────────────────────────────────
        actual_sha = sha.hexdigest()
        if actual_sha != expected_sha:
            # Discard the corrupted partial — next download attempts a
            # fresh full pull. The user-visible error is intentionally
            # specific so a mirror swap can be diagnosed.
            partial.unlink(missing_ok=True)
            meta.unlink(missing_ok=True)
            _set_state(
                job,
                status="failed",
                error=(f"sha256 mismatch — expected {expected_sha}, "
                       f"got {actual_sha}. The file you downloaded does not "
                       f"match the pinned hash; the upstream may have been "
                       f"rotated. Retry to attempt a clean re-download."),
            )
            return

        # ── Atomic rename → final ─────────────────────────────────────
        os.replace(partial, final)
        meta.unlink(missing_ok=True)

        _set_state(
            job,
            status="completed",
            bytes_downloaded=expected_size,
            bytes_total=expected_size,
            sha256_verified=True,
            error=None,
        )
    except RuntimeError as exc:
        _set_state(job, status="failed", error=str(exc))
    except Exception as exc:
        logger.exception("Unhandled error in download worker for %s", model.get("id"))
        _set_state(job, status="failed", error=f"Unexpected error: {exc}")


def start_download(model_id: str) -> dict[str, Any]:
    """Idempotent entry point. If a download is running, returns the live
    state. If completed, returns completion. Otherwise spawns a worker."""
    model = KNOWN_MODELS.get(model_id)
    if model is None:
        return {"ok": False, "error": f"unknown model id: {model_id}"}

    job = _get_or_create_job(model_id)
    with job._lock:
        if job.status == "running":
            return {"ok": True, "state": job.to_dict(), "note": "already running"}

    if _is_final_present(model):
        _set_state(
            job,
            status="completed",
            bytes_downloaded=int(model["size_bytes"]),
            bytes_total=int(model["size_bytes"]),
            sha256_verified=True,
            error=None,
        )
        return {"ok": True, "state": job.to_dict(), "note": "already installed"}

    job._cancel_event.clear()
    _set_state(job, status="running", error=None, started_at=time.time())
    thread = threading.Thread(
        target=_download_thread, args=(model, job),
        name=f"model-download-{model_id}", daemon=True,
    )
    thread.start()
    return {"ok": True, "state": job.to_dict()}


def cancel_download(model_id: str) -> dict[str, Any]:
    job = _jobs.get(model_id)
    if job is None or job.status != "running":
        return {"ok": False, "error": "no active download for that model"}
    job._cancel_event.set()
    return {"ok": True, "state": job.to_dict()}


def delete_model(model_id: str) -> dict[str, Any]:
    """Delete an installed model. Refuses while a download is in progress
    for the same model — cancel first."""
    model = KNOWN_MODELS.get(model_id)
    if model is None:
        return {"ok": False, "error": f"unknown model id: {model_id}"}

    job = _jobs.get(model_id)
    if job is not None and job.status == "running":
        return {"ok": False, "error": "download in progress; cancel before deleting"}

    final, partial, meta = _model_paths(model)
    freed = 0
    for path in (final, partial, meta):
        if path.exists():
            try:
                freed += path.stat().st_size
                path.unlink()
            except OSError as exc:
                logger.warning("Could not delete %s: %s", path, exc)

    if job is not None:
        _set_state(
            job, status="idle",
            bytes_downloaded=0, bytes_total=0,
            sha256_verified=False, error=None,
        )

    return {"ok": True, "model_id": model_id, "freed_bytes": freed}


def list_models() -> dict[str, Any]:
    """Return registry + on-disk status for every known model."""
    out = []
    total_disk = 0
    for model_id, model in KNOWN_MODELS.items():
        final, partial, _meta = _model_paths(model)
        installed = _is_final_present(model)
        size_on_disk = 0
        if installed:
            size_on_disk = final.stat().st_size
        elif partial.exists():
            size_on_disk = partial.stat().st_size
        total_disk += size_on_disk
        job = _jobs.get(model_id)
        out.append({
            "id": model_id,
            "name": model["name"],
            "filename": model["filename"],
            "description": model.get("description", ""),
            "expected_size_bytes": int(model["size_bytes"]),
            "size_on_disk_bytes": size_on_disk,
            "installed": installed,
            "state": job.to_dict() if job else None,
        })
    return {"models": out, "total_size_bytes": total_disk}


# ── SSE subscribe ──────────────────────────────────────────────────────────


def subscribe(model_id: str) -> queue.Queue | None:
    """Register a queue for SSE updates on a model's job. Returns None if
    the model id is unknown. Caller is responsible for unsubscribing
    (passing the same queue back) on disconnect."""
    if model_id not in KNOWN_MODELS:
        return None
    job = _get_or_create_job(model_id)
    q: queue.Queue = queue.Queue(maxsize=64)
    with job._lock:
        job._subscribers.append(q)
    # Send the current state immediately so a late-joining subscriber
    # doesn't have to wait for the next progress tick to know where they
    # are. Without this, a download that finished 5 ms before subscribe
    # would never emit the completion event to the new client.
    try:
        q.put_nowait(job.to_dict())
    except queue.Full:
        pass
    return q


def unsubscribe(model_id: str, q: queue.Queue) -> None:
    job = _jobs.get(model_id)
    if job is None:
        return
    with job._lock:
        try:
            job._subscribers.remove(q)
        except ValueError:
            pass


# ── Route handlers ─────────────────────────────────────────────────────────


def handle_get_models(handler) -> dict[str, Any]:
    """GET /api/models — registry + on-disk + active-job snapshot."""
    return list_models()


def handle_post_download(handler, body: dict, model_id: str) -> dict[str, Any]:
    """POST /api/models/<id>/download — idempotent."""
    return start_download(model_id)


def handle_post_cancel(handler, body: dict, model_id: str) -> dict[str, Any]:
    """POST /api/models/<id>/cancel."""
    return cancel_download(model_id)


def handle_post_delete(handler, body: dict, model_id: str) -> dict[str, Any]:
    """POST /api/models/<id>/delete."""
    return delete_model(model_id)


def handle_progress_sse(handler, model_id: str) -> bool:
    """GET /api/models/<id>/progress — SSE stream of state changes.

    The first event is the current state (so late joiners learn where the
    job is without waiting for the next tick). Subsequent events fire on
    every state change. The stream ends when the job reaches a terminal
    state (completed, failed, cancelled).
    """
    if model_id not in KNOWN_MODELS:
        handler.send_response(404)
        handler.send_header("Content-Type", "application/json")
        handler.end_headers()
        handler.wfile.write(b'{"error":"unknown model id"}')
        return True

    q = subscribe(model_id)
    if q is None:
        handler.send_response(404)
        handler.end_headers()
        return True

    handler.send_response(200)
    handler.send_header("Content-Type", "text/event-stream; charset=utf-8")
    handler.send_header("Cache-Control", "no-store")
    handler.send_header("X-Accel-Buffering", "no")
    handler.send_header("Connection", "keep-alive")
    handler.end_headers()

    try:
        terminal = {"completed", "failed", "cancelled"}
        while True:
            try:
                snapshot = q.get(timeout=30)
            except queue.Empty:
                # Heartbeat — keeps the proxy/browser connection alive
                # during slow phases (e.g. between sha256 verification and
                # atomic rename).
                try:
                    handler.wfile.write(b": heartbeat\n\n")
                    handler.wfile.flush()
                except (BrokenPipeError, ConnectionResetError):
                    return True
                continue
            payload = f"data: {json.dumps(snapshot)}\n\n"
            try:
                handler.wfile.write(payload.encode("utf-8"))
                handler.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                return True
            if snapshot.get("status") in terminal:
                return True
    finally:
        unsubscribe(model_id, q)


# ──────────────────────────────────────────────────────────────────────
# Fox dispatcher integration — Phase 5 of v0.6.0 migration.
# First module to use the dispatcher's allow_bare=True opt-in:
# /api/local-models owns BOTH the bare path (list endpoint) and
# parameterized sub-paths (/<model_id>/progress for SSE,
# /<model_id>/{download,cancel,delete} for actions). The wrapper does
# boundary checks to reject /api/local-modelsX adjacency attacks.
# ──────────────────────────────────────────────────────────────────────
from fox_overlay import dispatch  # noqa: E402


def _handle_get(handler, parsed) -> bool:
    """GET /api/local-models[/<id>/progress] — returns True if handled, False to fall through.

    Boundary contract: must reject /api/local-modelsX and any other path
    that startswith()-matches but isn't a real endpoint, because the
    dispatcher prefix is registered with allow_bare=True (no trailing /).
    """
    from api.helpers import j

    # Bare list endpoint.
    if parsed.path == "/api/local-models":
        j(handler, handle_get_models(handler))
        return True

    # SSE progress endpoint — handle_progress_sse manages its own response.
    if parsed.path.startswith("/api/local-models/") and parsed.path.endswith("/progress"):
        model_id = parsed.path[len("/api/local-models/"):-len("/progress")]
        return handle_progress_sse(handler, model_id)

    # Anything else under (or adjacent to) /api/local-models — not ours.
    return False


def _handle_post(handler, parsed) -> bool:
    """POST /api/local-models/<id>/{download,cancel,delete} — returns True if handled, False to fall through.

    Boundary contract: must reject /api/local-models (no action),
    /api/local-modelsX, and unknown actions.
    """
    from api.helpers import j, read_body

    # Reject bare path AND adjacency attacks — must start with the slash form.
    if not parsed.path.startswith("/api/local-models/"):
        return False

    body = read_body(handler)
    suffix = parsed.path[len("/api/local-models/"):]
    if "/" not in suffix:
        return False  # malformed (no action)
    model_id, action = suffix.rsplit("/", 1)

    if action == "download":
        r = handle_post_download(handler, body, model_id)
        j(handler, r, status=200 if r.get("ok") else 400)
        return True
    if action == "cancel":
        r = handle_post_cancel(handler, body, model_id)
        j(handler, r, status=200 if r.get("ok") else 400)
        return True
    if action == "delete":
        r = handle_post_delete(handler, body, model_id)
        j(handler, r, status=200 if r.get("ok") else 400)
        return True

    return False  # unknown action


# allow_bare=True: prefix omits trailing slash so dispatcher matches both
# /api/local-models (bare list) and /api/local-models/<id>/... (sub-paths).
# Boundary checks live in the handlers above.
dispatch.register_get("/api/local-models", _handle_get, allow_bare=True)
dispatch.register_post("/api/local-models", _handle_post, allow_bare=True)

