import os, sys, asyncio, requests, urllib.parse
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

BASE_RAW_DIR = "/home/surdeep/Documents/K.A.N.A.D/production_pipeline/pdf_raw"

# Remaining high-value portals with deeper path targeting
TARGETS = {
    "sports_youth": "https://sycd.gujarat.gov.in/gr-circular.htm",
    "urban_dev": "https://ududh.gujarat.gov.in/government-resolution.htm",
    "social_justice": "https://sje.gujarat.gov.in/gr.htm",
    "agri_cooperation": "http://agri.gujarat.gov.in/government-resolutions.htm",
    "education": "https://education.gujarat.gov.in/government-resolutions.htm",
    "energy_petro": "https://epd.gujarat.gov.in/gr.htm",
    "narmada_water": "https://guj-nwrws.gujarat.gov.in/gr.htm",
    "health_family_welfare": "https://gujhealth.gujarat.gov.in/gr.htm"
}

def is_valid_pdf(content):
    return len(content) > 1000 and content.startswith(b'%PDF')

def fetch_and_save(url, dest_path):
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

async def main():
    print("=== SCRAPING DEEP PATH TARGETS FOR REMAINING DEPARTMENTS ===")
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=['--ignore-certificate-errors', '--no-sandbox'])
        page = await browser.new_page()
        
        for name, url in TARGETS.items():
            dest_dir = os.path.join(BASE_RAW_DIR, name)
            os.makedirs(dest_dir, exist_ok=True)
            print(f"\nScanning [{name}] -> {url}")
            pdf_links = set()
            try:
                await page.goto(url, wait_until='load', timeout=25000)
                await page.wait_for_timeout(2000)
                found = await page.evaluate('''() => {
                    return Array.from(document.querySelectorAll('a')).map(a => a.href).filter(h => h && h.includes('.pdf'));
                }''')
                for link in found:
                    pdf_links.add(link)
            except Exception as e:
                print(f"  Note for {name}: {str(e)[:70]}")
                
            print(f" Found {len(pdf_links)} PDF links for [{name}]")
            saved = 0
            for idx, p_url in enumerate(pdf_links):
                dest = os.path.join(dest_dir, f"{name}_deep_{idx+1:03d}.pdf")
                if fetch_and_save(p_url, dest):
                    saved += 1
            print(f" Saved {saved} verified PDFs for [{name}]")
            
        await browser.close()

if __name__ == '__main__':
    asyncio.run(main())
