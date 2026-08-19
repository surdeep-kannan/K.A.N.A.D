import os, asyncio
from playwright.async_api import async_playwright

BASE_RAW_DIR = "/home/surdeep/Documents/K.A.N.A.D/production_pipeline/pdf_raw"
DEST_DIR = os.path.join(BASE_RAW_DIR, "egazette_central")
os.makedirs(DEST_DIR, exist_ok=True)

def is_valid_pdf(content):
    return len(content) > 1000 and content.startswith(b'%PDF')

async def main():
    print("=== EXECUTING PLAYWRIGHT ROUTE INTERCEPTION FOR CENTRAL EGAZETTE ===")
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=['--ignore-certificate-errors', '--no-sandbox'])
        context = await browser.new_context()
        page = await context.new_page()
        
        pdf_binaries = []
        
        async def handle_response(response):
            try:
                ct = response.headers.get("content-type", "").lower()
                cd = response.headers.get("content-disposition", "").lower()
                if "application/pdf" in ct or ".pdf" in response.url.lower() or "attachment" in cd:
                    body = await response.body()
                    if is_valid_pdf(body):
                        pdf_binaries.append((response.url, body))
                        print(f"  [✓] Caught PDF binary response! ({len(body)} bytes) -> URL: {response.url[:60]}")
            except Exception:
                pass
                
        page.on("response", handle_response)
        
        try:
            await page.goto("https://egazette.gov.in/Default.aspx", wait_until='networkidle', timeout=25000)
            await page.wait_for_timeout(2000)
            
            buttons = page.locator('input[src*="download-pdf.png"]')
            count = await buttons.count()
            print(f"Found {count} ASP.NET download buttons on homepage.")
            
            for i in range(count):
                print(f"Clicking ASP.NET Download Button {i+1}...")
                await page.goto("https://egazette.gov.in/Default.aspx", wait_until='domcontentloaded')
                await page.wait_for_timeout(1500)
                btn = page.locator('input[src*="download-pdf.png"]').nth(i)
                await btn.click()
                await page.wait_for_timeout(3000)
                
            saved = 0
            for idx, (url, body) in enumerate(pdf_binaries):
                dest_path = os.path.join(DEST_DIR, f"central_gazette_live_{idx+1:03d}.pdf")
                with open(dest_path, 'wb') as f:
                    f.write(body)
                saved += 1
                
            print(f"\n==========================================")
            print(f"TOTAL PLAYWRIGHT INTERCEPTED CENTRAL EGAZETTE PDFs: {saved}")
            print(f"==========================================")
            
        except Exception as e:
            print(f"Error: {e}")
            
        await browser.close()

if __name__ == '__main__':
    asyncio.run(main())
