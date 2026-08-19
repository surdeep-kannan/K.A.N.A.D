"""Crawl the ASP.NET GridView-paginated GR listings on gad.gujarat.gov.in and
its divisional sub-sites, using pipeline_lib.aspnet_grid (real postback
pagination, not a guessed range or a single-page GET).

Each division maps onto one of the pre-existing pdf_raw/<dept> folders.
NRI division (gad_nri) was probed but its GR page URL could not be found
from the site's own navigation in this run, so it's left untouched.
"""
import os, sys, requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pipeline_lib import manifest, aspnet_grid

GRID_EVENT_TARGET = 'ctl00$ContentPlaceHolder1$UserDisplayGRDocuments1$gvDocument'

PORTALS = {
    "gad_personnel": "https://gad.gujarat.gov.in/personnel/government-resolutions.htm",
    "gad_planning": "https://planning.gujarat.gov.in/govt-resolution.htm",
    "gad_admin_reforms": "https://artd.gujarat.gov.in/government-resolution.htm",
}

is_valid_pdf = manifest.is_valid_pdf
HEADERS = aspnet_grid.HEADERS


def fetch_portal(source, start_url):
    dest_dir = manifest.source_dir(source)
    os.makedirs(dest_dir, exist_ok=True)
    print(f"\n=== {source}: {start_url} ===")

    session = requests.Session()
    session.headers.update(HEADERS)

    pdf_hits, reached_end, last_page = aspnet_grid.crawl_gridview_pdfs(
        session, start_url, GRID_EVENT_TARGET
    )
    print(f"  Walked {last_page} grid pages, {len(pdf_hits)} unique PDF links, reached_end={reached_end}")

    already = manifest.load_verified_filenames(source)
    saved, skipped, failed = 0, 0, 0

    for page_no, pdf_url in pdf_hits:
        filename = os.path.basename(pdf_url.split('?')[0])
        dest_path = os.path.join(dest_dir, filename)

        if filename in already:
            skipped += 1
            continue
        if os.path.exists(dest_path) and os.path.getsize(dest_path) > 1000:
            skipped += 1
            continue

        try:
            pr = session.get(pdf_url, headers=HEADERS, verify=False, timeout=20)
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
            source=source,
            filename=filename,
            source_url=pdf_url,
            http_status=pr.status_code,
            pdf_header_verified=True,
            num_bytes=len(pr.content),
            gazette_id=None,
            year=None,
            extra={"grid_page": page_no, "listing_page": start_url},
        )
        saved += 1
        if saved % 25 == 0:
            print(f"    [{saved} saved so far]")

    files = [f for f in os.listdir(dest_dir) if f.lower().endswith('.pdf')]
    print(f"  -> {source}: {len(files)} PDFs on disk, {saved} new, {skipped} skipped, {failed} failed")

    status = "exhausted" if reached_end else "partial"
    note = (f"Walked the GridView postback pagination for {start_url} "
            f"({last_page} pages, reached_end={reached_end}). "
            f"{'Grid paging was walked until 3 consecutive pages returned no new links.' if reached_end else 'Crawl stopped before confirming the end of the grid (hit max_pages or a request error).'}")
    manifest.write_status(
        source=source,
        status=status,
        note=note,
        method=f"ASP.NET GridView postback pagination crawl of {start_url}",
    )
    return saved


def main():
    print("=== EXECUTING GUJARAT GR PORTALS ACQUISITION (gad.gujarat.gov.in divisions) ===")
    totals = {}
    for source, url in PORTALS.items():
        totals[source] = fetch_portal(source, url)
    print("\n==========================================")
    print("New PDFs saved this run:", totals)
    print("==========================================")


if __name__ == '__main__':
    main()
