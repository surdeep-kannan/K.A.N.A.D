"""Corpus-wide enrichment pipeline: OCR + page images + AI summary for every
PDF across every pdf_raw/<source>/ folder (not just the small curated batch
run_pipeline.py originally targeted).

For each (source, filename) not already in gr_documents:
  1. OCR the PDF (reused from run_pipeline.process_pdf_ocr) -> text + one
     PNG per page saved under pdf_images/<source>__<doc_id>/page_N.png.
  2. Parse header metadata (department/GR number/date) -- reused from
     run_pipeline.parse_header_metadata.
  3. Call Zoho Catalyst's GLM chat endpoint for an English summary.
  4. Look up the document's source_url from pdf_raw/<source>/_manifest.jsonl
     (the "where we got this PDF" link -- may be None for pre-manifest files).
  5. Insert one row into gr_documents and commit immediately, so the job is
     safe to interrupt and resume -- rerunning just skips (source, filename)
     pairs already present.

This is slow (OCR + a network LLM call per document) and NOT meant to
process all ~13k PDFs in one sitting. Run with --limit N to do a bounded
batch, and rerun repeatedly (or cron it) to make incremental progress.
"""
import os
import sys
import json
import sqlite3
import argparse
import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pipeline_lib import manifest as prov_manifest, catalog
from run_pipeline import (
    process_pdf_ocr, parse_header_metadata, get_zoho_headers, sanitize_ocr_text,
)

BASE_DIR = "/home/surdeep/Documents/K.A.N.A.D/production_pipeline"
DB_PATH = os.path.join(BASE_DIR, "database", "gujarat_gr_intel.db")
IMG_DIR = os.path.join(BASE_DIR, "pdf_images")

SKIP_SOURCES = {"_root_untracked"}  # loose files, no clean source folder


def init_schema():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("PRAGMA table_info(gr_documents)")
    cols = [c[1] for c in cur.fetchall()]
    if "source" not in cols:
        cur.execute("ALTER TABLE gr_documents ADD COLUMN source TEXT")
    if "ai_summary" not in cols:
        cur.execute("ALTER TABLE gr_documents ADD COLUMN ai_summary TEXT")
    conn.commit()
    conn.close()


def already_processed(conn, source, filename):
    row = conn.execute(
        "SELECT id FROM gr_documents WHERE source = ? AND filename = ?", (source, filename)
    ).fetchone()
    return row is not None


def lookup_source_url(source, filename):
    for entry in prov_manifest.load_manifest(source):
        if entry.get("filename") == filename:
            return entry.get("source_url")
    return None


def summarize_glm(text, title=None):
    headers, project_id = get_zoho_headers()
    url = f"https://api.catalyst.zoho.in/quickml/v1/project/{project_id}/glm/chat"

    title_hint = f"Document title (if known): {title}\n\n" if title else ""
    prompt = (
        "You are summarizing an official Indian government document (a Government Resolution, "
        "gazette notification, Act, or court judgment) for a citizen-facing legal search platform. "
        "The source text may be in Gujarati, English, or a mix (OCR output, may contain noise).\n\n"
        "Write a concise summary in clean English (3-6 sentences): what the document does, which "
        "department/authority issued it, and any key dates, numbers, or eligibility conditions. "
        "Output ONLY the summary paragraph, no preamble, no meta-commentary, no markdown.\n\n"
        f"{title_hint}SOURCE TEXT:\n{text[:4500]}"
    )
    payload = {
        "model": "crm-di-glm47b_30b_it",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.0,
        "max_tokens": 400,
    }
    try:
        r = requests.post(url, headers=headers, json=payload, timeout=90)
        if r.status_code != 200:
            return None
        res_text = r.json().get("response", "")
        if "</think>" in res_text:
            res_text = res_text.split("</think>")[-1].strip()
        return res_text.strip() or None
    except Exception as e:
        print(f"  GLM summary error: {e}")
        return None


def process_one(conn, source, filename, pdf_path):
    doc_id = f"{source}__{os.path.splitext(filename)[0]}"
    # process_pdf_ocr derives its image dir from the pdf's basename; give it
    # a source-qualified temp copy path via doc_id override is unnecessary --
    # instead we just pass the real path and post-fix the image dir name.
    text, lang, status, _unused_img_paths = process_pdf_ocr(pdf_path)
    text = sanitize_ocr_text(text)

    # Re-derive image paths using our source-qualified doc_id so filenames
    # from different sources never collide under pdf_images/.
    src_doc_id = os.path.splitext(filename)[0]
    default_img_dir = os.path.join(IMG_DIR, src_doc_id)
    qualified_img_dir = os.path.join(IMG_DIR, doc_id)
    if os.path.isdir(default_img_dir) and default_img_dir != qualified_img_dir:
        if os.path.isdir(qualified_img_dir):
            import shutil
            shutil.rmtree(qualified_img_dir)
        os.rename(default_img_dir, qualified_img_dir)
    page_images = sorted(
        os.path.join("pdf_images", doc_id, f)
        for f in os.listdir(qualified_img_dir)
    ) if os.path.isdir(qualified_img_dir) else []

    meta = parse_header_metadata(text, pdf_path)
    summary = summarize_glm(text, title=meta.get("gr_number")) if status == "PASS" else None
    source_url = lookup_source_url(source, filename)

    conn.execute(
        """INSERT INTO gr_documents
           (filename, source, title, doc_type, department, gr_number, gr_date,
            source_language, quality_status, date_confidence, gr_number_confidence,
            english_translation, ai_summary, source_pdf_path, page_image_paths, source_url)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            filename, source, None, catalog.classify(source)["doc_type"],
            meta.get("department"), meta.get("gr_number"), meta.get("gr_date"),
            lang, status, meta.get("date_confidence"), meta.get("gr_number_confidence"),
            None, summary, pdf_path, json.dumps(page_images), source_url,
        ),
    )
    conn.commit()
    return status, bool(summary)


def run(limit=None, only_source=None):
    init_schema()
    conn = sqlite3.connect(DB_PATH)

    todo = []
    for source in sorted(os.listdir(prov_manifest.BASE_RAW_DIR)):
        if source in SKIP_SOURCES:
            continue
        if only_source and source != only_source:
            continue
        src_dir = os.path.join(prov_manifest.BASE_RAW_DIR, source)
        if not os.path.isdir(src_dir):
            continue
        for filename in sorted(os.listdir(src_dir)):
            if not filename.lower().endswith(".pdf"):
                continue
            if already_processed(conn, source, filename):
                continue
            todo.append((source, filename, os.path.join(src_dir, filename)))

    print(f"=== ENRICHMENT: {len(todo)} unprocessed documents queued"
          f"{f' (limit {limit})' if limit else ''} ===")
    if limit:
        todo = todo[:limit]

    done, passed, summarized = 0, 0, 0
    for source, filename, pdf_path in todo:
        try:
            status, got_summary = process_one(conn, source, filename, pdf_path)
        except Exception as e:
            print(f"  [FAIL] {source}/{filename}: {e}")
            continue
        done += 1
        if status == "PASS":
            passed += 1
        if got_summary:
            summarized += 1
        if done % 5 == 0:
            print(f"  [{done}/{len(todo)}] processed -- {passed} OCR-pass, {summarized} summarized")

    print(f"=== DONE: {done} processed, {passed} OCR-pass, {summarized} summarized ===")
    conn.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None, help="Max documents to process this run")
    ap.add_argument("--source", type=str, default=None, help="Only process this one source")
    args = ap.parse_args()
    run(limit=args.limit, only_source=args.source)
