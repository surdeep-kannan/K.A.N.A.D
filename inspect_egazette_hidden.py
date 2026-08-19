import os, requests
from bs4 import BeautifulSoup

url = "https://egazette.gov.in/Default.aspx"
headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}

s = requests.Session()
r = s.get(url, headers=headers, verify=False)
soup = BeautifulSoup(r.text, 'html.parser')

inputs = soup.find_all('input', {'type': 'hidden'})
print("=== ALL HIDDEN ASP.NET INPUT FIELDS ===")
for i in inputs:
    print(f" Name: {i.get('name'):30s} | Value: {i.get('value')[:50] if i.get('value') else ''}")
