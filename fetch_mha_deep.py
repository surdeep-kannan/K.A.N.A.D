import os, asyncio, requests, urllib.parse
from playwright.async_api import async_playwright

BASE_RAW_DIR = "/home/surdeep/Documents/K.A.N.A.D/production_pipeline/pdf_raw"

def is_valid_pdf(content):
    return len(content) > 1000 and content.startswith(b'%PDF')

def save_pdf(url, filepath):
    try:
        r = requests.get(url, verify=False, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}, timeout=15)
        if r.status_code == 200 and is_valid_pdf(r.content):
            with open(filepath, 'wb') as f:
                f.write(r.content)
            return True
    except Exception:
        pass
    return False

async def fetch_mha_deep():
    dest_dir = os.path.join(BASE_RAW_DIR, "mha_central")
    os.makedirs(dest_dir, exist_ok=True)
    print("\n=== DEEP FETCHING MHA CENTRAL NOTIFICATIONS & CIRCULARS ===")
    
    urls = [
        "https://www.mha.gov.in/en/notifications/circulars",
        "https://www.mha.gov.in/en/common-circulars",
        "https://www.mha.gov.in/en/document-reports"
    ]
    
    pdf_urls = set()
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=['--ignore-certificate-errors', '--no-sandbox'])
        page = await browser.new_page()
        for u in urls:
            try:
                await page.goto(u, wait_until='domcontentloaded', timeout=15000)
                await page.wait_for_timeout(2000)
                found = await page.evaluate('''() => {
                    return Array.from(document.querySelectorAll('a')).map(a => a.href).filter(h => h && (h.toLowerCase().includes('.pdf') || h.toLowerCase().includes('download')));
                }''')
                for f in found:
                    pdf_urls.add(f)
            except Exception as e:
                print(f"  Note for MHA {u}: {str(e)[:60]}")
        await browser.close()
        
    print(f" Total PDF links collected for [mha_central]: {len(pdf_urls)}")
    saved = 0
    for idx, p_url in enumerate(list(pdf_urls)):
        dest = os.path.join(dest_dir, f"mha_doc_{idx+1:03d}.pdf")
        if save_pdf(p_url, dest):
            saved += 1
            print(f"  [{saved}/{len(pdf_urls)}] Saved -> {os.path.basename(dest)} ({os.path.getsize(dest)} bytes)")
            
    print(f"=== COMPLETED MHA CENTRAL: Saved {saved} verified PDFs in {dest_dir} ===")
    return saved

if __name__ == '__main__':
    asyncio.run(fetch_mha_deep())
