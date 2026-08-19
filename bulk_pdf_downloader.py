import os, sys, asyncio, re, requests, urllib.parse
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

BASE_RAW_DIR = "/home/surdeep/Documents/K.A.N.A.D/production_pipeline/pdf_raw"

# Unlimited high-yield targets
SOURCES = {
    "home_department": "https://home.gujarat.gov.in/homedepartment/CMS.aspx?content_id=41",
    "gad_personnel": "https://gad.gujarat.gov.in/Personnel/",
    "gad_planning": "https://planning.gujarat.gov.in/govt-resolution.htm",
    "gad_admin_reforms": "https://artd.gujarat.gov.in/government-resolution.htm",
    "egazette_state": "https://egazette.gujarat.gov.in/RecentGazette.aspx",
    "gujarat_police": "https://police.gujarat.gov.in/dgp/default.aspx",
    "mha_central": "https://www.mha.gov.in/en/notifications/circulars"
}

def is_valid_pdf(content):
    return len(content) > 1000 and content.startswith(b'%PDF')

def download_file(url, dest_path):
    if os.path.exists(dest_path) and os.path.getsize(dest_path) > 1000:
        return True
    try:
        r = requests.get(url, verify=False, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}, timeout=25)
        if r.status_code == 200 and is_valid_pdf(r.content):
            with open(dest_path, 'wb') as f:
                f.write(r.content)
            return True
    except Exception:
        pass
    return False

async def scrape_all_unlimited(name, url, page):
    target_dir = os.path.join(BASE_RAW_DIR, name)
    os.makedirs(target_dir, exist_ok=True)
    print(f"\n==========================================")
    print(f"BULK DOWNLOAD RUNNER: [{name}] -> {url}")
    print(f"==========================================")
    
    pdf_urls = set()
    
    # 1. Fetch links via Requests
    try:
        r = requests.get(url, verify=False, headers={'User-Agent': 'Mozilla/5.0'}, timeout=15)
        if r.status_code == 200:
            soup = BeautifulSoup(r.text, 'html.parser')
            for a in soup.find_all('a'):
                href = a.get('href', '')
                if href and ('.pdf' in href.lower() or 'upload' in href.lower() or 'download' in href.lower()):
                    pdf_urls.add(urllib.parse.urljoin(url, href))
    except Exception:
        pass

    # 2. Fetch via Playwright if needed
    if len(pdf_urls) < 5:
        try:
            await page.goto(url, wait_until='load', timeout=30000)
            await page.wait_for_timeout(3000)
            discovered = await page.evaluate('''() => {
                return Array.from(document.querySelectorAll('a')).map(a => a.href).filter(h => h && (h.includes('.pdf') || h.includes('upload') || h.includes('download')));
            }''')
            for u in discovered:
                pdf_urls.add(u)
        except Exception as e:
            print(f"  Playwright note: {str(e)[:60]}")

    print(f" Found {len(pdf_urls)} direct PDF links to download for [{name}]")
    
    downloaded = 0
    # Download ALL links found without artificial cap
    for idx, pdf_url in enumerate(list(pdf_urls)):
        fname = f"{name}_doc_{idx+1:03d}.pdf"
        dest = os.path.join(target_dir, fname)
        
        if download_file(pdf_url, dest):
            downloaded += 1
            if downloaded % 5 == 0 or downloaded == len(pdf_urls):
                print(f"  [{downloaded}/{len(pdf_urls)}] Downloaded -> {fname} ({os.path.getsize(dest)} bytes)")
            
    print(f"=== COMPLETED [{name}]: Total {downloaded} verified PDFs saved in {target_dir} ===")
    return downloaded

async def run_unlimited_downloader():
    print("=== STARTING UNLIMITED BULK PDF DOWNLOAD RUNNER ===")
    os.makedirs(BASE_RAW_DIR, exist_ok=True)
    
    total = 0
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=['--ignore-certificate-errors', '--no-sandbox'])
        context = await browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64)")
        page = await context.new_page()
        
        for name, url in SOURCES.items():
            count = await scrape_all_unlimited(name, url, page)
            total += count
            
        await browser.close()
        
    print(f"\n==========================================")
    print(f"UNLIMITED RUNNER COMPLETE! Total PDFs Saved across all subfolders: {total}")
    print(f"==========================================")

if __name__ == '__main__':
    asyncio.run(run_unlimited_downloader())
