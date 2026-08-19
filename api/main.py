"""API layer for the Unified Legal & Government Intelligence Platform.

Serves what the acquisition pipeline actually produced:
  - corpus_manifest.json  -- per-source counts/status/external links
  - pdf_raw/<source>/_manifest.jsonl -- per-document provenance (source_url,
    fetch time, year, ...) for the ~10k documents fetched with the new
    tracked scripts. Sources that predate manifest tracking (e.g.
    home_department, labour_employment) still count toward totals in
    corpus_manifest.json but have no per-document rows here.
  - pipeline_lib/catalog.py -- static jurisdiction/doc-type classification
    per source, since that's not derivable from the raw files.

Run: uvicorn api.main:app --reload --port 8000   (from production_pipeline/)
"""
import os
import sys
import json
import glob
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from pipeline_lib import manifest, catalog
import build_corpus_manifest

app = FastAPI(
    title="Unified Legal & Government Intelligence Platform API",
    description="Search and browse Government Resolutions, gazette notifications, "
                "Acts, and court judgments aggregated from Central Government and "
                "Gujarat State sources.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_CACHE = {"corpus": None, "documents": None}


def _load_corpus(force=False):
    if _CACHE["corpus"] is None or force:
        _CACHE["corpus"] = build_corpus_manifest.build()
    return _CACHE["corpus"]


def _load_all_documents(force=False):
    """Flatten every source's _manifest.jsonl into one in-memory list, each
    row enriched with its source key + jurisdiction/doc_type classification.
    Only sources with manifest tracking appear here (see module docstring)."""
    if _CACHE["documents"] is not None and not force:
        return _CACHE["documents"]

    docs = []
    for jsonl_path in glob.glob(os.path.join(manifest.BASE_RAW_DIR, "*", "_manifest.jsonl")):
        source = os.path.basename(os.path.dirname(jsonl_path))
        cls = catalog.classify(source)
        with open(jsonl_path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not entry.get("pdf_header_verified"):
                    continue
                jurisdiction = cls["jurisdiction"]
                if source == "india_code" and entry.get("collection"):
                    jurisdiction = catalog.CENTRAL if entry["collection"] == "central" else catalog.GUJARAT_STATE
                docs.append({
                    "source": source,
                    "source_display_name": cls["display_name"],
                    "jurisdiction": jurisdiction,
                    "doc_type": cls["doc_type"],
                    "filename": entry.get("filename"),
                    "title": entry.get("title"),
                    "source_url": entry.get("source_url"),
                    "fetched_at": entry.get("fetched_at"),
                    "year": entry.get("year"),
                    "gazette_id": entry.get("gazette_id"),
                    "bytes": entry.get("bytes"),
                })
    _CACHE["documents"] = docs
    return docs


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/sources")
def list_sources():
    """Every pdf_raw/<source> folder: count, fetch status, jurisdiction,
    doc type, and (for blocked sources) a link to the live official site."""
    corpus = _load_corpus()
    out = []
    for key, info in corpus["sources"].items():
        cls = catalog.classify(key)
        out.append({
            "source": key,
            **cls,
            "count": info["count"],
            "status": info["status"],
            "status_note": info.get("status_note"),
            "years_covered": info.get("years_covered", []),
            "external_link": info.get("external_link"),
        })
    out.sort(key=lambda s: -s["count"])
    return {"generated_at": corpus["generated_at"], "total_pdfs": corpus["total_pdfs"], "sources": out}


@app.get("/api/sources/{source}")
def get_source(source: str):
    corpus = _load_corpus()
    if source not in corpus["sources"]:
        raise HTTPException(status_code=404, detail=f"Unknown source '{source}'")
    info = corpus["sources"][source]
    cls = catalog.classify(source)
    return {"source": source, **cls, **info}


@app.get("/api/documents")
def list_documents(
    source: Optional[str] = None,
    jurisdiction: Optional[str] = None,
    doc_type: Optional[str] = None,
    year: Optional[int] = None,
    q: Optional[str] = Query(None, description="Matches filename, title, or gazette/act ID"),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=200),
):
    """Paginated, filterable listing across every document we have real
    provenance for (source_url, fetch time, etc.) -- the Data Aggregation +
    Advanced Filtering modules."""
    docs = _load_all_documents()

    if source:
        docs = [d for d in docs if d["source"] == source]
    if jurisdiction:
        docs = [d for d in docs if d["jurisdiction"] == jurisdiction]
    if doc_type:
        docs = [d for d in docs if d["doc_type"] == doc_type]
    if year:
        docs = [d for d in docs if d["year"] == year]
    if q:
        needle = q.lower()
        def matches(d):
            haystack = " ".join(str(d.get(f) or "") for f in ("filename", "title", "gazette_id"))
            return needle in haystack.lower()
        docs = [d for d in docs if matches(d)]

    total = len(docs)
    start = (page - 1) * page_size
    page_docs = docs[start:start + page_size]

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": (total + page_size - 1) // page_size,
        "results": page_docs,
    }


