"""Generic crawler for the ASP.NET WebForms GridView pagination pattern used
by several Gujarat government sites (gad.gujarat.gov.in and its divisional
sub-sites). These pages can't be paged with a query-string GET -- the "next
page" links are `javascript:__doPostBack('...$gvDocument','Page$N')`, so a
plain requests+BeautifulSoup GET loop (like the rest of this pipeline uses)
silently only ever sees page 1.

This walks it properly: extract the ASP.NET hidden form fields
(__VIEWSTATE/__VIEWSTATEGENERATOR/__EVENTVALIDATION/etc.), POST back with
__EVENTTARGET/__EVENTARGUMENT set to the grid's page target, and re-extract
fresh hidden fields from each response before requesting the next page (the
viewstate must advance with each postback or the grid silently stops
paginating).
"""
import re
import urllib.parse
from bs4 import BeautifulSoup

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

PDF_HREF_RE = re.compile(r'href="([^"]*\.pdf[^"]*)"', re.I)


def _form_state(page_url, html):
    soup = BeautifulSoup(html, 'html.parser')
    form = soup.find('form')
    action = urllib.parse.urljoin(page_url, form.get('action')) if form else page_url
    inputs = {inp.get('name'): inp.get('value', '') for inp in soup.find_all('input') if inp.get('name')}
    return action, inputs


def crawl_gridview_pdfs(session, start_url, grid_event_target,
                         max_pages=500, dup_streak_stop=3):
    """Pages through the GridView starting at page 1 (the initial GET).

    Returns (pdf_urls, reached_end, last_page):
      pdf_urls    -- list of (page_number, absolute_pdf_url), in the order found
      reached_end -- True if we stopped because `dup_streak_stop` consecutive
                     pages produced no new links (i.e. we walked past the
                     real end of the grid), False if we hit max_pages or a
                     request error first
      last_page   -- highest page number attempted
    """
    r = session.get(start_url, headers=HEADERS, verify=False, timeout=15)
    html = r.text
    action, inputs = _form_state(start_url, html)

    seen = set()
    results = []
    page = 1
    dup_streak = 0
    reached_end = False

    while page <= max_pages:
        pdfs = [urllib.parse.urljoin(start_url, h) for h in PDF_HREF_RE.findall(html)]
        new = [p for p in pdfs if p not in seen]
        for p in new:
            results.append((page, p))
        seen.update(pdfs)

        if not new:
            dup_streak += 1
            if dup_streak >= dup_streak_stop:
                reached_end = True
                break
        else:
            dup_streak = 0

        page += 1
        inputs['__EVENTTARGET'] = grid_event_target
        inputs['__EVENTARGUMENT'] = f'Page${page}'
        try:
            r = session.post(action, data=inputs, headers={**HEADERS, 'Referer': start_url},
                              verify=False, timeout=15)
        except Exception:
            break
        if r.status_code != 200:
            break
        html = r.text
        action, inputs = _form_state(start_url, html)

    return results, reached_end, page
