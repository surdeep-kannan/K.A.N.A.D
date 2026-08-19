import os, sys, asyncio, re, requests, urllib.parse
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

BASE_RAW_DIR = "/home/surdeep/Documents/K.A.N.A.D/production_pipeline/pdf_raw"

# Define source directories
SOURCES = {
    "home_department": "https://home.gujarat.gov.in/homedepartment/CMS.aspx?content_id=41",
    "gad_personnel": "https://gad.gujarat.gov.in/Personnel/",
    "gad_planning": "https://planning.gujarat.gov.in/govt-resolution.htm",
    "gad_admin_reforms": "https://artd.gujarat.gov.in/government-resolution.htm",
    "gad_nri": "https://nri.gujarat.gov.in/gr.htm",
    "revenue_department": "https://revenuedepartment.gujarat.gov.in/rules-and-regulations",
    "finance_department": "https://financedepartment.gujarat.gov.in/Documents/",
    "egazette_state": "https://egazette.gujarat.gov.in/RecentGazette.aspx",
    "gujarat_police": "https://police.gujarat.gov.in/dgp/default.aspx",
    "mha_central": "https://www.mha.gov.in/en/notifications/circulars",
    "india_code": "https://www.indiacode.nic.in/",
    "egazette_central": "https://egazette.gov.in/",
    "ecourts": "https://services.ecourts.gov.in/ecourtindia_v6/"
}

def is_valid_pdf(content):
    return len(content) > 1000 and content.startswith(b'%PDF')

def download_sync(url, dest_path):
    if os.path.exists(dest_path) and os.path.getsize(dest_path) > 1000:
        return True
    try:
        r = requests.get(url, verify=False, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}, timeout=20)
        if r.status_code == 200 and is_valid_pdf(r.content):
            with open(dest_path, 'wb') as f:
                f.write(r.content)
            return True
    except Exception:
        pass
    return False

async def scrape_source(name, url, page):
    target_dir = os.path.join(BASE_RAW_DIR, name)
    os.makedirs(target_dir, exist_ok=True)
    print(f"\n==========================================")
    print(f"SCRAPING SOURCE: [{name}] -> {url}")
    print(f"==========================================")
    
    downloaded = 0
    pdf_urls = set()
    
    # 1. First Attempt: Static Requests
    try:
        r = requests.get(url, verify=False, headers={'User-Agent': 'Mozilla/5.0'}, timeout=15)
        if r.status_code == 200:
            soup = BeautifulSoup(r.text, 'html.parser')
            for a in soup.find_all('a'):
                href = a.get('href', '')
                if href and ('.pdf' in href.lower() or 'download' in href.lower() or 'upload' in href.lower()):
                    pdf_urls.add(urllib.parse.urljoin(url, href))
    except Exception:
        pass

    # 2. Second Attempt: Playwright Headless Browser for JS/AJAX/Forms
    if len(pdf_urls) < 3:
        try:
            print(f" Using Playwright Browser Context for JS-Rendered Portal...")
            resp = await page.goto(url, wait_until='load', timeout=30000)
            await page.wait_for_timeout(3000)
            
            # Click buttons or forms if applicable
            try:
                submit_btn = await page.query_selector('input[type="submit"], button[type="submit"], .btn-search')
                if submit_btn:
                    await submit_btn.click()
                    await page.wait_for_timeout(3000)
            except Exception:
                pass
                
            discovered = await page.evaluate('''() => {
                return Array.from(document.querySelectorAll('a')).map(a => a.href).filter(h => h && (h.includes('.pdf') || h.includes('upload') || h.includes('download') || h.includes('Document')));
            }''')
            for u in discovered:
                pdf_urls.add(u)
        except Exception as e:
            print(f" Playwright Browser Error: {str(e)[:80]}")

    print(f" Found {len(pdf_urls)} potential PDF download links for [{name}]")
    
    # 3. Download & Validate %PDF Binary Header
    for idx, pdf_url in enumerate(list(pdf_urls)[:25]): # Cap at top 25 per source for efficiency
        fname = f"{name}_doc_{idx+1:02d}.pdf"
        dest = os.path.join(target_dir, fname)
        
        if download_sync(pdf_url, dest):
            print(f"  [SUCCESS {downloaded+1:02d}] Saved -> {fname} ({os.path.getsize(dest)} bytes)")
            downloaded += 1
            
    print(f"=== SUMMARY [{name}]: Successfully saved {downloaded} verified PDF files to {target_dir} ===")
    return downloaded

async def run_master_multi_portal_scraper():
    print("=== STARTING MASTER MULTI-PORTAL BULK PDF SCRAPER ===")
    os.makedirs(BASE_RAW_DIR, exist_ok=True)
    
    total_downloaded = 0
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=['--ignore-certificate-errors', '--no-sandbox'])
        context = await browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
        page = await context.new_page()
        
        for name, url in SOURCES.items():
            count = await scrape_source(name, url, page)
            total_downloaded += count
            
        await browser.close()
        
    print(f"\n==========================================")
    print(f"MASTER SCRAPE COMPLETE! Total Verified PDFs Acquired across all sources: {total_downloaded}")
    print(f"==========================================")

if __name__ == '__main__':
    asyncio.run(run_master_multi_portal_scraper())
