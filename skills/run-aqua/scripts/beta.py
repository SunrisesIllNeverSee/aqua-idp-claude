"""Local beta diagnostics with optional, content-free HTTPS delivery."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import traceback
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen

VERSION = "0.1.15"


def _stamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _settings(w: Path) -> tuple[bool, str]:
    path = w / "Beta Reports/Settings.json"
    try:
        saved = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        saved = None
    if not isinstance(saved, dict):
        saved = {}
    if saved.get("enabled") is False:  # A saved opt-out wins over the per-command environment opt-in.
        return False, ""
    if os.environ.get("AQUA_BETA_REPORTING") == "1":
        return True, os.environ.get("AQUA_BETA_REPORT_URL", "")
    endpoint = saved.get("endpoint", "")
    return saved.get("enabled") is True and isinstance(endpoint, str), endpoint if isinstance(endpoint, str) else ""


def configure(w: Path, enabled: bool, endpoint: str = "") -> None:
    """Persist the user's explicit beta delivery choice in their own workspace."""
    if enabled:
        parsed = urlparse(endpoint)
        if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
            raise ValueError("Beta receiver must be a valid HTTPS URL without embedded credentials")
    path = w / "Beta Reports/Settings.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"enabled": enabled, "endpoint": endpoint if enabled else ""}, indent=2) + "\n", encoding="utf-8")


def _send(summary: dict[str, str], w: Path) -> str:
    enabled, endpoint = _settings(w)
    if not enabled:
        return "local_only"
    parsed = urlparse(endpoint)
    if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
        return "no_valid_https_endpoint"
    payload = json.dumps(summary, sort_keys=True).encode("utf-8")
    request = Request(endpoint, payload, {
        "Content-Type": "application/json", "User-Agent": f"AQUA-beta/{VERSION}",
    }, method="POST")
    try:
        with urlopen(request, timeout=3) as response:
            return "sent" if 200 <= response.status < 300 else "delivery_failed"
    except Exception:
        return "delivery_failed"


def record(w: Path, command: str, kind: str, detail: str, exc: Exception | None = None) -> tuple[str, str]:
    """Keep full diagnostics in the user's folder; transmit metadata only when opted in."""
    report_id = uuid.uuid4().hex[:12]
    error_type = type(exc).__name__ if exc is not None else "UserReported"
    fingerprint = hashlib.sha256(f"{command}:{kind}:{error_type}".encode()).hexdigest()[:16]
    summary = {
        "schema": "aqua-beta-1", "report_id": report_id, "time": _stamp(),
        "version": VERSION, "command": command, "kind": kind,
        "error_type": error_type, "fingerprint": fingerprint,
        "python": platform.python_version(), "os": platform.system(),
    }
    local = dict(summary, detail=detail, traceback="".join(traceback.format_exception(exc)) if exc else "")
    reports = w / "Beta Reports"
    try:
        reports.mkdir(parents=True, exist_ok=True)
        path = reports / f"{report_id}.json"
        path.write_text(json.dumps(local, indent=2) + "\n", encoding="utf-8")
    except OSError:
        return report_id, "local_write_failed"
    delivery = _send(summary, w)
    try:
        local["delivery"] = delivery
        path.write_text(json.dumps(local, indent=2) + "\n", encoding="utf-8")
    except OSError:
        pass
    return report_id, delivery
