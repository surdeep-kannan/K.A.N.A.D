import os, asyncio
from playwright.async_api import async_playwright

BASE_RAW_DIR = "/home/surdeep/Documents/K.A.N.A.D/production_pipeline/pdf_raw"
DEST_DIR = os.path.join(BASE_RAW_DIR, "egazette_central")
os.makedirs(DEST_DIR, exist_ok=True)

def is_valid_pdf(content):
    return len(content) > 1000 and content.startswith(b'%PDF')

async def main():
    print("=== MONITORING NETWORK REQUESTS UPON EGAZETTE CLICK ===")
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=['--ignore-certificate-errors', '--no-sandbox'])
        context = await browser.new_context()
        page = await context.new_page()
        
        pdf_urls_caught = []
        
        page.on("response", lambda res: pdf_urls_caught.append(res.url) if ".pdf" in res.url.lower() or "pdf" in res.headers.get("content-type", "").lower() else None)
        
        try:
            await page.goto("https://egazette.gov.in/Default.aspx", wait_until='domcontentloaded')
            await page.wait_for_timeout(2000)
            
            btn = page.locator('input[src*="download-pdf.png"]').first
            print("Clicking download button and inspecting network traffic...")
            await btn.click()
            await page.wait_for_timeout(5000)
            
            print(f"Network responses caught with PDF: {pdf_urls_caught}")
            
            # Check frame contents or redirected URLs
            frames = page.frames
            print(f"Total frames on page: {len(frames)}")
            for idx, f in enumerate(frames):
                print(f" Frame {idx}: {f.url}")
                
        except Exception as e:
            print(f"  Note: {e}")
            
        await browser.close()

if __name__ == '__main__':
    asyncio.run(main())
