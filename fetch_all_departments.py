import os, sys, asyncio, requests, urllib.parse
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

BASE_RAW_DIR = "/home/surdeep/Documents/K.A.N.A.D/production_pipeline/pdf_raw"

# Confirmed Official Department URLs
DEPARTMENTS = {
    "agri_cooperation": "http://agri.gujarat.gov.in",
    "climate_change": "https://ccd.gujarat.gov.in",
    "education": "http://gujarat-education.gov.in",
    "energy_petro": "http://guj-epd.gov.in",
    "finance_alt": "http://financedepartment.gujarat.gov.in",
    "food_civil_supplies": "http://www.fcsca.gujarat.gov.in",
    "forest_environment": "http://gujenvfor.gswan.gov.in",
    "gad_personnel": "https://gad.gujarat.gov.in/Personnel/",
    "health_family_welfare": "http://www.gujhealth.gov.in",
    "home_department": "http://home.gujarat.gov.in/homedepartment/default.aspx",
    "industries_mines": "http://imd-gujarat.gov.in",
    "info_broadcasting": "http://www.gujaratinformation.net",
    "labour_employment": "https://labour.gujarat.gov.in",
    "legal_department": "http://www.gujlegal.gov.in",
    "legislative_parliamentary": "http://lpd.gujarat.gov.in",
    "narmada_water": "https://guj-nwrws.gujarat.gov.in",
    "panchayat_rural_housing": "https://panchayat.gujarat.gov.in",
    "ports_transport": "https://pnt.gujarat.gov.in",
    "revenue_circulars": "https://revenuedepartment.gujarat.gov.in/circulars",
    "roads_buildings": "http://rnbgujarat.org",
    "rural_dev": "http://ruraldev.gujarat.gov.in",
    "social_justice": "http://www.sje.gujarat.gov.in",
    "sports_youth": "https://sycd.gujarat.gov.in",
    "urban_dev": "https://ududh.gujarat.gov.in",
    "women_child_dev": "https://wcd.gujarat.gov.in"
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

async def scrape_dept(dept_key, url, page):
    dest_dir = os.path.join(BASE_RAW_DIR, dept_key)
    os.makedirs(dest_dir, exist_ok=True)
    print(f"\n==========================================")
    print(f"DEPARTMENT SCRAPING: [{dept_key}] -> {url}")
    print(f"==========================================")
    
    pdf_links = set()
    
    # Pass 1: Direct HTTP Requests
    try:
        r = requests.get(url, verify=False, headers={'User-Agent': 'Mozilla/5.0'}, timeout=15)
        if r.status_code == 200:
            soup = BeautifulSoup(r.text, 'html.parser')
            for a in soup.find_all('a'):
                href = a.get('href', '')
                if href and ('.pdf' in href.lower() or 'download' in href.lower() or 'upload' in href.lower()):
                    pdf_links.add(urllib.parse.urljoin(url, href))
    except Exception:
        pass

    # Pass 2: Playwright for JS/Dynamic DOM Rendering
    if len(pdf_links) < 5:
        try:
            print(f"  Attempting Playwright JS Render for [{dept_key}]...")
            await page.goto(url, wait_until='load', timeout=25000)
            await page.wait_for_timeout(2500)
            found = await page.evaluate('''() => {
                return Array.from(document.querySelectorAll('a')).map(a => a.href).filter(h => h && (h.includes('.pdf') || h.includes('upload') || h.includes('download')));
            }''')
            for f_link in found:
                pdf_links.add(f_link)
        except Exception as e:
            print(f"  Playwright note: {str(e)[:70]}")

    print(f" Found {len(pdf_links)} total candidate PDF links for [{dept_key}]")
    
    downloaded = 0
    for idx, p_url in enumerate(list(pdf_links)):
        fname = f"{dept_key}_doc_{idx+1:03d}.pdf"
        filepath = os.path.join(dest_dir, fname)
        if fetch_and_save(p_url, filepath):
            downloaded += 1
            if downloaded % 5 == 0 or downloaded == len(pdf_links):
                print(f"  [{downloaded}/{len(pdf_links)}] Downloaded & Verified -> {fname} ({os.path.getsize(filepath)} bytes)")
                
    print(f"=== COMPLETED [{dept_key}]: Saved {downloaded} verified PDFs in {dest_dir} ===")
    return downloaded

async def main():
    print("=== STARTING FULL GUJARAT ALL-DEPARTMENT BULK PDF FETCH ===")
    os.makedirs(BASE_RAW_DIR, exist_ok=True)
    
    total = 0
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=['--ignore-certificate-errors', '--no-sandbox'])
        context = await browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64)")
        page = await context.new_page()
        
        for dept_key, url in DEPARTMENTS.items():
            cnt = await scrape_dept(dept_key, url, page)
            total += cnt
            
        await browser.close()
        
    print(f"\n==========================================")
    print(f"ALL-DEPARTMENT FETCH COMPLETE! Total Verified PDFs Saved across all subfolders: {total}")
    print(f"==========================================")

if __name__ == '__main__':
    asyncio.run(main())
