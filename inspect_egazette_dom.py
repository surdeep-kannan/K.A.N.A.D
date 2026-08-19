import requests
from bs4 import BeautifulSoup

url = "https://egazette.gov.in/"
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

r = requests.get(url, headers=headers, verify=False)
soup = BeautifulSoup(r.text, 'html.parser')

print("=== ALL LINKS AND BUTTONS ON EGAZETTE HOMEPAGE ===")
for idx, a in enumerate(soup.find_all(['a', 'input', 'button'])):
    href = a.get('href') or a.get('onclick') or a.get('src') or a.get('value')
    text = a.get_text(strip=True) or a.get('name') or ''
    print(f"[{idx:3d}] Tag: {a.name:6s} | Text/Val: {text[:40]:40s} | Link/Action: {href}")
