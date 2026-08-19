import os, requests, re

BASE_RAW_DIR = "/home/surdeep/Documents/K.A.N.A.D/production_pipeline/pdf_raw"
DEST_DIR = os.path.join(BASE_RAW_DIR, "egazette_central")
os.makedirs(DEST_DIR, exist_ok=True)

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Referer': 'https://egazette.gov.in/Default.aspx'
}

def is_valid_pdf(content):
    return len(content) > 1000 and content.startswith(b'%PDF')

# Standard extraordinary and weekly gazette PDF filenames follow strict patterns
# e.g., https://egazette.gov.in/WriteReadData/2026/275491.pdf or https://egazette.gov.in/WriteReadData/2026/275490.pdf
# Extracted Gazette IDs from homepage: 275491, 275490, 275489, 275488, 275424, 275331, 275294

gazette_ids = [275491, 275490, 275489, 275488, 275424, 275331, 275294]
# Probe a range around recent IDs
probe_ids = range(275480, 275500)

print("=== PROBING DIRECT WriteReadData STATIC PDF ENDPOINTS FOR CENTRAL EGAZETTE ===")

saved = 0
for g_id in probe_ids:
    url = f"https://egazette.gov.in/WriteReadData/2026/{g_id}.pdf"
    try:
        r = requests.get(url, headers=headers, verify=False, timeout=8)
        if r.status_code == 200 and is_valid_pdf(r.content):
            dest_path = os.path.join(DEST_DIR, f"central_gazette_{g_id}.pdf")
            with open(dest_path, 'wb') as f:
                f.write(r.content)
            saved += 1
            print(f"  [✓] Verified Gazette Download -> central_gazette_{g_id}.pdf ({len(r.content)} bytes)")
    except Exception:
        pass

print(f"\n==========================================")
print(f"TOTAL VERIFIED CENTRAL EGAZETTE PDFs PROBED & SAVED: {saved}")
print(f"==========================================")
