import os, asyncio, requests, urllib.parse
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

SMALL_TARGETS = {
    "ports_transport": ["https://pnt.gujarat.gov.in/pnt/default.aspx", "https://pnt.gujarat.gov.in/pnt/downloads/government-resolution.htm"],
    "food_civil_supplies": ["http://www.fcsca.gujarat.gov.in", "http://www.fcsca.gujarat.gov.in/gr-circular.htm"],
    "roads_buildings": ["http://rnbgujarat.org", "http://rnbgujarat.org/downloads.htm"]
}

async def inspect_small_depts():
    print("=== INSPECTING SUB-PAGES OF SMALL DEPARTMENTS ===")
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=['--ignore-certificate-errors', '--no-sandbox'])
        page = await browser.new_page()
        
        for name, urls in SMALL_TARGETS.items():
            print(f"\nTargeting [{name}]:")
            all_pdfs = set()
            for url in urls:
                try:
                    await page.goto(url, wait_until='domcontentloaded', timeout=15000)
                    await page.wait_for_timeout(1500)
                    links = await page.evaluate('''() => {
                        return Array.from(document.querySelectorAll('a')).map(a => a.href).filter(h => h && h.toLowerCase().includes('.pdf'));
                    }''')
                    for l in links:
                        all_pdfs.add(l)
                except Exception as e:
                    print(f"  Url {url} note: {str(e)[:60]}")
            print(f" -> Total PDFs available on [{name}]: {len(all_pdfs)}")
            
        await browser.close()

if __name__ == '__main__':
    asyncio.run(inspect_small_depts())
