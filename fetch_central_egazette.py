import os, sys, requests, urllib.parse
from bs4 import BeautifulSoup

BASE_RAW_DIR = "/home/surdeep/Documents/K.A.N.A.D/production_pipeline/pdf_raw"
DEST_DIR = os.path.join(BASE_RAW_DIR, "egazette_central")

def is_valid_pdf(content):
    return len(content) > 1000 and content.startswith(b'%PDF')

def fetch_central_egazette():
    os.makedirs(DEST_DIR, exist_ok=True)
    print("=== EXECUTING CENTRAL EGAZETTE ACQUISITION (egazette.gov.in) ===\n")
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8'
    }
    
    urls_to_scan = [
        "https://egazette.gov.in/",
        "https://egazette.gov.in/Default.aspx",
        "https://egazette.gov.in/RecentExtraOrdinaryGazette.aspx",
        "https://egazette.gov.in/RecentWeeklyGazette.aspx",
        "https://egazette.gov.in/SearchGazette.aspx"
    ]
    
    pdf_urls = set()
    
    for url in urls_to_scan:
        print(f"Scanning target endpoint: {url}")
        try:
            r = requests.get(url, headers=headers, verify=False, timeout=15)
            if r.status_code == 200:
                soup = BeautifulSoup(r.text, 'html.parser')
                links = soup.find_all('a', href=True)
                page_count = 0
                for a in links:
                    href = a['href']
                    if '.pdf' in href.lower() or 'writereaddata' in href.lower() or 'download' in href.lower():
                        full_url = urllib.parse.urljoin(url, href)
                        if full_url.lower().endswith('.pdf') or 'download' in full_url.lower():
                            pdf_urls.add(full_url)
                            page_count += 1
                print(f"  -> Found {page_count} PDF/download links on {url}")
            else:
                print(f"  -> HTTP Status {r.status_code} for {url}")
        except Exception as e:
            print(f"  -> Exception scanning {url}: {e}")

    print(f"\n==========================================")
    print(f"TOTAL UNIQUE CENTRAL EGAZETTE LINKS DISCOVERED: {len(pdf_urls)}")
    print(f"==========================================")
    
    saved_count = 0
    for idx, pdf_url in enumerate(list(pdf_urls)):
        filename = os.path.basename(urllib.parse.urlparse(pdf_url).path)
        if not filename or not filename.endswith('.pdf'):
            filename = f"central_gazette_{idx+1:03d}.pdf"
            
        dest_path = os.path.join(DEST_DIR, filename)
        
        if os.path.exists(dest_path) and os.path.getsize(dest_path) > 1000:
            saved_count += 1
            continue
            
        try:
            res = requests.get(pdf_url, headers=headers, verify=False, timeout=15)
            if res.status_code == 200 and is_valid_pdf(res.content):
                with open(dest_path, 'wb') as f:
                    f.write(res.content)
                saved_count += 1
                print(f"  [{saved_count}/{len(pdf_urls)}] Saved -> {os.path.basename(dest_path)} ({len(res.content)} bytes)")
        except Exception:
            pass
            
    print(f"\n=== COMPLETED CENTRAL EGAZETTE ACQUISITION: {saved_count} VERIFIED PDFs IN {DEST_DIR} ===")

if __name__ == '__main__':
    fetch_central_egazette()
