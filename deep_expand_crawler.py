import os, sys, asyncio, re, requests, urllib.parse
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

BASE_RAW_DIR = "/home/surdeep/Documents/K.A.N.A.D/production_pipeline/pdf_raw"

# Expanded Deep-Crawling Domain Targets & Aggregators
DEEP_TARGETS = {
    "sports_youth": "https://sycd.gujarat.gov.in/gr-circular.htm",
    "agri_cooperation": "http://agri.gujarat.gov.in/downloads/government-resolutions.htm",
    "narmada_water": "https://guj-nwrws.gujarat.gov.in/downloads/gr.htm",
    "gudm_urban_dev": "https://gudm.gujarat.gov.in/",
    "labour_deeper": "https://labour.gujarat.gov.in/downloads.htm",
    "panchayat_deeper": "https://panchayat.gujarat.gov.in/panchayatvibhag/english/index.htm",
    "women_child_deeper": "https://wcd.gujarat.gov.in/circulars.htm",
    "aggregator_gujaratgr": "http://gujaratgr.in/",
    "aggregator_grportal": "http://grportal.in/"
}

def is_valid_pdf(content):
    return len(content) > 1000 and content.startswith(b'%PDF')

def fetch_and_save(url, dest_path):
    if os.path.exists(dest_path) and os.path.getsize(dest_path) > 1000:
        return True
    try:
        r = requests.get(url, verify=False, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}, timeout=15)
        if r.status_code == 200 and is_valid_pdf(r.content):
            with open(dest_path, 'wb') as f:
                f.write(r.content)
            return True
    except Exception:
        pass
    return False

async def crawl_deep_links(name, base_url, page):
    dest_dir = os.path.join(BASE_RAW_DIR, name)
    os.makedirs(dest_dir, exist_ok=True)
    print(f"\n==========================================")
    print(f"DEEP CRAWLING TARGET: [{name}] -> {base_url}")
    print(f"==========================================")
    
    discovered_pdfs = set()
    subpages_to_visit = set([base_url])
    
    # 1. Discover Sub-pages containing GR / resolution / circular / ઠરાવ / પરિપત્ર
    try:
        await page.goto(base_url, wait_until='domcontentloaded', timeout=20000)
        await page.wait_for_timeout(2000)
        links = await page.evaluate('''() => {
            let res = { pdfs: [], subpages: [] };
            let keywords = ['resolution', 'circular', 'gr', 'download', 'ઠરાવ', 'પરિપત્ર', 'જાહેરાત'];
            document.querySelectorAll('a').forEach(a => {
                let href = a.href || '';
                let text = (a.innerText || '').toLowerCase();
                if (href.toLowerCase().includes('.pdf')) {
                    res.pdfs.push(href);
                } else if (keywords.some(kw => text.includes(kw) || href.toLowerCase().includes(kw))) {
                    res.subpages.push(href);
                }
            });
            return res;
        }''')
        
        for p in links.get('pdfs', []):
            discovered_pdfs.add(p)
        for sp in links.get('subpages', [])[:10]: # Visit top 10 subpages
            subpages_to_visit.add(sp)
            
    except Exception as e:
        print(f"  Note for root {name}: {str(e)[:70]}")
        
    print(f"  Subpages discovered for deep crawl: {len(subpages_to_visit)}")
    
    # 2. Crawl Subpages 1-level deep
    for sp_url in list(subpages_to_visit):
        if sp_url == base_url:
            continue
        try:
            await page.goto(sp_url, wait_until='domcontentloaded', timeout=15000)
            await page.wait_for_timeout(1500)
            found_pdfs = await page.evaluate('''() => {
                return Array.from(document.querySelectorAll('a')).map(a => a.href).filter(h => h && h.toLowerCase().includes('.pdf'));
            }''')
            for p in found_pdfs:
                discovered_pdfs.add(p)
        except Exception:
            pass
            
    print(f" Total PDF links collected for [{name}]: {len(discovered_pdfs)}")
    
    # 3. Download & Save Verified PDFs
    saved = 0
    for idx, pdf_url in enumerate(list(discovered_pdfs)):
        filepath = os.path.join(dest_dir, f"{name}_deep_{idx+1:03d}.pdf")
        if fetch_and_save(pdf_url, filepath):
            saved += 1
            if saved % 5 == 0 or saved == len(discovered_pdfs):
                print(f"  [{saved}/{len(discovered_pdfs)}] Saved -> {os.path.basename(filepath)}")
                
    print(f"=== COMPLETED [{name}]: Total {saved} new verified PDFs in {dest_dir} ===")
    return saved

async def main():
    print("=== STARTING DEEP-LEVEL MULTI-DEPARTMENT & AGGREGATOR EXPANSION ===")
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=['--ignore-certificate-errors', '--no-sandbox'])
        context = await browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64)")
        page = await context.new_page()
        
        total_new = 0
        for name, url in DEEP_TARGETS.items():
            cnt = await crawl_deep_links(name, url, page)
            total_new += cnt
            
        await browser.close()
        
    print(f"\n==========================================")
    print(f"DEEP CRAWL EXPANSION COMPLETE! Total New PDFs Added: {total_new}")
    print(f"==========================================")

if __name__ == '__main__':
    asyncio.run(main())
