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

async def main():
    dest_dir = os.path.join(BASE_RAW_DIR, "mha_central")
    os.makedirs(dest_dir, exist_ok=True)
    print("=== TARGETED MHA JS CLICK & MODAL INTERACTION RETRY ===")
    
    url = "https://www.mha.gov.in/en/notifications/circulars"
    pdf_urls = set()
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=['--ignore-certificate-errors', '--no-sandbox'])
        page = await browser.new_page()
        try:
            await page.goto(url, wait_until='networkidle', timeout=25000)
            await page.wait_for_timeout(3000)
            
            # Click modal/table buttons to trigger dynamic JS actions
            print("  Attempting to click dynamic rows and modal links on MHA page...")
            rows = await page.query_selector_all('tbody tr, .view-content .views-row, a[href*="javascript"], button')
            print(f"  Found {len(rows)} interactive table rows/buttons on page.")
            
            for row in rows[:15]:
                try:
                    await row.click(timeout=1000)
                    await page.wait_for_timeout(500)
                except Exception:
                    pass
                    
            # Extract PDF anchors after click interactions
            found = await page.evaluate('''() => {
                let list = [];
                document.querySelectorAll('a, [onclick]').forEach(el => {
                    let href = el.href || el.getAttribute('onclick') || '';
                    if (href && (href.toLowerCase().includes('.pdf') || href.toLowerCase().includes('download'))) {
                        list.push(href);
                    }
                });
                return list;
            }''')
            for f in found:
                pdf_urls.add(f)
                
            print(f"  Result after click interaction: Found {len(pdf_urls)} PDF links.")
        except Exception as e:
            print(f"  [MHA Click Attempt Note]: {str(e)[:80]}")
            
        await browser.close()
        
    saved = 0
    for idx, p_url in enumerate(list(pdf_urls)):
        dest = os.path.join(dest_dir, f"mha_modal_{idx+1:03d}.pdf")
        if save_pdf(p_url, dest):
            saved += 1
            
    print(f"=== MHA RETRY FINAL RESULT: Saved {saved} verified PDFs ===")

if __name__ == '__main__':
    asyncio.run(main())
