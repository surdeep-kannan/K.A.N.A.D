"""Crawl gujarathighcourt.nic.in for Gujarati-translated High Court judgments.

Real listing crawl: https://gujarathighcourt.nic.in/gujaratijudgments?page=N
walked from page 0 until a page returns zero PDF links (confirmed empty at
page 119). Each PDF is downloaded directly -- there's no separate item page,
the listing itself carries the final download URL.

This is the "judicial platform" source the PS calls for; previously there was
no fetch script for judgments anywhere in the pipeline.
"""
import os, sys, re, requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pipeline_lib import manifest

BASE = "https://gujarathighcourt.nic.in"
SOURCE = "gujarat_hc_judgments"
DEST_DIR = manifest.source_dir(SOURCE)

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

is_valid_pdf = manifest.is_valid_pdf
PDF_RE = re.compile(r'href="(https://gujarathighcourt\.nic\.in/hccms/sites/default/files/gujaratijudgments/[^"]+\.pdf)"', re.I)
YEAR_RE = re.compile(r'_of_(\d{4})_translated', re.I)

MAX_PAGES = 130  # site had 119 as of the last check; leave headroom


def main():
    os.makedirs(DEST_DIR, exist_ok=True)
    print("=== EXECUTING GUJARAT HIGH COURT JUDGMENTS ACQUISITION ===\n")

    already = manifest.load_verified_filenames(SOURCE)

    saved = 0
    skipped = 0
    failed = 0
    pages_walked = 0
    reached_empty_page = False

    for page in range(0, MAX_PAGES):
        url = f"{BASE}/gujaratijudgments?page={page}"
        try:
            r = requests.get(url, headers=HEADERS, verify=False, timeout=15)
        except Exception as e:
            print(f"  page {page}: error {e}")
            break
        if r.status_code != 200:
            print(f"  page {page}: HTTP {r.status_code}, stopping")
            break

        pdf_urls = sorted(set(PDF_RE.findall(r.text)))
        pages_walked += 1
        if not pdf_urls:
            reached_empty_page = True
            print(f"  page {page}: 0 links -> end of listing")
            break

        print(f"  page {page}: {len(pdf_urls)} judgment links")

        for pdf_url in pdf_urls:
            filename = os.path.basename(pdf_url)
            dest_path = os.path.join(DEST_DIR, filename)

            if filename in already:
                skipped += 1
                continue
            if os.path.exists(dest_path) and os.path.getsize(dest_path) > 1000:
                skipped += 1
                continue

            year_match = YEAR_RE.search(filename)
            year = int(year_match.group(1)) if year_match else None

            try:
                pr = requests.get(pdf_url, headers=HEADERS, verify=False, timeout=20)
            except Exception:
                failed += 1
                continue

            verified = pr.status_code == 200 and is_valid_pdf(pr.content)
            if not verified:
                failed += 1
                continue

            with open(dest_path, 'wb') as f:
                f.write(pr.content)

            manifest.append_entry(
                source=SOURCE,
                filename=filename,
                source_url=pdf_url,
                http_status=pr.status_code,
                pdf_header_verified=True,
                num_bytes=len(pr.content),
                gazette_id=None,
                year=year,
            )
            saved += 1
            if saved % 20 == 0:
                print(f"    [{saved} saved so far]")

    files = [f for f in os.listdir(DEST_DIR) if f.lower().endswith('.pdf')]
    print(f"\n==========================================")
    print(f"TOTAL VERIFIED GUJARAT HC JUDGMENT PDFs ON DISK: {len(files)}")
    print(f"NEWLY DOWNLOADED THIS RUN: {saved} (skipped: {skipped}, failed: {failed})")
    print(f"Pages walked: {pages_walked}")
    print(f"==========================================")

    if reached_empty_page:
        manifest.write_status(
            source=SOURCE,
            status="exhausted",
            note=(f"Walked the /gujaratijudgments listing page-by-page from page 0 until a "
                  f"page returned zero PDF links (empty at page {pages_walked}). This is the "
                  f"'Gujarati translated' High Court judgments listing specifically -- the "
                  f"site may have other judgment listings (e.g. English-language orders) not "
                  f"covered by this crawl."),
            method=f"paginated listing crawl (?page=0..{pages_walked-1}) of /gujaratijudgments",
        )
    else:
        manifest.write_status(
            source=SOURCE,
            status="partial",
            note=f"Listing crawl was capped at MAX_PAGES={MAX_PAGES} without hitting an empty page; "
                 f"the site may have more pages beyond what this run checked.",
            method=f"paginated listing crawl (?page=0..{MAX_PAGES-1}, capped)",
        )


if __name__ == '__main__':
    main()
