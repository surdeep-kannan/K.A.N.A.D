import requests
from bs4 import BeautifulSoup

headers = {'User-Agent': 'Mozilla/5.0'}
session = requests.Session()

# Test category links
cat_urls = [
    "https://egazette.gov.in/RecentUploads.aspx?Category=1",
    "https://egazette.gov.in/RecentUploads.aspx?Category=2",
    "https://egazette.gov.in/RecentUploads.aspx?Category=5",
    "https://egazette.gov.in/GazetteDirectory.aspx",
    "https://egazette.gov.in/SearchMenu.aspx"
]

print("=== INSPECTING EGAZETTE DIRECT CATEGORY ENDPOINTS ===")
for url in cat_urls:
    try:
        r = session.get(url, headers=headers, verify=False)
        soup = BeautifulSoup(r.text, 'html.parser')
        inputs = soup.find_all('input', {'src': lambda s: s and 'download' in s.lower()})
        links = soup.find_all('a', href=lambda h: h and ('.pdf' in h.lower() or 'writereaddata' in h.lower()))
        print(f" URL: {url:55s} | Status: {r.status_code} | Download Inputs: {len(inputs)} | Direct PDF Anchors: {len(links)}")
    except Exception as e:
        print(f" Exception on {url}: {e}")
