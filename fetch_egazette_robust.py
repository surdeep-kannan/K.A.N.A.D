import os, asyncio
from playwright.async_api import async_playwright

BASE_RAW_DIR = "/home/surdeep/Documents/K.A.N.A.D/production_pipeline/pdf_raw"
DEST_DIR = os.path.join(BASE_RAW_DIR, "egazette_central")
os.makedirs(DEST_DIR, exist_ok=True)

def is_valid_pdf(content):
    return len(content) > 1000 and content.startswith(b'%PDF')

async def main():
    print("=== EXECUTING ROBUST PLAYWRIGHT EGAZETTE DOWNLOAD RETRY ===")
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=['--ignore-certificate-errors', '--no-sandbox'])
        context = await browser.new_context(accept_downloads=True)
        page = await context.new_page()
        
        try:
            await page.goto("https://egazette.gov.in/Default.aspx", wait_until='networkidle', timeout=25000)
            await page.wait_for_timeout(2000)
            
            # Count elements dynamically
            count = await page.locator('input[src*="download-pdf.png"]').count()
            print(f"Found {count} dynamic download buttons on page.")
            
            saved = 0
            for i in range(count):
                try:
                    await page.goto("https://egazette.gov.in/Default.aspx", wait_until='domcontentloaded')
                    await page.wait_for_timeout(1000)
                    btn = page.locator('input[src*="download-pdf.png"]').nth(i)
                    
                    async with page.expect_download(timeout=12000) as download_info:
                        await btn.click()
                    download = await download_info.value
                    dest_path = os.path.join(DEST_DIR, f"central_gazette_{i+1:03d}_{download.suggested_filename}")
                    await download.save_as(dest_path)
                    
                    with open(dest_path, 'rb') as f:
                        data = f.read()
                    if is_valid_pdf(data):
                        saved += 1
                        print(f"  [✓] [{saved}/{count}] Saved -> {os.path.basename(dest_path)} ({len(data)} bytes)")
                    else:
                        os.remove(dest_path)
                except Exception as e:
                    print(f"  Button {i+1} note: {str(e)[:60]}")
                    
            print(f"\n==========================================")
            print(f"TOTAL VERIFIED PLAYWRIGHT DOWNLOADS SAVED: {saved}")
            print(f"==========================================")
            
        except Exception as e:
            print(f"Page load error: {e}")
            
        await browser.close()

if __name__ == '__main__':
    asyncio.run(main())
