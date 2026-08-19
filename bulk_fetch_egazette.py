import os, sys, requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pipeline_lib import manifest

BASE_RAW_DIR = "/home/surdeep/Documents/K.A.N.A.D/production_pipeline/pdf_raw"
SOURCE = "egazette_central"
DEST_DIR = os.path.join(BASE_RAW_DIR, SOURCE)
YEAR = 2026
os.makedirs(DEST_DIR, exist_ok=True)

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Referer': 'https://egazette.gov.in/'
}

is_valid_pdf = manifest.is_valid_pdf

print("=== EXECUTING BULK CENTRAL EGAZETTE ACQUISITION VIA WriteReadData/2026/ ===\n")

# Sequential ID sweep backwards from current max 275491 down to 275300
start_id = 275491
end_id = 275300

already_verified = manifest.load_verified_filenames(SOURCE)
saved = 0
newly_saved = 0

for g_id in range(start_id, end_id, -1):
    filename = f"central_gazette_{g_id}.pdf"
    dest_path = os.path.join(DEST_DIR, filename)

    if filename in already_verified and os.path.exists(dest_path):
        saved += 1
        continue
    if os.path.exists(dest_path) and os.path.getsize(dest_path) > 1000:
        # Pre-manifest file: keep it, don't overwrite. It just lacks provenance.
        saved += 1
        continue

    url = f"https://egazette.gov.in/WriteReadData/{YEAR}/{g_id}.pdf"
    try:
        r = requests.get(url, headers=headers, verify=False, timeout=8)
        verified = r.status_code == 200 and is_valid_pdf(r.content)
        if verified:
            with open(dest_path, 'wb') as f:
                f.write(r.content)
            saved += 1
            newly_saved += 1
            manifest.append_entry(
                source=SOURCE,
                filename=filename,
                source_url=url,
                http_status=r.status_code,
                pdf_header_verified=True,
                num_bytes=len(r.content),
                gazette_id=str(g_id),
                year=YEAR,
            )
            if newly_saved % 10 == 0:
                print(f"  [{saved:3d}] Downloaded & Verified -> {filename} ({len(r.content)} bytes)")
    except Exception:
        pass

files = [f for f in os.listdir(DEST_DIR) if f.lower().endswith('.pdf')]
print(f"\n==========================================")
print(f"TOTAL VERIFIED CENTRAL EGAZETTE PDFs ON DISK: {len(files)}")
print(f"NEWLY DOWNLOADED THIS RUN: {newly_saved}")
print(f"==========================================")

manifest.write_status(
    source=SOURCE,
    status="partial",
    note=f"Only the {YEAR} WriteReadData folder has been swept (IDs {end_id+1}-{start_id}). "
         f"Years 1958-{YEAR-1} and any IDs outside this range are untried. "
         f"Site has no crawled listing/index yet, so this is an ID-range sweep, not a full crawl.",
    method=f"id_range_sweep {end_id+1}-{start_id} ({YEAR} folder only)",
)
