import asyncio
import os
import aiohttp
from playwright.async_api import async_playwright

TARGET_URL = "https://home.gujarat.gov.in/homedepartment/CMS.aspx?content_id=41"
RAW_PDF_DIR = "/home/surdeep/Documents/K.A.N.A.D/production_pipeline/pdf_raw"

async def crawl_and_download_grs(max_docs=5):
    os.makedirs(RAW_PDF_DIR, exist_ok=True)
    print(f"=== LIVE GR PORTAL AUTOMATED SCRAPER STARTED ===")
    print(f"Crawling Resolutions & Orders Portal: {TARGET_URL}")
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=['--ignore-certificate-errors'])
        context = await browser.new_context(
            ignore_https_errors=True,
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        
        try:
            await page.goto(TARGET_URL, wait_until="load", timeout=60000)
            
            sub_links = await page.evaluate('''() => {
                return Array.from(document.querySelectorAll('a')).map(a => ({
                    text: a.innerText.trim(),
                    href: a.href
                }));
            }''')
            
            pdf_links = [l for l in sub_links if '.pdf' in l['href'].lower() or 'upload' in l['href'].lower()]
            print(f"Discovered {len(pdf_links)} total PDF resolution documents.")
            
            downloaded = 0
            async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=False)) as session:
                for idx, item in enumerate(pdf_links):
                    if downloaded >= max_docs:
                        break
                    pdf_url = item['href']
                    if not pdf_url.startswith('http'):
                        continue
                        
                    fname = f"scraped_live_gr_{downloaded+1:02d}.pdf"
                    dest_path = os.path.join(RAW_PDF_DIR, fname)
                    
                    print(f"[{downloaded+1}/{max_docs}] Downloading ({item['text'][:30]}...): {pdf_url}")
                    try:
                        async with session.get(pdf_url, headers={"User-Agent": "Mozilla/5.0"}) as resp:
                            if resp.status == 200:
                                with open(dest_path, 'wb') as f:
                                    f.write(await resp.read())
                                print(f"    Saved -> {dest_path}")
                                downloaded += 1
                    except Exception as e:
                        print(f"    Download Error: {e}")
                        
            print(f"\n=== SCRAPING COMPLETE: Saved {downloaded} live GRs to {RAW_PDF_DIR} ===")
        except Exception as e:
            print(f"Portal Navigation Error: {e}")
        finally:
            await browser.close()

if __name__ == '__main__':
    # Pure bulk PDF downloader - no DB or RAG execution
    asyncio.run(crawl_and_download_grs(max_docs=100))
