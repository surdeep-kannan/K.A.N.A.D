import os, requests, re
from bs4 import BeautifulSoup

BASE_RAW_DIR = "/home/surdeep/Documents/K.A.N.A.D/production_pipeline/pdf_raw"
DEST_DIR = os.path.join(BASE_RAW_DIR, "egazette_central")
os.makedirs(DEST_DIR, exist_ok=True)

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Referer': 'https://egazette.gov.in/Default.aspx'
}

session = requests.Session()
session.headers.update(headers)

# 1. Fetch initial page and extractions
r = session.get('https://egazette.gov.in/Default.aspx', verify=False)
soup = BeautifulSoup(r.text, 'html.parser')

viewstate = soup.find('input', {'id': '__VIEWSTATE'})['value']
viewstategen = soup.find('input', {'id': '__VIEWSTATEGENERATOR'})['value']
eventvalidation = soup.find('input', {'id': '__EVENTVALIDATION'})['value']

print("=== PARSING CENTRAL EGAZETTE ASP.NET POSTBACK DOWNLOAD BUTTONS ===")

# Find all download inputs
inputs = soup.find_all('input', {'name': re.compile(r'ImgDownLoad')})
print(f"Found {len(inputs)} ASP.NET Download buttons on Homepage table:")

def is_valid_pdf(content):
    return len(content) > 1000 and content.startswith(b'%PDF')

saved = 0
for idx, inp in enumerate(inputs):
    target_name = inp['name']
    
    post_data = {
        '__EVENTTARGET': target_name,
        '__EVENTARGUMENT': '',
        '__VIEWSTATE': viewstate,
        '__VIEWSTATEGENERATOR': viewstategen,
        '__EVENTVALIDATION': eventvalidation
    }
    
    try:
        res = session.post('https://egazette.gov.in/Default.aspx', data=post_data, verify=False, timeout=15)
        if res.status_code == 200 and is_valid_pdf(res.content):
            fname = f"central_gazette_postback_{idx+1:03d}.pdf"
            dest_path = os.path.join(DEST_DIR, fname)
            with open(dest_path, 'wb') as f:
                f.write(res.content)
            saved += 1
            print(f"  [✓] [{saved}/{len(inputs)}] Postback Success -> {fname} ({len(res.content)} bytes)")
        else:
            print(f"  [!] Postback target {target_name} returned status {res.status_code} / Non-PDF")
    except Exception as e:
        print(f"  [!] Postback exception for {target_name}: {e}")

print(f"\n==========================================")
print(f"TOTAL VERIFIED CENTRAL EGAZETTE PDFs SAVED: {saved}")
print(f"==========================================")
