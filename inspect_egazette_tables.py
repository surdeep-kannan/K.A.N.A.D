import os, requests
from bs4 import BeautifulSoup

url = "https://egazette.gov.in/Default.aspx"
headers = {'User-Agent': 'Mozilla/5.0'}

r = requests.get(url, headers=headers, verify=False)
soup = BeautifulSoup(r.text, 'html.parser')

print("=== TABLE CELL STRUCTURE ON CENTRAL EGAZETTE HOMEPAGE ===")
tables = soup.find_all('table')
print(f"Total tables found: {len(tables)}")

for idx, t in enumerate(tables):
    rows = t.find_all('tr')
    print(f"\nTable {idx+1}: {len(rows)} rows")
    for r_idx, tr in enumerate(rows[:5]):
        cells = [td.get_text(strip=True) for td in tr.find_all(['td', 'th'])]
        imgs = [img.get('src') for img in tr.find_all('img')]
        links = [a.get('href') for a in tr.find_all('a')]
        inputs = [inp.get('name') for inp in tr.find_all('input')]
        print(f"  Row {r_idx}: Cells={cells[:3]} | Inputs={inputs} | Links={links}")
