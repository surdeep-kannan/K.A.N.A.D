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

r = session.get('https://egazette.gov.in/Default.aspx', verify=False)
soup = BeautifulSoup(r.text, 'html.parser')

viewstate = soup.find('input', {'id': '__VIEWSTATE'})['value']
viewstategen = soup.find('input', {'id': '__VIEWSTATEGENERATOR'})['value']
eventvalidation = soup.find('input', {'id': '__EVENTVALIDATION'})['value']
hidden1 = soup.find('input', {'id': 'hidden1'})['value'] if soup.find('input', {'id': 'hidden1'}) else ''

def is_valid_pdf(content):
    return len(content) > 1000 and content.startswith(b'%PDF')

buttons = soup.find_all('input', {'name': re.compile(r'ImgDownLoad')})
print(f"=== TESTING FULL FORM POST FOR {len(buttons)} DOWNLOAD BUTTONS ===")

saved = 0
for idx, btn in enumerate(buttons):
    btn_name = btn['name']
    
    payload = {
        '__EVENTTARGET': btn_name,
        '__EVENTARGUMENT': '',
        '__VIEWSTATE': viewstate,
        '__VIEWSTATEGENERATOR': viewstategen,
        '__EVENTVALIDATION': eventvalidation,
        'hidden1': hidden1,
        '__SCROLLPOSITIONX': '0',
        '__SCROLLPOSITIONY': '0',
        f'{btn_name}.x': '10',
        f'{btn_name}.y': '10'
    }
    
    try:
        res = session.post('https://egazette.gov.in/Default.aspx', data=payload, verify=False, timeout=15)
        cd = res.headers.get('content-disposition', '')
        ct = res.headers.get('content-type', '')
        print(f"  Button {idx+1} ({btn_name}) -> Status: {res.status_code} | Content-Type: {ct} | Content-Disp: {cd}")
        
        if res.status_code == 200 and is_valid_pdf(res.content):
            dest_path = os.path.join(DEST_DIR, f"central_gazette_post_{idx+1:03d}.pdf")
            with open(dest_path, 'wb') as f:
                f.write(res.content)
            saved += 1
            print(f"    [✓] Saved -> {os.path.basename(dest_path)} ({len(res.content)} bytes)")
    except Exception as e:
        print(f"  Error on {btn_name}: {e}")

print(f"\n==========================================")
print(f"TOTAL VERIFIED CENTRAL EGAZETTE PDFs: {saved}")
print(f"==========================================")
