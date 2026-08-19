"""Regenerate production_pipeline/corpus_manifest.json from what's actually on
disk. Never hand-edit corpus_manifest.json -- rerun this script instead.

count is always len(actual .pdf files in pdf_raw/<source>/), not a manifest
line count, so it stays correct even for sources that predate manifest
tracking. years_covered is derived from manifest 'year' fields when present.
status is read from pdf_raw/<source>/_status.json, written by whichever fetch
script last touched that source; sources with no _status.json are reported as
status "unknown" rather than a guess.

Sources whose status is "blocked" and which have an entry in
external_sources.json get an "external_link" field instead of local PDFs --
these are departments whose GR listings are JS-rendered and WAF-protected
against automated browsers, so we never downloaded a local copy. The
platform should render these as "view at official source" links rather than
claiming local coverage.
"""
import os
import sys
import json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pipeline_lib import manifest

PIPELINE_DIR = "/home/surdeep/Documents/K.A.N.A.D/production_pipeline"
OUT_PATH = os.path.join(PIPELINE_DIR, "corpus_manifest.json")
EXTERNAL_SOURCES_PATH = os.path.join(PIPELINE_DIR, "external_sources.json")


def load_external_sources():
    if not os.path.exists(EXTERNAL_SOURCES_PATH):
        return {}
    with open(EXTERNAL_SOURCES_PATH) as f:
        return json.load(f)


def build():
    external_sources = load_external_sources()
    sources = {}
    total = 0

    # PDFs sitting loose directly in pdf_raw/ (not under any source subdir)
    root_pdfs = [f for f in os.listdir(manifest.BASE_RAW_DIR)
                 if f.lower().endswith('.pdf')
                 and os.path.isfile(os.path.join(manifest.BASE_RAW_DIR, f))]
    if root_pdfs:
        total += len(root_pdfs)
        sources["_root_untracked"] = {
            "count": len(root_pdfs),
            "years_covered": [],
            "status": "unknown",
            "status_note": "Loose PDFs directly under pdf_raw/, not sorted into a source "
                            "subdirectory. No provenance manifest exists for these.",
        }

    for name in sorted(os.listdir(manifest.BASE_RAW_DIR)):
        src_dir = os.path.join(manifest.BASE_RAW_DIR, name)
        if not os.path.isdir(src_dir):
            continue

        pdf_files = [f for f in os.listdir(src_dir) if f.lower().endswith('.pdf')]
        count = len(pdf_files)
        total += count

        years = set()
        for entry in manifest.load_manifest(name):
            year = entry.get('year')
            if year and 1800 <= year <= 2026:
                years.add(year)

        status_info = manifest.read_status(name)
        status = status_info['status'] if status_info else "unknown"

        sources[name] = {
            "count": count,
            "years_covered": sorted(years),
            "status": status,
        }
        if status_info:
            sources[name]["status_note"] = status_info.get("note")
            sources[name]["last_fetch_method"] = status_info.get("last_fetch_method")
            sources[name]["status_updated_at"] = status_info.get("updated_at")

        if status == "blocked" and name in external_sources:
            sources[name]["external_link"] = external_sources[name]

    unblocked_external = {k: v for k, v in external_sources.items() if k not in sources}

    payload = {
        "generated_at": manifest.now_iso(),
        "sources": sources,
        "total_pdfs": total,
        "external_only_sources": unblocked_external,
    }

    with open(OUT_PATH, 'w') as f:
        json.dump(payload, f, indent=2)

    print(f"Wrote {OUT_PATH}: {total} total PDFs across {len(sources)} sources.")
    return payload


if __name__ == '__main__':
    build()
