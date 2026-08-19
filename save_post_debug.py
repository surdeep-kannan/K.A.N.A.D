import requests
from bs4 import BeautifulSoup

headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
session = requests.Session()

r1 = session.get('https://egazette.gov.in/Default.aspx', headers=headers, verify=False)
soup = BeautifulSoup(r1.text, 'html.parser')

payload = {
    '__EVENTTARGET': 'rpt_Extra$ctl01$ImgDownLoadE',
    '__EVENTARGUMENT': '',
    '__VIEWSTATE': soup.find('input', {'id': '__VIEWSTATE'})['value'],
    '__VIEWSTATEGENERATOR': soup.find('input', {'id': '__VIEWSTATEGENERATOR'})['value'],
    '__EVENTVALIDATION': soup.find('input', {'id': '__EVENTVALIDATION'})['value'],
    'hidden1': soup.find('input', {'id': 'hidden1'})['value'] if soup.find('input', {'id': 'hidden1'}) else ''
}

r2 = session.post('https://egazette.gov.in/Default.aspx', data=payload, headers=headers, verify=False)

with open('/home/surdeep/Documents/K.A.N.A.D/production_pipeline/post_response_debug.html', 'w') as f:
    f.write(r2.text)

print("Saved post response debug HTML to post_response_debug.html")
