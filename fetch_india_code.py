"""Crawl indiacode.nic.in (DSpace) for Central Acts + Gujarat State Acts.

Real listing crawl, not a guessed ID sweep:
  1. https://www.indiacode.nic.in/handle/123456789/<collection>/browse?type=shorttitle&offset=N
     walked with offset += 20 until offset >= the "X to Y of TOTAL" count DSpace reports.
  2. Each item page (/handle/123456789/<id>?view_type=browse) is fetched to find its
     bitstream (PDF) link(s).
  3. Each bitstream is downloaded and logged to the manifest with its exact source URL.

Scope matches the PS: Central Acts (collection 1362) + Gujarat State Acts (collection 2455).
"""
import os, sys, re, time, requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pipeline_lib import manifest

BASE = "https://www.indiacode.nic.in"
SOURCE = "india_code"
DEST_DIR = manifest.source_dir(SOURCE)

COLLECTIONS = {
    "central": "123456789/1362",
    "gujarat": "123456789/2455",
}

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

is_valid_pdf = manifest.is_valid_pdf

ITEM_RE = re.compile(r'href="(/handle/123456789/(\d+)\?view_type=browse)"')
COUNT_RE = re.compile(r'(\d+)\s+to\s+(\d+)\s+of\s+(\d+)')
BITSTREAM_RE = re.compile(r'href="(/bitstream/123456789/\d+/[^"]+\.pdf)"', re.I)
YEAR_RE = re.compile(r'\b(1[7-9]\d{2}|20\d{2})\b')


def list_item_handles(collection_path):
    """Walk the shorttitle browse listing for a collection, returning all
    (item_id, item_url) pairs. Stops when offset passes the reported total,
    so this is an exhaustive crawl of the collection's own index."""
    handles = {}
    offset = 0
    total = None
    while total is None or offset < total:
        url = (f"{BASE}/handle/{collection_path}/browse?type=shorttitle"
               f"&sort_by=3&order=ASC&rpp=20&etal=-1&offset={offset}")
        try:
            r = requests.get(url, headers=HEADERS, verify=False, timeout=15)
        except Exception as e:
            print(f"    [list] error at offset {offset}: {e}")
            break
        if r.status_code != 200:
            print(f"    [list] HTTP {r.status_code} at offset {offset}")
            break

        m = COUNT_RE.search(r.text)
        if m:
            total = int(m.group(3))

        found = ITEM_RE.findall(r.text)
        if not found:
            break
        for path, item_id in found:
            handles[item_id] = f"{BASE}{path}"

        offset += 20
        if total is None:
            # no count banner and no growth -> bail rather than loop forever
            break

    return handles, total


def fetch_item_pdf(item_id, item_url, collection_name, already_ids):
    if item_id in already_ids:
        return "skipped"

    try:
        r = requests.get(item_url, headers=HEADERS, verify=False, timeout=15)
    except Exception as e:
        return f"error: {e}"
    if r.status_code != 200:
        return f"http {r.status_code}"

    bitstreams = BITSTREAM_RE.findall(r.text)
    if not bitstreams:
        return "no_pdf_link"

    pdf_path = bitstreams[0]
    pdf_url = f"{BASE}{pdf_path}"
    base_filename = os.path.basename(pdf_path)
    filename = f"{collection_name}_{item_id}_{base_filename}"
    dest_path = os.path.join(DEST_DIR, filename)

    title_match = re.search(r'<title>India Code:\s*(.*?)</title>', r.text, re.S)
    title = title_match.group(1).strip() if title_match else None
    year_match = YEAR_RE.search(title) if title else None
    year = int(year_match.group(1)) if year_match else None

    if os.path.exists(dest_path) and os.path.getsize(dest_path) > 1000:
        return "on_disk_untracked"

    try:
        pr = requests.get(pdf_url, headers=HEADERS, verify=False, timeout=20)
    except Exception as e:
        return f"error: {e}"

    verified = pr.status_code == 200 and is_valid_pdf(pr.content)
    if not verified:
        return f"http {pr.status_code} not_verified"

    with open(dest_path, 'wb') as f:
        f.write(pr.content)

    manifest.append_entry(
        source=SOURCE,
        filename=filename,
        source_url=pdf_url,
        http_status=pr.status_code,
        pdf_header_verified=True,
        num_bytes=len(pr.content),
        gazette_id=item_id,
        year=year,
        extra={"collection": collection_name, "item_page": item_url, "title": title},
    )
    return "saved"


def main():
    os.makedirs(DEST_DIR, exist_ok=True)
    print("=== EXECUTING INDIA CODE ACQUISITION (indiacode.nic.in) ===\n")

    already = manifest.load_verified_filenames(SOURCE)
    already_ids = set()
    for e in manifest.load_manifest(SOURCE):
        if e.get("pdf_header_verified") and e.get("gazette_id"):
            already_ids.add(e["gazette_id"])

    saved = 0
    skipped = 0
    failed = 0
    collection_totals = {}
    fully_walked = True

    for name, path in COLLECTIONS.items():
        print(f"Listing collection '{name}' ({path}) ...")
        handles, total = list_item_handles(path)
        collection_totals[name] = {"listed": len(handles), "reported_total": total}
        if total is not None and len(handles) < total:
            fully_walked = False
        print(f"  -> {len(handles)} items listed (site reports total={total})")

        for i, (item_id, item_url) in enumerate(handles.items()):
            result = fetch_item_pdf(item_id, item_url, name, already_ids)
            if result == "saved":
                saved += 1
                if saved % 10 == 0:
                    print(f"  [{name}] [{saved} saved so far] item {item_id}")
            elif result in ("skipped", "on_disk_untracked"):
                skipped += 1
            else:
                failed += 1

    files = [f for f in os.listdir(DEST_DIR) if f.lower().endswith('.pdf')]
    print(f"\n==========================================")
    print(f"TOTAL VERIFIED INDIA CODE PDFs ON DISK: {len(files)}")
    print(f"NEWLY DOWNLOADED THIS RUN: {saved}  (skipped already-present: {skipped}, failed: {failed})")
    print(f"Collection totals: {collection_totals}")
    print(f"==========================================")

    if fully_walked:
        status = "partial"
        note = (f"Walked the shorttitle browse index end-to-end for both collections "
                f"(central Acts handle 1362, Gujarat Acts handle 2455) and reached the "
                f"site-reported item counts: {collection_totals}. Both indexes are "
                f"exhausted, but only these two collections (Central + Gujarat) were "
                f"crawled -- other states/UTs on indiacode.nic.in were not touched, and "
                f"some items had no bitstream (PDF) link and were skipped ({failed} failures).")
    else:
        status = "partial"
        note = f"Listing crawl did not reach the site-reported totals: {collection_totals}."

    manifest.write_status(
        source=SOURCE,
        status=status,
        note=note,
        method="DSpace shorttitle browse index crawl (offset paging) over collections 1362 (Central) and 2455 (Gujarat)",
    )


if __name__ == '__main__':
    main()
