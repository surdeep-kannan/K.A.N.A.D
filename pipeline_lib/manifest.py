"""Shared provenance-tracking helpers for the acquisition pipeline.

Every fetch script that saves a PDF to pdf_raw/<source>/ should also append
one line to pdf_raw/<source>/_manifest.jsonl recording where that file came
from. This is the only place that knows the on-disk manifest format, so all
fetch scripts should go through it rather than writing JSON lines by hand.
"""
import os
import json
import threading
from datetime import datetime, timezone, timedelta

BASE_RAW_DIR = "/home/surdeep/Documents/K.A.N.A.D/production_pipeline/pdf_raw"
IST = timezone(timedelta(hours=5, minutes=30))

_append_lock = threading.Lock()


def source_dir(source):
    return os.path.join(BASE_RAW_DIR, source)


def manifest_path(source):
    return os.path.join(source_dir(source), "_manifest.jsonl")


def status_path(source):
    return os.path.join(source_dir(source), "_status.json")


def now_iso():
    return datetime.now(IST).isoformat(timespec="seconds")


def is_valid_pdf(content):
    return len(content) > 1000 and content.startswith(b"%PDF")


def load_manifest(source):
    """Return list of all entries currently recorded for a source (may include
    unverified/failed attempts if a caller chooses to log those)."""
    path = manifest_path(source)
    entries = []
    if os.path.exists(path):
        with open(path, "r") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return entries


def load_verified_filenames(source):
    """Filenames already downloaded and verified for this source, per the
    manifest. Used by fetch scripts to skip work they've already done."""
    return {e["filename"] for e in load_manifest(source) if e.get("pdf_header_verified")}


def append_entry(source, filename, source_url, http_status, pdf_header_verified,
                  num_bytes, gazette_id=None, year=None, extra=None):
    """Append one provenance record for a downloaded (or attempted) file.

    This never truncates or rewrites the manifest -- it only opens in append
    mode, so concurrent/rerun invocations are safe to skip-and-continue.
    """
    entry = {
        "filename": filename,
        "source_url": source_url,
        "fetched_at": now_iso(),
        "gazette_id": gazette_id,
        "year": year,
        "http_status": http_status,
        "pdf_header_verified": bool(pdf_header_verified),
        "bytes": num_bytes,
    }
    if extra:
        entry.update(extra)

    path = manifest_path(source)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with _append_lock:
        with open(path, "a") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return entry


def write_status(source, status, note, method):
    """Record the outcome of the most recent fetch attempt for a source.

    status must be one of: 'blocked', 'partial', 'exhausted'.
    """
    assert status in ("blocked", "partial", "exhausted"), status
    payload = {
        "status": status,
        "note": note,
        "last_fetch_method": method,
        "updated_at": now_iso(),
    }
    path = status_path(source)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(payload, f, indent=2)
    return payload


def read_status(source):
    path = status_path(source)
    if not os.path.exists(path):
        return None
    with open(path, "r") as f:
        return json.load(f)
