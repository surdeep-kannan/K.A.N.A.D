import os, asyncio, requests, urllib.parse
from playwright.async_api import async_playwright

BASE_RAW_DIR = "/home/surdeep/Documents/K.A.N.A.D/production_pipeline/pdf_raw"

# Targets that failed previously
FAILED_PORTALS = {
    "agri_cooperation": "http://agri.gujarat.gov.in",
    "education": "https://education.gujarat.gov.in",
    "energy_petro": "https://epd.gujarat.gov.in",
    "forest_environment": "http://gujenvfor.gswan.gov.in",
    "health_family_welfare": "https://gujhealth.gujarat.gov.in",
    "industries_mines": "http://imd-gujarat.gov.in",
    "narmada_water": "https://guj-nwrws.gujarat.gov.in",
    "sports_youth": "https://sycd.gujarat.gov.in",
    "urban_dev": "https://ududh.gujarat.gov.in"
}

def is_valid_pdf(content):
    return len(content) > 1000 and content.startswith(b'%PDF')

def save_pdf(url, filepath):
    try:
        r = requests.get(url, verify=False, headers={'User-Agent': 'Mozilla/5.0'}, timeout=15)
        if r.status_code == 200 and is_valid_pdf(r.content):
            with open(filepath, 'wb') as f:
                f.write(r.content)
            return True
    except Exception:
        pass
    return False

async def main():
    print("=== PLAYWRIGHT RETRY FOR FAILED/EMPTY PORTALS ===")
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=['--ignore-certificate-errors', '--no-sandbox'])
        context = await browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
        page = await context.new_page()
        
        for name, base_url in FAILED_PORTALS.items():
            dest_dir = os.path.join(BASE_RAW_DIR, name)
            os.makedirs(dest_dir, exist_ok=True)
            print(f"\n[RETRY] Testing Playwright Browser on [{name}] -> {base_url}")
            pdf_urls = set()
            try:
                # Try navigating with explicit wait and timeout handling
                await page.goto(base_url, wait_until='networkidle', timeout=20000)
                await page.wait_for_timeout(3000)
                
                # Evaluate links inside frames and main DOM
                found = await page.evaluate('''() => {
                    let urls = [];
                    document.querySelectorAll('a').forEach(a => { if (a.href) urls.push(a.href); });
                    document.querySelectorAll('iframe, frame').forEach(f => {
                        try {
                            f.contentDocument.querySelectorAll('a').forEach(a => { if (a.href) urls.push(a.href); });
                        } catch(e) {}
                    });
                    return urls.filter(u => u.toLowerCase().includes('.pdf') || u.toLowerCase().includes('download'));
                }''')
                for u in found:
                    pdf_urls.add(u)
                print(f"  [SUCCESS] Connected to {name}. Found {len(pdf_urls)} PDF links.")
            except Exception as e:
                print(f"  [BLOCKED/TIMEOUT] {name} failed Playwright navigation: {str(e)[:80]}")
                
            saved = 0
            for idx, p_url in enumerate(pdf_urls):
                filepath = os.path.join(dest_dir, f"{name}_pw_{idx+1:03d}.pdf")
                if save_pdf(p_url, filepath):
                    saved += 1
            print(f"  Saved {saved} verified PDFs for [{name}].")
            
        await browser.close()

if __name__ == '__main__':
    asyncio.run(main())
