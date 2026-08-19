"""Crawl Gujarat department GR pages that dump their full listing into a
single static page (no ASP.NET GridView postback, no query-string
pagination -- confirmed by checking for __doPostBack/page= controls before
adding each one here). One GET per page is the whole crawl.

Sources, each mapped onto its pre-existing pdf_raw/<dept> folder:
  forest_environment  -- fed.gujarat.gov.in/government-resolutions.htm
  labour_deeper       -- labour.gujarat.gov.in e-citizen GR page
                          (kept separate from labour_employment, which came
                          from an older, differently-sourced scrape)
  urban_dev           -- udd.gujarat.gov.in homepage (mixed policy/budget/GR
                          PDFs, not a dedicated GR listing -- there's no
                          separate GR page on this site)
  panchayat_deeper    -- panchayat.gujarat.gov.in/en/government-resolutions
                          (kept separate from panchayat_rural_housing, which
                          came from an older, differently-sourced scrape)
"""
import os, sys, re, requests
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pipeline_lib import manifest, aspnet_grid

HEADERS = aspnet_grid.HEADERS
is_valid_pdf = manifest.is_valid_pdf
PDF_HREF_RE = re.compile(r'href="([^"]*\.pdf[^"]*)"', re.I)
WORKERS = 12


def _make_session():
    s = requests.Session()
    s.headers.update(HEADERS)
    adapter = requests.adapters.HTTPAdapter(pool_connections=WORKERS, pool_maxsize=WORKERS)
    s.mount('https://', adapter)
    s.mount('http://', adapter)
    return s

PAGES = {
    "forest_environment": "https://fed.gujarat.gov.in/government-resolutions.htm",
    "labour_deeper": "https://www.labour.gujarat.gov.in/e-citizen-government-resolution.htm",
    "urban_dev": "https://udd.gujarat.gov.in/",
    "panchayat_deeper": "https://panchayat.gujarat.gov.in/en/government-resolutions",
    "health_family_welfare": "https://gujhealth.gujarat.gov.in/government-resolutions.htm",
    "sports_youth": "https://sycd.gujarat.gov.in/government-resolution.htm",
}


def _download_one(session, source, dest_dir, url, pdf_url):
    import urllib.parse
    filename = os.path.basename(urllib.parse.urlparse(pdf_url).path)
    dest_path = os.path.join(dest_dir, filename)

    try:
        pr = session.get(pdf_url, verify=False, timeout=20)
    except Exception:
        return "failed"

    verified = pr.status_code == 200 and is_valid_pdf(pr.content)
    if not verified:
        return "failed"

    with open(dest_path, 'wb') as f:
        f.write(pr.content)

    manifest.append_entry(
        source=source,
        filename=filename,
        source_url=pdf_url,
        http_status=pr.status_code,
        pdf_header_verified=True,
        num_bytes=len(pr.content),
        gazette_id=None,
        year=None,
        extra={"listing_page": url},
    )
    return "saved"


def fetch_page(source, url):
    dest_dir = manifest.source_dir(source)
    os.makedirs(dest_dir, exist_ok=True)
    print(f"\n=== {source}: {url} ===")

    session = _make_session()
    try:
        r = session.get(url, verify=False, timeout=25)
    except Exception as e:
        print(f"  ERROR fetching listing: {e}")
        manifest.write_status(source, "blocked", f"Could not fetch listing page: {e}", f"GET {url}")
        return 0
    if r.status_code != 200:
        print(f"  HTTP {r.status_code} fetching listing")
        manifest.write_status(source, "blocked", f"Listing page returned HTTP {r.status_code}", f"GET {url}")
        return 0

    import urllib.parse
    pdf_urls = sorted(set(urllib.parse.urljoin(url, h) for h in PDF_HREF_RE.findall(r.text)))
    print(f"  {len(pdf_urls)} unique PDF links on the page")

    already = manifest.load_verified_filenames(source)
    to_fetch = []
    skipped = 0
    for pdf_url in pdf_urls:
        filename = os.path.basename(urllib.parse.urlparse(pdf_url).path)
        if not filename.lower().endswith('.pdf'):
            continue
        dest_path = os.path.join(dest_dir, filename)
        if filename in already or (os.path.exists(dest_path) and os.path.getsize(dest_path) > 1000):
            skipped += 1
            continue
        to_fetch.append(pdf_url)

    saved, failed = 0, 0
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futures = [pool.submit(_download_one, session, source, dest_dir, url, u) for u in to_fetch]
        for i, fut in enumerate(as_completed(futures), 1):
            result = fut.result()
            if result == "saved":
                saved += 1
            else:
                failed += 1
            if i % 25 == 0:
                print(f"    [{i}/{len(to_fetch)} processed, {saved} saved so far]")

    files = [f for f in os.listdir(dest_dir) if f.lower().endswith('.pdf')]
    print(f"  -> {source}: {len(files)} PDFs on disk, {saved} new, {skipped} skipped, {failed} failed")

    has_pagination = bool(re.search(r'__doPostBack|[?&]page=\d', r.text))
    if has_pagination:
        status, note = "partial", "Pagination controls were detected on this page after all -- re-check crawl logic."
    else:
        status = "exhausted"
        note = (f"Fetched the single listing page at {url}; it dumps its full GR list without "
                f"pagination (no __doPostBack or ?page= controls found), so every PDF link on "
                f"the page was captured. Other sections of this department's site (if any) were "
                f"not crawled.")
    manifest.write_status(source, status, note, method=f"single-page listing scrape of {url}")
    return saved


def main():
    print("=== EXECUTING STATIC GUJARAT GR PAGE ACQUISITION ===")
    totals = {}
    for source, url in PAGES.items():
        totals[source] = fetch_page(source, url)
    print("\n==========================================")
    print("New PDFs saved this run:", totals)
    print("==========================================")


if __name__ == '__main__':
    main()
