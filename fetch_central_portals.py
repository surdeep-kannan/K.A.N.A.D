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

async def fetch_mha():
    dest_dir = os.path.join(BASE_RAW_DIR, "mha_central")
    os.makedirs(dest_dir, exist_ok=True)
    print("\n=== 1. FETCHING MHA CENTRAL (mha.gov.in) ===")
    
    pdf_urls = set()
    url = "https://www.mha.gov.in/en/notifications/circulars"
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=['--ignore-certificate-errors', '--no-sandbox'])
        page = await browser.new_page()
        try:
            await page.goto(url, wait_until='domcontentloaded', timeout=20000)
            await page.wait_for_timeout(2000)
            found = await page.evaluate('''() => {
                return Array.from(document.querySelectorAll('a')).map(a => a.href).filter(h => h && h.toLowerCase().includes('.pdf'));
            }''')
            for f in found:
                pdf_urls.add(f)
            print(f"  [MHA] Discovered {len(pdf_urls)} PDF links on notifications/circulars page.")
        except Exception as e:
            print(f"  [MHA Note]: {str(e)[:80]}")
        await browser.close()
        
    saved = 0
    for idx, p_url in enumerate(list(pdf_urls)):
        dest = os.path.join(dest_dir, f"mha_doc_{idx+1:03d}.pdf")
        if save_pdf(p_url, dest):
            saved += 1
    print(f"=== COMPLETED MHA: Saved {saved} verified PDFs in {dest_dir} ===")
    return saved

async def fetch_egazette_central():
    dest_dir = os.path.join(BASE_RAW_DIR, "egazette_central")
    os.makedirs(dest_dir, exist_ok=True)
    print("\n=== 2. RETRYING CENTRAL EGAZETTE (egazette.gov.in) VIA PLAYWRIGHT ===")
    
    url = "https://egazette.gov.in"
    status = "BLOCKED"
    saved = 0
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=['--ignore-certificate-errors', '--no-sandbox'])
        page = await browser.new_page()
        try:
            response = await page.goto(url, wait_until='networkidle', timeout=25000)
            print(f"  [Central eGazette HTTP Status]: {response.status if response else 'No Response'}")
            if response and response.status == 200:
                print("  [SUCCESS] Central eGazette page accessible!")
                status = "ACCESSIBLE"
            else:
                print(f"  [BLOCKED] Status {response.status if response else 'Timeout'}")
        except Exception as e:
            print(f"  [BLOCKED/RATE-LIMITED]: {str(e)[:80]}")
        await browser.close()
        
    print(f"=== COMPLETED CENTRAL EGAZETTE: Final Status -> {status} (Saved {saved} PDFs) ===")
    return saved

async def fetch_india_code():
    dest_dir = os.path.join(BASE_RAW_DIR, "india_code")
    os.makedirs(dest_dir, exist_ok=True)
    print("\n=== 3. RETRYING INDIA CODE (indiacode.nic.in) VIA PLAYWRIGHT ===")
    
    url = "https://www.indiacode.nic.in"
    status = "BLOCKED"
    saved = 0
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=['--ignore-certificate-errors', '--no-sandbox'])
        page = await browser.new_page()
        try:
            response = await page.goto(url, wait_until='domcontentloaded', timeout=25000)
            print(f"  [India Code HTTP Status]: {response.status if response else 'No Response'}")
            if response and response.status == 200:
                print("  [SUCCESS] India Code portal accessible!")
                status = "ACCESSIBLE"
            else:
                print(f"  [BLOCKED/WAF] Status {response.status if response else 'Timeout'}")
        except Exception as e:
            print(f"  [BLOCKED/WAF]: {str(e)[:80]}")
        await browser.close()
        
    print(f"=== COMPLETED INDIA CODE: Final Status -> {status} (Saved {saved} PDFs) ===")
    return saved

async def main():
    print("=== EXECUTING CENTRAL PORTALS & REMAINING RETRIES ===")
    await fetch_mha()
    await fetch_egazette_central()
    await fetch_india_code()

if __name__ == '__main__':
    asyncio.run(main())
