import os, asyncio
from playwright.async_api import async_playwright

BASE_RAW_DIR = "/home/surdeep/Documents/K.A.N.A.D/production_pipeline/pdf_raw"
DEST_DIR = os.path.join(BASE_RAW_DIR, "egazette_central")
os.makedirs(DEST_DIR, exist_ok=True)

def is_valid_pdf(content):
    return len(content) > 1000 and content.startswith(b'%PDF')

async def main():
    print("=== EXECUTING NEW-TAB POPUP INTERCEPTION FOR EGAZETTE ===")
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=['--ignore-certificate-errors', '--no-sandbox'])
        context = await browser.new_context(accept_downloads=True)
        page = await context.new_page()
        
        try:
            await page.goto("https://egazette.gov.in/Default.aspx", wait_until='domcontentloaded')
            await page.wait_for_timeout(2000)
            
            btn = page.locator('input[src*="download-pdf.png"]').first
            print("Clicking download button and expecting page/popup event...")
            
            async with page.expect_popup(timeout=8000) as popup_info:
                await btn.click()
            popup = await popup_info.value
            print(f"  [✓] New Tab Opened! URL: {popup.url}")
            
            res = await popup.request.get(popup.url)
            body = await res.body()
            if is_valid_pdf(body):
                dest_path = os.path.join(DEST_DIR, "central_gazette_popup_001.pdf")
                with open(dest_path, 'wb') as f:
                    f.write(body)
                print(f"  [✓] Successfully saved popup PDF: {dest_path} ({len(body)} bytes)")
        except Exception as e:
            print(f"  Popup interception note: {e}")
            
        await browser.close()

if __name__ == '__main__':
    asyncio.run(main())
