import os, sys, requests, urllib.parse
from bs4 import BeautifulSoup

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pipeline_lib import manifest

BASE_RAW_DIR = "/home/surdeep/Documents/K.A.N.A.D/production_pipeline/pdf_raw"
SOURCE = "mha_central"
DEST_DIR = os.path.join(BASE_RAW_DIR, SOURCE)

is_valid_pdf = manifest.is_valid_pdf


def fetch_mha_paginated():
    os.makedirs(DEST_DIR, exist_ok=True)
    print("=== EXECUTING PAGINATED MHA ACQUISITION (mha.gov.in/en/notifications/circular) ===\n")

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }

    base_urls = [
        "https://www.mha.gov.in/en/notifications/circular",
        "https://www.mha.gov.in/en/notifications/circular/archive-circular"
    ]

    pdf_urls = set()
    fully_paginated = True

    for base_url in base_urls:
        print(f"Scanning pagination for: {base_url}")
        for page in range(0, 35):
            url = f"{base_url}?page={page}"
            try:
                r = requests.get(url, headers=headers, verify=False, timeout=12)
                if r.status_code != 200:
                    break
                soup = BeautifulSoup(r.text, 'html.parser')
                links = soup.find_all('a', href=True)
                page_pdf_count = 0
                for a in links:
                    href = a['href']
                    if href.lower().endswith('.pdf') or '/sites/default/files/' in href.lower():
                        full_url = urllib.parse.urljoin(url, href)
                        if full_url.lower().endswith('.pdf'):
                            pdf_urls.add(full_url)
                            page_pdf_count += 1

                print(f"  Page {page:2d} -> Found {page_pdf_count:2d} PDF links (Total unique so far: {len(pdf_urls)})")
                if page_pdf_count == 0 and page > 0:
                    # End of pagination reached
                    break
            except Exception as e:
                print(f"  Error on page {page}: {e}")
                fully_paginated = False
                break

    print(f"\n==========================================")
    print(f"TOTAL UNIQUE MHA PDF LINKS DISCOVERED: {len(pdf_urls)}")
    print(f"==========================================")

    already_verified = manifest.load_verified_filenames(SOURCE)
    saved_count = 0
    newly_saved = 0

    for idx, pdf_url in enumerate(list(pdf_urls)):
        filename = os.path.basename(urllib.parse.urlparse(pdf_url).path)
        if not filename or not filename.endswith('.pdf'):
            filename = f"mha_doc_{idx+1:04d}.pdf"

        local_filename = f"mha_{filename}"
        dest_path = os.path.join(DEST_DIR, local_filename)

        if local_filename in already_verified and os.path.exists(dest_path):
            saved_count += 1
            continue
        if os.path.exists(dest_path) and os.path.getsize(dest_path) > 1000:
            # Pre-manifest file: keep it, don't overwrite. It just lacks provenance.
            saved_count += 1
            continue

        try:
            res = requests.get(pdf_url, headers=headers, verify=False, timeout=15)
            verified = res.status_code == 200 and is_valid_pdf(res.content)
            if verified:
                with open(dest_path, 'wb') as f:
                    f.write(res.content)
                saved_count += 1
                newly_saved += 1
                manifest.append_entry(
                    source=SOURCE,
                    filename=local_filename,
                    source_url=pdf_url,
                    http_status=res.status_code,
                    pdf_header_verified=True,
                    num_bytes=len(res.content),
                    gazette_id=None,
                    year=None,
                )
                if newly_saved % 10 == 0:
                    print(f"  [{saved_count:3d}/{len(pdf_urls)}] Saved -> {local_filename} ({len(res.content)} bytes)")
        except Exception:
            pass

    print(f"\n=== COMPLETED MHA ACQUISITION: {saved_count} VERIFIED PDFs IN {DEST_DIR} ({newly_saved} new) ===")

    if fully_paginated:
        manifest.write_status(
            source=SOURCE,
            status="partial",
            note="Walked notifications/circular and archive-circular pagination end-to-end "
                 "(stopped each listing when a page returned zero new PDF links), so those two "
                 "listings specifically are exhausted. But other MHA sections (common-circulars, "
                 "document-reports, press releases, orders) were not crawled by this script, so "
                 "the source as a whole is still partial.",
            method="paginated listing crawl (?page=0..34) across notifications/circular and archive-circular",
        )
    else:
        manifest.write_status(
            source=SOURCE,
            status="partial",
            note="Pagination crawl was interrupted by a request error before reaching the end "
                 "of at least one listing.",
            method="paginated listing crawl (?page=0..34), interrupted",
        )

    return saved_count


if __name__ == '__main__':
    fetch_mha_paginated()
