import asyncio
import os
import aiohttp
import urllib.parse
from bs4 import BeautifulSoup

MAIN_PORTAL_URL = "https://home.gujarat.gov.in/homedepartment/CMS.aspx?content_id=41"
BASE_HOST = "https://home.gujarat.gov.in/homedepartment/"
RAW_PDF_DIR = "/home/surdeep/Documents/K.A.N.A.D/production_pipeline/pdf_raw"

async def download_file(session, pdf_url, dest_path, semaphore):
    async with semaphore:
        if os.path.exists(dest_path) and os.path.getsize(dest_path) > 0:
            return True # Skip already downloaded
        try:
            async with session.get(pdf_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=30) as resp:
                if resp.status == 200:
                    with open(dest_path, 'wb') as f:
                        f.write(await resp.read())
                    return True
        except Exception as e:
            pass
    return False

async def full_portal_bulk_scraper():
    os.makedirs(RAW_PDF_DIR, exist_ok=True)
    print("=== STARTING FULL PORTAL BULK SCRAPER (MAIN + ALL 92 SUB-SECTIONS) ===")
    
    semaphore = asyncio.Semaphore(15) # Concurrent downloads limit
    pdf_queue = {} # url -> filename
    
    # 1. Fetch Main Page (content_id=41)
    print(f"Fetching Main Resolutions Page: {MAIN_PORTAL_URL}")
    async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=False)) as session:
        try:
            async with session.get(MAIN_PORTAL_URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=60) as resp:
                html = await resp.text()
                soup = BeautifulSoup(html, 'html.parser')
                
                # Discover all sub-sections
                sub_sections = set()
                for a in soup.find_all('a'):
                    href = a.get('href', '')
                    if href:
                        full_url = urllib.parse.urljoin(BASE_HOST, href)
                        if '.pdf' in href.lower() or 'upload' in href.lower():
                            fname = os.path.basename(urllib.parse.urlparse(full_url).path)
                            if fname:
                                pdf_queue[full_url] = fname
                        elif 'CMS.aspx' in href:
                            sub_sections.add(full_url)
                            
                print(f"Main Page Ingested: Discovered {len(pdf_queue)} direct PDFs and {len(sub_sections)} sub-sections.")
                
                # 2. Crawl all 92 Sub-sections recursively
                print(f"\nCrawling all {len(sub_sections)} sub-sections...")
                for idx, sub_url in enumerate(sub_sections):
                    try:
                        async with session.get(sub_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=20) as sub_resp:
                            if sub_resp.status == 200:
                                sub_html = await sub_resp.text()
                                sub_soup = BeautifulSoup(sub_html, 'html.parser')
                                sub_pdfs = 0
                                for a in sub_soup.find_all('a'):
                                    href = a.get('href', '')
                                    if href and ('.pdf' in href.lower() or 'upload' in href.lower()):
                                        full_pdf = urllib.parse.urljoin(sub_url, href)
                                        fname = os.path.basename(urllib.parse.urlparse(full_pdf).path)
                                        if fname and full_pdf not in pdf_queue:
                                            pdf_queue[full_pdf] = fname
                                            sub_pdfs += 1
                                if (idx + 1) % 10 == 0 or idx == len(sub_sections) - 1:
                                    print(f" [{idx+1}/{len(sub_sections)}] Crawled {sub_url[:60]}... Total unique PDFs queued: {len(pdf_queue)}")
                    except Exception:
                        continue
                        
        except Exception as e:
            print(f"Error initializing portal crawl: {e}")
            return

        # 3. Bulk Parallel Download of ALL queued PDFs
        print(f"\n=== STARTING PARALLEL BULK DOWNLOAD OF {len(pdf_queue)} UNIQUE PDF DOCUMENTS ===")
        tasks = []
        download_count = 0
        
        for url, orig_fname in pdf_queue.items():
            download_count += 1
            # Clean filename
            clean_name = f"portal_gr_{download_count:04d}_{orig_fname}"
            dest = os.path.join(RAW_PDF_DIR, clean_name)
            tasks.append(download_file(session, url, dest, semaphore))
            
        results = await asyncio.gather(*tasks)
        successful = sum(1 for r in results if r)
        print(f"\n=== FULL PORTAL BULK SCRAPE COMPLETE ===")
        print(f"Successfully downloaded & saved {successful} / {len(pdf_queue)} total PDF documents to: {RAW_PDF_DIR}")

if __name__ == '__main__':
    asyncio.run(full_portal_bulk_scraper())