@app.get("/api/documents/{source}/{filename}")
def get_document(source: str, filename: str):
    for entry in manifest.load_manifest(source):
        if entry.get("filename") == filename:
            cls = catalog.classify(source)
            return {"source": source, **cls, **entry, "pdf_url": f"/api/pdf/{source}/{filename}"}
    dest_path = os.path.join(manifest.source_dir(source), filename)
    if os.path.exists(dest_path):
        cls = catalog.classify(source)
        return {
            "source": source, **cls, "filename": filename,
            "source_url": None,
            "note": "File exists on disk but predates provenance tracking -- no manifest record.",
            "pdf_url": f"/api/pdf/{source}/{filename}",
        }
    raise HTTPException(status_code=404, detail="Document not found")


@app.get("/api/pdf/{source}/{filename}")
def get_pdf(source: str, filename: str):
    """Direct access to the original document -- Download & Sharing module."""
    dest_path = os.path.join(manifest.source_dir(source), filename)
    real_dir = os.path.realpath(manifest.source_dir(source))
    real_path = os.path.realpath(dest_path)
    if not real_path.startswith(real_dir + os.sep) or not os.path.exists(real_path):
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(real_path, media_type="application/pdf", filename=filename)


@app.get("/api/search")
def search_documents(q: str = Query(..., min_length=1), limit: int = Query(25, ge=1, le=200)):
    """Metadata search (filename/title/gazette id) across all tracked
    documents. Not full-text: OCR/translation hasn't run on the bulk
    13k-document corpus, only on a small legacy sample -- see /api/legacy-fulltext-search."""
    result = list_documents(q=q, page=1, page_size=limit)
    return {"query": q, "total_matches": result["total"], "results": result["results"]}


@app.get("/api/legacy-fulltext-search")
def legacy_fulltext_search(q: str = Query(..., min_length=1), top_k: int = Query(5, ge=1, le=50)):
    """AI-summarization-adjacent full-text search over the small legacy OCR
    sample (rag_search_engine.py + vector_store/rag_documents_manifest.json,
    ~17 documents). Kept separate from /api/search because it covers a tiny
    fraction of the real corpus -- don't confuse this with corpus-wide search."""
    import rag_search_engine
    manifest_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                  "vector_store", "rag_documents_manifest.json")
    if not os.path.exists(manifest_path):
        raise HTTPException(status_code=503, detail="Legacy RAG manifest not found")
    engine = rag_search_engine.MinimalRAGEngine(manifest_path)
    return {"query": q, "results": engine.search(q, top_k=top_k)}


@app.get("/api/stats")
def stats():
    """Dashboard & Analytics module: totals by jurisdiction, doc type, and status."""
    corpus = _load_corpus()
    by_jurisdiction = {}
    by_doc_type = {}
    by_status = {}
    for key, info in corpus["sources"].items():
        cls = catalog.classify(key)
        by_jurisdiction[cls["jurisdiction"]] = by_jurisdiction.get(cls["jurisdiction"], 0) + info["count"]
        by_doc_type[cls["doc_type"]] = by_doc_type.get(cls["doc_type"], 0) + info["count"]
        by_status[info["status"]] = by_status.get(info["status"], 0) + 1
    return {
        "total_pdfs": corpus["total_pdfs"],
        "total_sources": len(corpus["sources"]),
        "by_jurisdiction": by_jurisdiction,
        "by_doc_type": by_doc_type,
        "sources_by_status": by_status,
        "generated_at": corpus["generated_at"],
    }


@app.post("/api/admin/refresh")
def refresh():
    """Re-scan disk and rebuild the in-memory caches -- call after a fetch run."""
    _load_corpus(force=True)
    _load_all_documents(force=True)
    return {"status": "refreshed", "total_pdfs": _CACHE["corpus"]["total_pdfs"], "total_documents": len(_CACHE["documents"])}
