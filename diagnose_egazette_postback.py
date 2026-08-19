import requests
from bs4 import BeautifulSoup

headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
session = requests.Session()

r1 = session.get('https://egazette.gov.in/Default.aspx', headers=headers, verify=False)
soup = BeautifulSoup(r1.text, 'html.parser')

payload = {
    '__EVENTTARGET': 'rpt_Extra$ctl01$ImgDownLoadE.x',
    '__EVENTARGUMENT': '',
    '__VIEWSTATE': soup.find('input', {'id': '__VIEWSTATE'})['value'],
    '__VIEWSTATEGENERATOR': soup.find('input', {'id': '__VIEWSTATEGENERATOR'})['value'],
    '__EVENTVALIDATION': soup.find('input', {'id': '__EVENTVALIDATION'})['value'],
    'hidden1': soup.find('input', {'id': 'hidden1'})['value'] if soup.find('input', {'id': 'hidden1'}) else '',
    'rpt_Extra$ctl01$ImgDownLoadE.x': '12',
    'rpt_Extra$ctl01$ImgDownLoadE.y': '14'
}

r2 = session.post('https://egazette.gov.in/Default.aspx', data=payload, headers=headers, verify=False)
soup2 = BeautifulSoup(r2.text, 'html.parser')

print("=== POST RESPONSE DIAGNOSTIC ===")
print("Response Status Code:", r2.status_code)
print("Content-Type Header:", r2.headers.get('content-type'))
print("Content Length:", len(r2.content))

iframe = soup2.find('iframe')
if iframe:
    print("Found iframe:", iframe.get('src'))

embed = soup2.find('embed')
if embed:
    print("Found embed:", embed.get('src'))

# Check for window.open or location.href script redirects
scripts = soup2.find_all('script')
for s in scripts:
    stext = s.string or ''
    if 'window.open' in stext or 'location' in stext or 'pdf' in stext.lower() or 'writereaddata' in stext.lower():
        print(" Found JS Script Action/Redirect:", stext.strip()[:150])
