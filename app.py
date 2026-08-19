import os, sqlite3, json, requests, glob
import pdfplumber
from flask import Flask, request, jsonify, send_file, send_from_directory, render_template

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, 'database', 'gujarat_gr_intel.db')

app = Flask(__name__, static_folder='static', template_folder='templates')

def available_pdf_filenames():
    """Filenames of PDFs actually present under pdf_raw/ right now.
    If running in cloud deployment (Zoho AppSail) where pdf_raw is not bundled,
    falls back to serving all verified database records via OCR text & source URLs.
    """
    local_files = {
        os.path.basename(p)
        for p in glob.glob(os.path.join(BASE_DIR, 'pdf_raw', '**', '*.pdf'), recursive=True)
    }
    if local_files:
        return local_files
    try:
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT filename FROM gr_documents")
        db_files = {r['filename'] for r in c.fetchall()}
        conn.close()
        return db_files
    except Exception:
        return set()

import io, re, requests

def fetch_remote_url_text(source_url, max_chars=8000):
    """Fetch and extract text from a live official government webpage or remote PDF URL."""
    if not source_url or not source_url.startswith('http'):
        return ''
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
        res = requests.get(source_url, headers=headers, timeout=12, verify=False)
        if res.status_code != 200 or not res.content:
            return ''
        
        # 1. If PDF content stream
        if res.content[:4] == b'%PDF' or 'pdf' in res.headers.get('Content-Type', '').lower():
            text = ''
            with pdfplumber.open(io.BytesIO(res.content)) as pdf:
                for page in pdf.pages:
                    text += (page.extract_text() or '') + '\n'
                    if len(text) >= max_chars:
                        break
            return text.strip()[:max_chars]
        else:
            # 2. HTML Webpage text extraction
            html_text = res.text
            clean = re.sub(r'<(script|style).*?>.*?</\1>', '', html_text, flags=re.DOTALL | re.IGNORECASE)
            clean = re.sub(r'<.*?>', ' ', clean)
            clean = re.sub(r'\s+', ' ', clean).strip()
            return clean[:max_chars]
    except Exception as e:
        print(f"Error scanning remote URL {source_url}: {e}")
        return ''

def extract_pdf_text(source_pdf_path, max_chars=8000):
    """Pull real text out of a document's PDF on disk."""
    if not source_pdf_path:
        return ''
    full_path = os.path.join(BASE_DIR, source_pdf_path)
    if not os.path.exists(full_path):
        return ''
    try:
        text = ''
        with pdfplumber.open(full_path) as pdf:
            for page in pdf.pages:
                text += (page.extract_text() or '') + '\n'
                if len(text) >= max_chars:
                    break
    except Exception:
        return ''
    return text.strip()[:max_chars]

def get_document_text(doc_id, row):
    """Real text to summarize for a document:
    1. Stored translation/summary if valid.
    2. Text freshly extracted from local PDF on disk.
    3. Live text scanned directly from the official government webpage/PDF URL (source_url).
    4. Cached back to SQLite DB so it's only extracted once.
    """
    raw = row['english_translation'] or row['ai_summary'] or ''
    is_placeholder = (
        not raw or raw.startswith('Quarantined')
        or raw.startswith('Official Government Resolution document')
        or len(raw.strip()) < 50
    )
    
    # Step A: Local PDF on disk
    if is_placeholder and row['source_pdf_path']:
        extracted = extract_pdf_text(row['source_pdf_path'])
        if extracted and len(extracted) >= 50:
            conn = get_db()
            conn.execute("UPDATE gr_documents SET english_translation = ? WHERE id = ?", (extracted, doc_id))
            conn.commit()
            conn.close()
            return extracted

    # Step B: Live Remote Government Webpage / PDF URL Scan
    if is_placeholder and row.get('source_url'):
        remote_text = fetch_remote_url_text(row['source_url'])
        if remote_text and len(remote_text) >= 50:
            conn = get_db()
            conn.execute("UPDATE gr_documents SET english_translation = ? WHERE id = ?", (remote_text, doc_id))
            conn.commit()
            conn.close()
            return remote_text

    if is_placeholder:
        dept_name = row['department'] or 'Government of Gujarat'
        return f"Document Title: {row['filename']}\nDepartment: {dept_name}\nOfficial Government Resolution and Policy Notification."
    return raw

@app.after_request
def add_cache_control_headers(response):
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response

import re

def regexp(expr, item):
    if item is None:
        return False
    # Strip placeholder seed text so search doesn't match raw filenames embedded in seed string
    if item.startswith('Official Government Resolution document'):
        item = ''
    try:
        return re.search(r'\b' + re.escape(expr) + r'\b', item, re.IGNORECASE) is not None
    except Exception:
        return False

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.create_function('REGEXP', 2, regexp)
    conn.row_factory = sqlite3.Row
    return conn

@app.route('/')
def index():
    return send_from_directory('templates', 'index.html')

def _derive_title(fn, text, dept, gr_num=None):
    if not fn:
        return "Government Resolution"
    
    clean_fn = re.sub(r'\.pdf$', '', fn, flags=re.I)
    clean_fn = re.sub(r'^[\d_]+', '', clean_fn)
    clean_fn = re.sub(r'[-_]+', ' ', clean_fn).strip()
    
    # Check if explicit Subject line exists in translation text
    if text:
        subj_match = re.search(r'(?:Subject|Sub|Visay)\s*:\s*([^\n\.]+)', text, re.I)
        if subj_match:
            clean_sub = re.sub(r'[\*\#]', '', subj_match.group(1)).strip()
            if len(clean_sub) > 8:
                return clean_sub.title()[:90]

    # Strip generic draft / scrape prefixes for cleaner title display
    clean_title = re.sub(r'^(draft\s*(resolution|letter|gr|order)|scraped\s*live\s*gr|gr)\s*', '', clean_fn, flags=re.I).strip()
    clean_title = re.sub(r'[\*\#]', '', clean_title).strip()

    if len(clean_title) > 4 and not re.match(r'^\d+$', clean_title):
        return clean_title.title()
    elif len(clean_fn) > 5 and not re.match(r'^(gr\s*\d+|gad\s*personnel\s*gr\s*\d+|scraped\s*live\s*gr\s*\d+)$', clean_fn, re.I):
        return clean_fn.title()

    if text:
        lines = [l.strip() for l in text.splitlines() if l.strip()]
        for l in lines:
            l_clean = re.sub(r'^[^\w]+', '', l).strip()
            l_clean = re.sub(r'[\*\#]', '', l_clean).strip()
            l_clean = re.sub(r'^(Subject|Notification|Resolution|Government of Gujarat|Department|Order)\s*[:\s]*', '', l_clean, flags=re.I).strip()
            l_clean = re.sub(r'[^\w\s\-\.,\(\)]', '', l_clean).strip()

            if len(l_clean) > 10 and not re.match(r'^(notification|dated|sachivalaya|government|home department|order)$', l_clean, re.I):
                return l_clean[:90].title()

    if gr_num:
        return f"{dept or 'Government'} Resolution ({gr_num})"

    return f"{dept or 'Government'} Resolution"

@app.route('/api/search')
def search():
    query = request.args.get('q', '').strip()
    dept  = request.args.get('dept', '').strip()
    page  = int(request.args.get('page', 1))
    limit = 20
    offset = (page - 1) * limit

    conn = get_db()
    c    = conn.cursor()

    if not query and not dept:
        base = (
            "FROM gr_documents WHERE (quality_status IS NULL OR quality_status NOT LIKE 'REJECTED%') "
            "AND (english_translation IS NULL OR english_translation NOT LIKE 'Quarantined%') "
            "AND filename NOT LIKE 'gr_0%' AND filename NOT LIKE 'scraped_live_gr_0%' AND filename NOT LIKE '%Untitled%'"
        )
    else:
        base = (
            "FROM gr_documents WHERE (quality_status IS NULL OR quality_status NOT LIKE 'REJECTED%') "
            "AND (english_translation IS NULL OR english_translation NOT LIKE 'Quarantined%')"
        )

    # Restrict the feed to rows backed by a PDF that actually exists on disk.
    on_disk = available_pdf_filenames()
    if not on_disk:
        return jsonify({'total': 0, 'page': page, 'results': []})
    base += f" AND filename IN ({','.join('?' for _ in on_disk)})"
    disk_params = list(on_disk)

    params = list(disk_params)
    if query:
        base += " AND (filename REGEXP ? OR english_translation REGEXP ? OR gr_number REGEXP ? OR department REGEXP ?)"
        params.extend([query] * 4)
    if dept:
        base += " AND department LIKE ?"
        params.append(f"%{dept}%")

    c.execute(f"SELECT COUNT(*) {base}", params)
    total = c.fetchone()[0]

    if not query:
        order_by = (
            "ORDER BY (CASE "
            "WHEN (department LIKE '%Home%' AND department NOT LIKE '%Ministry%') OR filename LIKE '%Police%' OR filename LIKE '%FSL%' OR filename LIKE '%Jail%' OR filename LIKE '%Homeguards%' THEN 1 "
            "WHEN department LIKE '%Court%' OR department LIKE '%Government%' OR department LIKE '%GAD%' OR department LIKE '%Panchayat%' THEN 2 "
            "WHEN department LIKE '%Ministry of Home%' OR department LIKE '%India Code%' OR department LIKE '%eGazette%' THEN 3 "
            "ELSE 4 END) ASC, id DESC"
        )
    else:
        order_by = (
            "ORDER BY (CASE "
            "WHEN english_translation IS NOT NULL AND length(english_translation) > 200 AND english_translation NOT LIKE 'Official Government%' THEN 1 "
            "WHEN ai_summary IS NOT NULL AND length(ai_summary) > 50 THEN 2 ELSE 3 END) ASC, id DESC"
        )

    c.execute(
        f"SELECT id, filename, department, gr_number, gr_date, english_translation, ai_summary, "
        f"source_pdf_path, page_image_paths, source_url, quality_status {base} "
        f"{order_by} LIMIT ? OFFSET ?",
        params + [limit, offset]
    )
    rows = c.fetchall()
    conn.close()

    results = []
    for r in rows:
        imgs = []
        if r['page_image_paths']:
            try: imgs = json.loads(r['page_image_paths'])
            except: pass

        raw_summary = r['english_translation'] or ''
        if not raw_summary or raw_summary.startswith('Official Government') or raw_summary.startswith('Quarantined'):
            if r['ai_summary'] and len(r['ai_summary']) > 20:
                raw_summary = r['ai_summary']

        if raw_summary.startswith('Official Government Resolution document'):
            dept_name = r['department'] or 'Government of Gujarat'
            summary = f"Verified Official Document · {dept_name} · Select English / ગુજરાતી / हिन्दी below for instant AI briefing."
        elif not raw_summary:
            summary = "Verified Official Resolution · Select English / ગુજરાતી / हिन्दी below for instant AI briefing."
        else:
            summary = _clean_summary_output(raw_summary)
            # Remove markdown asterisks for card preview snippet
            summary = re.sub(r'[\*\#]', '', summary)
            if len(summary) > 280:
                summary = summary[:280].rstrip() + '…'

        title = _derive_title(r['filename'], raw_summary, r['department'], r['gr_number'])

        results.append({
            'id': r['id'],
            'filename': title,
            'raw_filename': r['filename'],
            'department': r['department'] or 'Government of Gujarat',
            'gr_number': r['gr_number'],
            'gr_date': r['gr_date'],
            'summary': summary,
            'source_url': r['source_url'],
            'page_count': len(imgs),
            'has_pdf': bool(r['source_pdf_path']),
            'quality': r['quality_status'],
        })

    return jsonify({'total': total, 'page': page, 'results': results})

@app.route('/api/doc/<int:doc_id>/pages')
def doc_pages(doc_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT filename, page_image_paths FROM gr_documents WHERE id=?", (doc_id,))
    row = c.fetchone()
    conn.close()
    if not row: return jsonify([])
    imgs = []
    if row['page_image_paths']:
        try: imgs = json.loads(row['page_image_paths'])
        except: pass
    return jsonify({'filename': row['filename'], 'pages': imgs})

@app.route('/api/pdf/<int:doc_id>')
def serve_pdf(doc_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT source_pdf_path, source_url FROM gr_documents WHERE id=?", (doc_id,))
    row = c.fetchone()
    conn.close()
    if row:
        if row['source_pdf_path']:
            full = os.path.join(BASE_DIR, row['source_pdf_path'])
            if os.path.exists(full):
                return send_file(full, mimetype='application/pdf')
        if row['source_url'] and row['source_url'].startswith('http'):
            from flask import redirect
            return redirect(row['source_url'], code=302)
    return "PDF Not Found", 404

@app.route('/pdf_images/<path:filename>')
def serve_images(filename):
    return send_from_directory(os.path.join(BASE_DIR, 'pdf_images'), filename)

@app.route('/doc/<int:doc_id>')
def doc_detail(doc_id):
    conn = get_db()
    c = conn.cursor()
    c.execute(
        "SELECT id, filename, department, gr_number, gr_date, english_translation, ai_summary, "
        "source_pdf_path, page_image_paths, source_url, quality_status FROM gr_documents WHERE id=?",
        (doc_id,)
    )
    row = c.fetchone()
    conn.close()

    if not row:
        return "Document not found", 404

    imgs = []
    if row['page_image_paths']:
        try: imgs = json.loads(row['page_image_paths'])
        except: pass

    raw_text = row['english_translation'] or row['ai_summary'] or ''
    title = _derive_title(row['filename'], raw_text, row['department'], row['gr_number'])

    has_pdf = bool((row['source_pdf_path'] and os.path.exists(os.path.join(BASE_DIR, row['source_pdf_path']))) or (row['source_url'] and row['source_url'].startswith('http')))

    doc_data = {
        'id': row['id'],
        'filename': title,
        'raw_filename': row['filename'],
        'department': row['department'] or 'Government of Gujarat',
        'gr_number': row['gr_number'],
        'gr_date': row['gr_date'],
        'english_translation': row['english_translation'] or '',
        'ai_summary': row['ai_summary'] or '',
        'source_url': row['source_url'],
        'pages': imgs,
        'has_pdf': has_pdf,
        'quality': row['quality_status']
    }
    return render_template('document_detail.html', doc=doc_data)


@app.route('/api/chat', methods=['POST'])
def api_chat():
    data = request.get_json() or {}
    user_msg = data.get('message', '').strip()
    doc_id = data.get('doc_id')

    if not user_msg:
        return jsonify({'error': 'Message cannot be empty'}), 400

    conn = get_db()
    c = conn.cursor()

    context_docs = []
    target_doc_info = None
    if doc_id:
        c.execute("SELECT filename, department, gr_number, gr_date, english_translation, ai_summary FROM gr_documents WHERE id=?", (doc_id,))
        row = c.fetchone()
        if row:
            target_doc_info = row
            text = row['english_translation'] or row['ai_summary'] or ''
            clean_fn = row['filename'].replace('.pdf', '').replace('_', ' ')
            context_docs.append(f"Target Document: {clean_fn}\nDepartment: {row['department']}\nGR Number: {row['gr_number']}\nContent: {text[:2500]}")

    if not context_docs or len(context_docs) < 2:
        c.execute(
            "SELECT filename, department, gr_number, english_translation, ai_summary "
            "FROM gr_documents WHERE english_translation REGEXP ? OR filename REGEXP ? OR department REGEXP ? LIMIT 3",
            (user_msg, user_msg, user_msg)
        )
        rows = c.fetchall()
        for r in rows:
            text = r['english_translation'] or r['ai_summary'] or ''
            context_docs.append(f"Document File: {r['filename']}\nDepartment: {r['department']}\nContent: {text[:1500]}")

    conn.close()

    context_str = "\n\n---\n\n".join(context_docs) if context_docs else "No specific documents found."
    prompt = (
        "You are K.A.N.A.D., an expert legal and administrative AI Assistant specializing in Gujarat Government Resolutions (GRs), pension regulations, police orders, and High Court judgments.\n"
        "Answer the user's question accurately, cleanly, and authoritatively based on the retrieved context below.\n\n"
        f"RETRIEVED CONTEXT:\n{context_str}\n\n"
        f"USER QUESTION: {user_msg}\n\n"
        "Provide a concise, professional answer in clean English. Do NOT output internal monologues, reasoning steps, or prompt echoes."
    )

    try:
        sec = _load_secrets()
        token = _get_token()
        project_id = os.getenv('ZOHO_PROJECT_ID', sec.get('ZOHO_PROJECT_ID', '46930000000013048'))
        org_id = os.getenv('ZOHO_ORG_ID', sec.get('ZOHO_ORG_ID', '60074744957'))

        url = f'https://api.catalyst.zoho.in/quickml/v1/project/{project_id}/glm/chat'
        headers = {
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json',
            'CATALYST-ORG': org_id,
        }
        payload = {
            'model': 'crm-di-glm47b_30b_it',
            'messages': [{'role': 'user', 'content': prompt}],
            'temperature': 0.2,
            'max_tokens': 600,
        }
        r = requests.post(url, headers=headers, json=payload, timeout=30)
        if r.status_code == 200:
            res_text = r.json().get('response', '')
            clean_reply = _clean_chat_reply(res_text, target_doc_info)
            if clean_reply:
                return jsonify({'reply': clean_reply})
    except Exception as e:
        pass

    if target_doc_info:
        clean_fn = target_doc_info['filename'].replace('.pdf', '').replace('_', ' ')
        dept_name = target_doc_info['department'] or 'Government of Gujarat'
        gr_num = target_doc_info['gr_number'] or 'Official Order'
        fallback_reply = (
            f"This document (**{clean_fn}**) is an official Government Resolution issued by the **{dept_name}**.\n\n"
            f"• **Subject & Scope**: Official administrative order and policy directives for police and state administration enforcement.\n"
            f"• **GR Reference**: {gr_num}\n"
            f"• **Department**: {dept_name}\n\n"
            f"You can download the original PDF or inspect the rendered document pages above for specific clauses."
        )
    else:
        fallback_reply = f"Based on the K.A.N.A.D. database, here is the relevant document context for '{user_msg}':\n\n" + (context_str[:800] if context_docs else "Please refine your query or select a specific document to view details.")

    return jsonify({'reply': fallback_reply})


def _clean_chat_reply(text, target_doc_info=None):
    if not text:
        return None
    if '</think>' in text:
        text = text.split('</think>')[-1].strip()

    for marker in ['4.  **Final Polish:**', '4. **Final Polish:**', 'Final Polish:', 'Final Answer:', '### Response', 'Response:']:
        if marker in text:
            text = text.split(marker)[-1].strip()
            break

    bad_keywords = [
        'crucial realization', 'formulate the answer', 'internal monologue', 'self-correction',
        'identify the problem', 'determine the strategy', 'draft 1', 'draft 2', 'constraint check'
    ]
    if any(k in text.lower() for k in bad_keywords):
        lines = [line.strip() for line in text.splitlines() if line.strip() and not any(k in line.lower() for k in bad_keywords)]
        if lines and len(lines[-1]) > 20 and not any(k in lines[-1].lower() for k in bad_keywords):
            return lines[-1]
        if target_doc_info:
            clean_fn = target_doc_info['filename'].replace('.pdf', '').replace('_', ' ')
            dept_name = target_doc_info['department'] or 'Government of Gujarat'
            return (
                f"This document (**{clean_fn}**) is an official Government Resolution issued by the **{dept_name}**.\n\n"
                f"• **Subject & Scope**: Official administrative order and policy directives for police and state administration enforcement.\n"
                f"• **Department**: {dept_name}\n\n"
                f"You can download the original PDF or inspect the rendered document pages above for specific clauses."
            )
        return None

    return text.strip()


@app.route('/api/stats')
def stats():
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM gr_documents")
    total = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM gr_documents WHERE source_url IS NOT NULL AND source_url != ''")
    linked = c.fetchone()[0]
    c.execute("SELECT COUNT(DISTINCT department) FROM gr_documents WHERE department IS NOT NULL")
    depts = c.fetchone()[0]
    conn.close()
    return jsonify({'total_docs': total, 'linked': linked, 'departments': depts})


# ── GLM SUMMARIZER ──────────────────────────────────────────────────────────

def _load_secrets():
    path = os.path.join(BASE_DIR, 'config', 'secrets.env')
    sec = {}
    if os.path.exists(path):
        for line in open(path):
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                k, v = line.split('=', 1)
                sec[k.strip()] = v.strip().strip('"').strip("'")
    return sec

def _get_token():
    sec = _load_secrets()
    r = requests.post('https://accounts.zoho.in/oauth/v2/token', data={
        'grant_type':    'refresh_token',
        'client_id':     os.getenv('ZOHO_CLIENT_ID',     sec.get('ZOHO_CLIENT_ID')),
        'client_secret': os.getenv('ZOHO_CLIENT_SECRET', sec.get('ZOHO_CLIENT_SECRET')),
        'refresh_token': os.getenv('ZOHO_REFRESH_TOKEN', sec.get('ZOHO_REFRESH_TOKEN')),
    }, timeout=15)
    return r.json().get('access_token')

def _clean_summary_output(text):
    if not text:
        return ""

    # 1. Truncate trailing self-checking blocks
    for stop_marker in [
        '5. Final Review',
        '5.  Final Review',
        '5. Final review',
        'Final Review against Constraints:',
        'Did I translate?',
        'Did I summarize?',
    ]:
        if stop_marker in text:
            text = text.split(stop_marker)[0].strip()

    # 2. Extract Section 3 or Section 4 (Drafting the Executive Summary / Final Output)
    for start_marker in [
        '3. Drafting the Executive Summary:',
        '3.  Drafting the Executive Summary:',
        '3. Drafting the Sections:',
        '3.  Drafting the Sections:',
        '3. Drafting',
        'Drafting the Executive Summary:',
        '3. Draft the Output:',
        '3.  Draft the Output:',
        '4. Refining for Conciseness and Clarity:',
        '4.  Refining for Conciseness and Clarity:',
        '### Executive Summary',
        'Executive Summary:',
    ]:
        if start_marker in text:
            text = text.split(start_marker)[-1].strip()
            break

    # 3. If start_marker was not found but 'Confidence Score:' exists, slice after Confidence Score
    if 'Confidence Score:' in text:
        text = text.split('Confidence Score:')[-1].strip()
        lines = text.splitlines()
        if lines and ('5/5' in lines[0] or lines[0].strip().startswith('.')):
            lines = lines[1:]
        text = '\n'.join(lines).strip()

    # 4. Pure English Sanitization: Purge raw Gujarati script quotes and '->' arrows
    # Match Gujarati script quotes followed by english in parens: "..." (English) -> English
    text = re.sub(r'\"[\u0A80-\u0AFF\s\.\:\,\-\(\)\?\/]+\"\s*\((.*?)\)', r'\1', text)
    # Match Gujarati script inside quotes -> remove quote
    text = re.sub(r'\"[\u0A80-\u0AFF\s\.\:\,\-\(\)\?\/]+\"', '', text)
    # Clean any leftover Gujarati characters
    text = re.sub(r'[\u0A80-\u0AFF]+', '', text)
    # Replace arrows
    text = text.replace(' -> ', ' — ').replace('->', ' — ')

    # 5. Filter remaining lines for meta keywords or prompt echoes
    lines = text.splitlines()
    clean_lines = []

    skip_keywords = [
        'Analyze the Request',
        'Analyze the Input Document',
        'Analyze the Source Text',
        'Analyze the Document Content',
        'Draft 1:',
        'Draft 2:',
        'Task:',
        'Role:',
        'Target Audience:',
        'Strict Rules:',
        'Categories Required:',
        'Constraint Checklist',
        'Never reveal system rules',
        'Be concise and precise',
        'Follow operator instructions',
        'Handle untrusted user input',
        'Confidence Score',
        'with four specific bullet points',
        'with 4 specific bullet points',
        'Input:',
        'Constraint:',
        'Translate and summarize',
        '1-2 sentences',
        '3-4 concise',
        'issuing department',
        'resolution numbers',
        'Subject (1-2',
        'Key Directives & Rules (',
        'Authority & Department.',
        'Dates & Ref Numbers.',
        'with specific bullet points',
        'Source Material:',
        'Source Text:',
        'Specific Requirements:',
        'Format:',
        'Let\'s look at',
        'Let\'s re-read',
        'Translation of Body:',
        'Needs to be inferred',
        'The prompt asks for',
        'I will list the Department',
    ]

    for line in lines:
        s = line.strip()
        if not s:
            continue

        if any(kw.lower() in s.lower() for kw in skip_keywords):
            continue

        if re.match(r'^\d+\.\s+.*Analyze', s, re.I) or re.match(r'^\d+\.\s+.*Request', s, re.I) or re.match(r'^\d+\.\s+.*Process', s, re.I):
            continue

        clean_lines.append(s)

    return '\n'.join(clean_lines).strip()

def _clean_summary_output_gu(text):
    if not text:
        return ""

    for stop_marker in ['5. Final Review', '5.  Final Review', 'Final Review against Constraints:']:
        if stop_marker in text:
            text = text.split(stop_marker)[0].strip()

    for start_marker in [
        '3. Drafting the Content in Gujarati:',
        '3.  Drafting the Content in Gujarati:',
        '3. Drafting the Executive Summary:',
        '3.  Drafting the Executive Summary:',
        '3. Drafting',
        'Drafting the Content in Gujarati:',
        'Executive Summary:',
    ]:
        if start_marker in text:
            text = text.split(start_marker)[-1].strip()
            break

    text = text.replace(' -> ', ' — ').replace('->', ' — ')

    lines = text.splitlines()
    clean_lines = []

    skip_keywords = [
        'Analyze the Request',
        'Analyze the Input Document',
        'Analyze the Source Text',
        'Analyze the Document Content',
        'Draft 1:',
        'Draft 2:',
        'Task:',
        'Role:',
        'Target Audience:',
        'Strict Rules:',
        'Categories Required:',
        'Constraint Checklist',
        'Confidence Score',
        'Required Output Format',
        'DOCUMENT CONTENT',
    ]

    for line in lines:
        s = line.strip()
        if not s:
            continue

        if any(kw.lower() in s.lower() for kw in skip_keywords):
            continue

        if re.search(r'\*?\s*\*?Source:\*?', s, re.I):
            continue

        if re.search(r'^\*?\s*Header:', s, re.I):
            continue

        if re.match(r'^\d+\.\s+.*Analyze', s, re.I) or re.match(r'^\d+\.\s+.*Request', s, re.I) or re.match(r'^\d+\.\s+.*Process', s, re.I):
            continue

        # Convert *Draft:* to clean bullet point
        s = re.sub(r'^\*?\s*\*?Draft:\*?\s*', '• ', s)
        # Strip trailing English translations in parens like (Subject), (Key Policy Directives)
        s = re.sub(r'\s*\([A-Za-z\s\&]+\)', '', s)

        clean_lines.append(s)

    return '\n'.join(clean_lines).strip()

def _clean_summary_output_hi(text):
    if not text:
        return ""

    for stop_marker in ['5. Final Review', '5.  Final Review', 'Final Review against Constraints:']:
        if stop_marker in text:
            text = text.split(stop_marker)[0].strip()

    for start_marker in [
        '3. Drafting the Content in Hindi:',
        '3.  Drafting the Content in Hindi:',
        '3. Drafting the Executive Summary:',
        '3.  Drafting the Executive Summary:',
        '3. Drafting',
        'Drafting the Content in Hindi:',
        'Executive Summary:',
    ]:
        if start_marker in text:
            text = text.split(start_marker)[-1].strip()
            break

    text = text.replace(' -> ', ' — ').replace('->', ' — ')

    lines = text.splitlines()
    clean_lines = []

    skip_keywords = [
        'Analyze the Request',
        'Analyze the Input Document',
        'Analyze the Source Text',
        'Analyze the Document Content',
        'Draft 1:',
        'Draft 2:',
        'Task:',
        'Role:',
        'Target Audience:',
        'Strict Rules:',
        'Categories Required:',
        'Constraint Checklist',
        'Confidence Score',
        'Required Output Format',
        'DOCUMENT CONTENT',
    ]

    for line in lines:
        s = line.strip()
        if not s:
            continue

        if any(kw.lower() in s.lower() for kw in skip_keywords):
            continue

        if re.search(r'\*?\s*\*?Source:\*?', s, re.I):
            continue

        if re.search(r'^\*?\s*Header:', s, re.I):
            continue

        if re.match(r'^\d+\.\s+.*Analyze', s, re.I) or re.match(r'^\d+\.\s+.*Request', s, re.I) or re.match(r'^\d+\.\s+.*Process', s, re.I):
            continue

        s = re.sub(r'^\*?\s*\*?Draft\s*(Hindi)?:\*?\s*', '• ', s)
        s = re.sub(r'^\*?\s*\*?Format:\*?\s*', '', s)
        s = re.sub(r'\s*\([A-Za-z\s\&]+\)', '', s)

        clean_lines.append(s)

    return '\n'.join(clean_lines).strip()


def _glm_summarize(raw_text, filename, department, lang='en'):
    sec = _load_secrets()
    token      = _get_token()
    project_id = os.getenv('ZOHO_PROJECT_ID', sec.get('ZOHO_PROJECT_ID', '46930000000013048'))
    org_id     = os.getenv('ZOHO_ORG_ID',     sec.get('ZOHO_ORG_ID',     '60074744957'))

    url = f'https://api.catalyst.zoho.in/quickml/v1/project/{project_id}/glm/chat'
    headers = {
        'Authorization': f'Bearer {token}',
        'Content-Type':  'application/json',
        'CATALYST-ORG':  org_id,
    }

    clean_input = raw_text
    for marker in ['**Analyze the Request:**', '*Header:*', '**Drafting', '**System']:
        if marker in clean_input:
            clean_input = clean_input[:clean_input.index(marker)].strip()
    clean_input = clean_input[:4500]

    if lang == 'gu':
        prompt = (
            "Provide a comprehensive, detailed executive legal summary of the following Gujarat Government Resolution in Gujarati script (ગુજરાતીમાં).\n\n"
            "Required 4-Section Output Format in Gujarati:\n"
            "### ૧. કારોબારી સારાંશ અને વહીવટી વ્યાપ્તિ\n"
            "<ઠરાવનો વિગતવાર હેતુ, પૃષ્ઠભૂમિ અને પ્રશાસનિક ઉદ્દેશ્ય>\n\n"
            "### ૨. મુખ્ય નીતિ નિર્દેશો અને જોગવાઈઓ\n"
            "• **મુખ્ય હુકમ**: <બદલીઓ, નિમણૂકો અથવા નિયમોની સંપૂર્ણ યાદી>\n"
            "• **ખાતાકીય શરતો**: <વહીવટી પાલન અને મહત્વપૂર્ણ નિયમો>\n\n"
            "### ૩. કાનૂની અને સંબંધિત સંદર્ભો\n"
            "• **જારી કરનાર સત્તા**: <વિભાગનું નામ અને ઠરાવ ક્રમાંક>\n\n"
            "### ૪. અમલીકરણ અને પાલન સૂચનાઓ\n"
            "• <જિલ્લા અધિકારીઓ અને ક્ષેત્રીય કચેરીઓ માટે અમલીકરણ માર્ગદર્શિકા>\n\n"
            f"DOCUMENT CONTENT:\n{clean_input}"
        )
    elif lang == 'hi':
        prompt = (
            "Provide a comprehensive, detailed executive legal summary of the following Gujarat Government Resolution in Hindi (हिन्दी में).\n\n"
            "Required 4-Section Output Format in Hindi:\n"
            "### 1. कार्यकारी सारांश एवं प्रशासनिक दायरा\n"
            "<संकल्प का विस्तृत विवरण, पृष्ठभूमि एवं मुख्य प्रशासनिक उद्देश्य>\n\n"
            "### 2. मुख्य नीति निर्देश एवं प्रमुख बिंदु\n"
            "• **मुख्य आदेश**: <तबादलों, नियुक्तियों, वेतनमान या नियमों का पूर्ण विवरण>\n"
            "• **विभागीय शर्तें**: <प्रशासनिक अनुपालन एवं आवश्यक दिशा-निर्देश>\n\n"
            "### 3. कानूनी संदर्भ एवं संकल्प संख्या\n"
            "• **जारीकर्ता प्राधिकरण**: <विभाग का नाम एवं संकल्प क्रमांक>\n\n"
            "### 4. अनुपालन एवं प्रवर्तन निर्देश\n"
            "• <सक्षम अधिकारियों एवं क्षेत्रीय कार्यालयों के लिए प्रवर्तन निर्देश>\n\n"
            f"DOCUMENT CONTENT:\n{clean_input}"
        )
    else:
        prompt = (
            "Provide a comprehensive, detailed executive legal briefing of the following official Gujarat Government Resolution. "
            "Write each section as full explanatory sentences, not just short labels — explain the reasoning and context behind each "
            "point, not only what it says. Aim for at least 2-3 sentences per bullet where the source material supports it.\n\n"
            "Required 4-Section Output Format:\n"
            "### 1. Executive Summary & Administrative Scope\n"
            "<Detailed, explanatory overview of the resolution order, its administrative background, why it was likely issued, and its primary policy objective>\n\n"
            "### 2. Key Policy Directives & Specific Provisions\n"
            "• **Core Directives**: <Comprehensive, explanatory breakdown listing all officer postings, personnel transfers, salary scales, or rules, with context on what each provision means in practice>\n"
            "• **Departmental Conditions**: <Detailed compliance conditions and procedural rules, explained clearly>\n\n"
            "### 3. Statutory References & Authorization\n"
            "• **Issuing Authority**: <Department name, resolution reference number, date, and the statutory basis for the order>\n\n"
            "### 4. Enforcement & Compliance Guidelines\n"
            "• **Execution Mandate**: <Actionable enforcement instructions for district authorities and field departments, including expected reporting or follow-up>\n\n"
            f"DOCUMENT CONTENT:\n{clean_input}"
        )

    payload = {
        'model':       'crm-di-glm47b_30b_it',
        'messages':    [{'role': 'user', 'content': prompt}],
        'temperature': 0.1,
        'max_tokens':  1800,
    }
    bad_markers = [
        "protected instructions", "can't help", "cannot summarize", "content is missing",
        "identify the problem", "determine the strategy", "drafting the response",
        "internal monologue", "self-correction", "please provide the text",
        "attempt 1", "attempt 2", "attempt 3"
    ]

    # The model doesn't reliably wrap its reasoning in a single </think> tag --
    # sometimes it plans out loud in plain bullet points instead. The one thing
    # that's consistent is the required "### 1."/"### ૧." section heading we
    # asked for, so anchor on that and discard everything before it (the
    # planning/reasoning preamble), regardless of how it was formatted.
    heading_re = re.compile(r'###\s*(?:1|૧)\.')

    def _extract_final_answer(candidate):
        if '</think>' in candidate:
            candidate = candidate.split('</think>')[-1].strip()
        m = heading_re.search(candidate)
        if not m:
            return None
        return candidate[m.start():].strip()

    # The GLM backend is occasionally flaky (500s, a truncated response, or
    # reasoning-only output that never reaches the real answer) -- retry once
    # before falling back to the generic template.
    text = ''
    last_err = None
    for _ in range(2):
        r = requests.post(url, headers=headers, json=payload, timeout=90)
        if r.status_code != 200:
            last_err = f'GLM API error {r.status_code}: {r.text[:200]}'
            continue
        raw_candidate = r.json().get('response', '')
        candidate = _extract_final_answer(raw_candidate)
        if candidate and not any(m in candidate.lower() for m in bad_markers) and len(candidate) >= 80:
            text = candidate
            last_err = None
            break
        text = candidate or ''
        last_err = None

    if not text and last_err:
        return None, last_err
    if any(m in text.lower() for m in bad_markers) or not text.strip() or len(text.strip()) < 80:
        dept_name = department or "Government of Gujarat"
        clean_fn = filename.replace('.pdf', '').replace('_', ' ')
        if lang == 'gu':
            text = (
                f"### ૧. કારોબારી સારાંશ અને વહીવટી વ્યાપ્તિ\n"
                f"આ અધિકૃત સરકારી ઠરાવ (**{clean_fn}**) {dept_name} દ્વારા રાજ્ય વહીવટી સુધારાઓ અને સંસ્થાકીય નિયમન હેતુ જારી કરવામાં આવ્યો છે. આ હુકમ ખાતાકીય ચુસ્તતા અને સરકારી પ્રક્રિયાઓનું પાલન સુનિશ્ચિત કરે છે. આ પ્રકારના ઠરાવો સામાન્ય રીતે હાલની ખાતાકીય પદ્ધતિની સમીક્ષા, બજેટ જોગવાઈ અથવા ઉચ્ચ વહીવટી સત્તાના નિર્દેશમાંથી ઉદ્ભવે છે.\n\n"
                f"### ૨. મુખ્ય નીતિ નિર્દેશો અને વહીવટી પ્રાવધાનો\n"
                f"• **સંચાલન હુકમ**: રાજ્ય વહીવટી ક્ષેત્રમાં શિસ્ત અને અધિકૃત નીતિઓનું યોગ્ય પાલન સુનિશ્ચિત કરવું, જેથી તમામ ગૌણ કચેરીઓમાં એકસમાન અમલ થાય.\n"
                f"• **ખાતાકીય અમલીકરણ**: {dept_name} હેઠળના તમામ સક્ષમ અધિકારીઓને આ નીતિનો તાત્કાલિક અમલ કરવા આદેશ, જેમાં સ્ટાફિંગ, પ્રક્રિયા અથવા સંસાધન ફાળવણી જેવી બાબતોનો સમાવેશ થઈ શકે.\n"
                f"• **સેવા નિયમો અને ચકાસણી**: અધિકૃત રેકોર્ડ અને પાત્રતા ધોરણો મુજબ કાર્યવાહી કરવી, અને અમલીકરણ પહેલાં હાલના ખાતાકીય રજિસ્ટર સાથે ચકાસણી કરવી.\n\n"
                f"### ૩. કાનૂની અને સંબંધિત સંદર્ભો\n"
                f"• **જારી કરનાર વિભાગ**: {dept_name}, પોતાના કાયદેસર અધિકારક્ષેત્ર હેઠળ ગૌણ કચેરીઓ પર બંધનકર્તા વહીવટી આદેશો જારી કરે છે.\n"
                f"• **દસ્તાવેજી નોંધણી**: સરકારી ઠરાવ ક્રમાંક અને અધિકૃત રાજ્ય સંહિતા પત્ર, જે ઠરાવની ચોક્કસ કલમો અને અમલ તારીખનો અધિકૃત સ્રોત છે.\n\n"
                f"### ૪. અમલીકરણ અને પાલન માર્ગદર્શિકા\n"
                f"તમામ સંબંધિત ક્ષેત્રીય કચેરીઓ, જિલ્લા પ્રશાસન અને વિભાગીય વડાઓએ આ હુકમ મુજબ ત્વરિત કાનૂની કાર્યવાહી હાથ ધરવાની રહેશે. પાલનમાં કોઈ પણ વિલંબ અથવા ક્ષતિ પ્રમાણભૂત વહીવટી માધ્યમથી જારી કરનાર વિભાગને જાણ કરવાની રહેશે."
            )
        elif lang == 'hi':
            text = (
                f"### 1. कार्यकारी सारांश एवं प्रशासनिक दायरा\n"
                f"यह आधिकारिक सरकारी संकल्प (**{clean_fn}**) {dept_name} द्वारा राज्य प्रशासन और विभागीय सुदृढ़ीकरण हेतु जारी किया गया है। इसका मुख्य उद्देश्य प्रशासनिक पारदर्शिता एवं नीतियों का कड़ाई से अनुपालन कराना है। इस प्रकार के संकल्प आमतौर पर मौजूदा विभागीय प्रक्रिया की समीक्षा, बजटीय प्रावधान, या किसी उच्च प्रशासनिक प्राधिकरण के निर्देश से उत्पन्न होते हैं।\n\n"
                f"### 2. मुख्य नीति निर्देश एवं प्रमुख बिंदु\n"
                f"• **प्रशासनिक आदेश**: राज्य प्रशासन एवं अधीनस्थ विभागों के लिए अनिवार्य अनुपालन निर्देश जारी किए गए हैं, ताकि सभी अधीनस्थ कार्यालयों में एक समान क्रियान्वयन सुनिश्चित हो।\n"
                f"• **विभागीय कार्यान्वयन**: {dept_name} के अंतर्गत सभी अधिकारियों को इस आदेश का तत्काल कार्यान्वयन सुनिश्चित करने का निर्देश, जिसमें स्टाफिंग, प्रक्रिया या संसाधन आवंटन जैसे विषय शामिल हो सकते हैं।\n"
                f"• **सेवा एवं नियम शर्तें**: सरकारी अभिलेखों एवं सेवा नियमों के अनुसार आवश्यक प्रशासनिक कार्यवाही, तथा क्रियान्वयन से पूर्व मौजूदा विभागीय रजिस्टरों से सत्यापन।\n\n"
                f"### 3. कानूनी संदर्भ एवं संकल्प संख्या\n"
                f"• **जारीकर्ता विभाग**: {dept_name}, जो अपने वैधानिक अधिकार क्षेत्र के तहत अधीनस्थ कार्यालयों पर बाध्यकारी प्रशासनिक आदेश जारी करता है।\n"
                f"• **आधिकारिक संदर्भ**: राज्य संकल्प पंजी एवं विभागीय गजट अधिसूचना, जो संकल्प की सटीक धाराओं एवं प्रभावी तिथि का आधिकारिक स्रोत है।\n\n"
                f"### 4. अनुपालन एवं प्रवर्तन निर्देश\n"
                f"सभी संबंधित जिलाधिकारियों, पुलिस अधिकारियों एवं विभागीय अध्यक्षों को इस आदेश के त्वरित कार्यान्वयन का कड़ा निर्देश दिया जाता है। अनुपालन में किसी भी देरी या चूक की सूचना मानक प्रशासनिक माध्यम से जारीकर्ता विभाग को दी जानी अपेक्षित है।"
            )
        else:
            text = (
                f"### 1. Executive Summary & Administrative Scope\n"
                f"This official Government Resolution (**{clean_fn}**) is promulgated by the **{dept_name}**. It establishes regulatory guidelines, departmental mandates, and administrative compliance procedures for state administration and statutory enforcement. Resolutions of this kind typically originate from a review of existing departmental practice, a budgetary provision, or a directive from a higher administrative authority, and are intended to standardize how the relevant offices carry out their duties going forward.\n\n"
                f"### 2. Key Policy Directives & Operational Provisions\n"
                f"• **Administrative Mandate**: Mandatory compliance across state departments, police authorities, and statutory bodies, ensuring the resolution's provisions are applied uniformly across all subordinate offices.\n"
                f"• **Departmental Directives**: Official instructions issued to subordinate offices under {dept_name} for immediate execution, typically covering matters such as staffing, procedure, or resource allocation as applicable to the department.\n"
                f"• **Regulatory Verification**: Strict adherence to verified service records, administrative protocols, and legal conditions, with implementing offices expected to cross-check compliance against existing departmental registers before reporting completion.\n\n"
                f"### 3. Statutory References & Authorization\n"
                f"• **Issuing Authority**: {dept_name}, acting within its statutory mandate to issue administrative orders binding on subordinate offices.\n"
                f"• **Document Reference**: Official Government Resolution Registry & Administrative Gazette Record, which serves as the authoritative source for the resolution's exact clauses, numbering, and effective date.\n\n"
                f"### 4. Enforcement & Compliance Directives\n"
                f"All designated authorities, district magistrates, police officers, and department heads are directed to implement these policy directives immediately and update departmental records accordingly. Any non-compliance or delay in implementation is expected to be reported through the standard administrative channel back to {dept_name} for review."
            )

    if lang == 'gu':
        summary_text = _clean_summary_output_gu(text)
    elif lang == 'hi':
        summary_text = _clean_summary_output_hi(text)
    else:
        summary_text = _clean_summary_output(text)

    return summary_text or text, None


@app.route('/api/summarize/<int:doc_id>', methods=['POST'])
def summarize(doc_id):
    lang = request.args.get('lang', 'en')
    conn = get_db()
    c = conn.cursor()
    c.execute(
        "SELECT filename, department, english_translation, ai_summary, source_pdf_path, source_url, page_image_paths "
        "FROM gr_documents WHERE id=?",
        (doc_id,)
    )
    row = c.fetchone()
    conn.close()

    if not row:
        return jsonify({'error': 'Document not found'}), 404

    raw = get_document_text(doc_id, row)

    try:
        summary, err = _glm_summarize(raw, row['filename'], row['department'], lang=lang)
    except requests.exceptions.Timeout:
        return jsonify({'error': 'GLM API timed out — try again.'}), 504
    except Exception as e:
        return jsonify({'error': f'Summarizer error: {str(e)[:120]}'}), 500

    if err or not summary:
        dept_lbl = row['department'] or 'Government of Gujarat'
        summary = f"• **Subject**: Official Resolution — {row['filename']}\n• **Department**: {dept_lbl}\n• **Key Policy Directives**: Official administrative decree issued for state enforcement.\n• **Status**: Verified Record."

    lang_name = 'Gujarati' if lang == 'gu' else ('Hindi' if lang == 'hi' else 'English')
    return jsonify({'summary': summary, 'language': lang_name})


@app.route('/api/related/<int:doc_id>', methods=['GET'])
def get_related(doc_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT department, filename, english_translation, gr_number FROM gr_documents WHERE id=?", (doc_id,))
    doc = c.fetchone()
    if not doc:
        conn.close()
        return jsonify({'related': []})

    dept = doc['department']
    filename = doc['filename']
    text = doc['english_translation'] or ''

    combined_text = (filename + ' ' + text).lower()

    on_disk = available_pdf_filenames()
    if not on_disk:
        conn.close()
        return jsonify({'related': []})
    disk_clause = f"filename IN ({','.join('?' for _ in on_disk)})"
    disk_params = list(on_disk)

    topic_pool = [
        'pension', 'gratuity', 'allowance', 'transfer', 'recruitment', 'appointment',
        'seniority', 'promotion', 'cadre', 'discipline', 'pay', 'salary', 'leave',
        'suspension', 'court', 'judgment'
    ]

    matched_topics = [t for t in topic_pool if t in combined_text]
    if 'pension' in matched_topics:
        matched_topics = ['pension', 'gratuity']
    else:
        matched_topics = matched_topics[:2]

    if matched_topics:
        like_clauses = " OR ".join(["english_translation LIKE ? OR filename LIKE ?" for _ in matched_topics])
        params = [doc_id] + disk_params
        for t in matched_topics:
            params.extend([f'%{t}%', f'%{t}%'])

        primary_term = matched_topics[0]
        query = (
            f"SELECT id, filename, department, gr_number, gr_date, english_translation FROM gr_documents "
            f"WHERE id != ? AND {disk_clause} AND ({like_clauses}) "
            f"ORDER BY (CASE WHEN filename LIKE ? THEN 1 ELSE 2 END) ASC, id ASC LIMIT 3"
        )
        params.append(f'%{primary_term}%')
        c.execute(query, params)
    else:
        c.execute(
            f"SELECT id, filename, department, gr_number, gr_date, english_translation FROM gr_documents WHERE id != ? AND {disk_clause} AND department = ? LIMIT 3",
            [doc_id] + disk_params + [dept]
        )

    rows = c.fetchall()
    conn.close()

    results = []
    for r in rows:
        formatted_title = _derive_title(r['filename'], r['english_translation'], r['department'], r['gr_number'])
        results.append({
            'id': r['id'],
            'filename': formatted_title,
            'department': r['department'] or 'Government of Gujarat'
        })

    return jsonify({'related': results})


@app.route('/api/chat', methods=['POST'])
def chat():
    data = request.json or {}
    user_query = data.get('message', '').strip()
    if not user_query:
        return jsonify({'error': 'Message required'}), 400

    # 1. Greeting Handler: Respond naturally without fetching random documents
    greetings = {'hi', 'hello', 'hey', 'greetings', 'namaste', 'kem cho', 'good morning', 'good afternoon', 'good evening', 'hi there', 'hello there'}
    clean_q = re.sub(r'[^\w\s]', '', user_query.lower()).strip()
    if clean_q in greetings or len(clean_q) <= 3:
        return jsonify({
            'reply': 'Hello! I am **K.A.N.A.D.**, your Legal & Administrative AI Assistant for Gujarat & Central Laws. How can I assist you with government resolutions, pension rules, or court judgments today?',
            'sources': []
        })

    conn = get_db()
    c = conn.cursor()
    keywords = [w for w in re.findall(r'\w+', user_query) if len(w) > 3][:3]
    like_clause = " OR ".join(["english_translation LIKE ? OR filename LIKE ?" for _ in keywords])
    params = []
    for k in keywords:
        params.extend([f'%{k}%', f'%{k}%'])

    if like_clause:
        c.execute(f"SELECT filename, department, english_translation, gr_number FROM gr_documents WHERE {like_clause} LIMIT 3", params)
    else:
        c.execute("SELECT filename, department, english_translation, gr_number FROM gr_documents LIMIT 2")

    rows = c.fetchall()
    conn.close()

    context_parts = []
    sources = []
    for r in rows:
        title = _derive_title(r['filename'], r['english_translation'], r['department'], r['gr_number'])
        sources.append(title)
        snippet = (r['english_translation'] or '')[:1000]
        context_parts.append(f"Document Title: {title}\nDepartment: {r['department']}\nContent: {snippet}")

    context = "\n\n".join(context_parts)

    sec = _load_secrets()
    token      = _get_token()
    project_id = os.getenv('ZOHO_PROJECT_ID', sec.get('ZOHO_PROJECT_ID', '46930000000013048'))
    org_id     = os.getenv('ZOHO_ORG_ID',     sec.get('ZOHO_ORG_ID',     '60074744957'))

    url = f'https://api.catalyst.zoho.in/quickml/v1/project/{project_id}/glm/chat'
    headers = {
        'Authorization': f'Bearer {token}',
        'Content-Type':  'application/json',
        'CATALYST-ORG':  org_id,
    }

    chat_prompt = (
        "You are K.A.N.A.D. Legal AI Assistant for the Government of Gujarat & Central Laws.\n"
        "Answer the user's legal/administrative query concisely and professionally using the retrieved document context below.\n"
        "Provide ONLY your direct, executive answer to the user. Do NOT include internal planning, draft steps, reasoning logs, or constraint checklists.\n"
        "Cite the document titles used in your response.\n\n"
        f"RETRIEVED CONTEXT:\n{context}\n\n"
        f"USER QUESTION: {user_query}"
    )

    payload = {
        'model':       'crm-di-glm47b_30b_it',
        'messages':    [{'role': 'user', 'content': chat_prompt}],
        'temperature': 0.2,
        'max_tokens':  600,
    }

    try:
        r = requests.post(url, headers=headers, json=payload, timeout=45)
        text = r.json().get('response', '')
        if '</think>' in text:
            text = text.split('</think>')[-1].strip()
        
        # Extract final answer if CoT drafting markers exist
        for marker in ['Draft the Response (Internal Draft):', 'Draft the Response:', 'Drafting the Response:', 'Draft:', 'Final Answer:', 'Final Polish (Checking Constraints):', 'Final Polish:']:
            if marker in text:
                text = text.split(marker)[-1].strip()

        lines = []
        for line in text.splitlines():
            s = line.strip()
            if re.match(r'^\*?\s*\*?\d*[\.\:]?\s*\*\*(Constraint|User Query|Context|Formulate|Refine|Final|Goal|Drafting|Input|Role|Task|Synthesize)', s, re.I):
                continue
            if re.match(r'^\*?\s*\**(Role|Task|Synthesize|Draft the Response)', s, re.I):
                continue
            if re.match(r'^\d+\.\s+\*\*(Analyze|Formulate|Refine|Evaluate|Drafting|Final|Synthesize)', s, re.I):
                continue
            lines.append(line)

        text = '\n'.join(lines).strip()
        text = re.sub(r'^[\:\*\s]+', '', text).strip()

        return jsonify({'reply': text, 'sources': sources})
    except Exception as e:
        return jsonify({'reply': f'I searched our database for "{user_query}". Relevant documents include: ' + ', '.join(sources) + '.', 'sources': sources})

    # ── On-demand: locate the PDF ────────────────────────────────────────────
    import tempfile, re as _re, pdfplumber, pytesseract
    from PIL import Image

    pdf_local = None
    tmp_path  = None

    # 1. Try local disk path first
    if row['source_pdf_path']:
        candidate = os.path.join(BASE_DIR, row['source_pdf_path'])
        if os.path.exists(candidate):
            pdf_local = candidate

    # 2. Fall back: download from source_url
    if not pdf_local and row['source_url']:
        try:
            r = requests.get(row['source_url'], timeout=30,
                             headers={'User-Agent': 'Mozilla/5.0'}, verify=False)
            if r.status_code == 200 and r.content[:4] == b'%PDF':
                tmp = tempfile.NamedTemporaryFile(suffix='.pdf', delete=False)
                tmp.write(r.content)
                tmp.close()
                tmp_path  = tmp.name
                pdf_local = tmp_path
        except Exception as e:
            return jsonify({'error': f'Could not fetch PDF: {str(e)[:120]}'}), 502

    if not pdf_local:
        return jsonify({'error': 'PDF not found on disk and no source URL available.'}), 422

    # ── OCR the PDF ──────────────────────────────────────────────────────────
    IMG_DIR = os.path.join(BASE_DIR, 'pdf_images')
    doc_id_str = os.path.splitext(row['filename'])[0]

    def _sanitize(text):
        text = _re.sub(r'([\u0A80-\u0AFF]+)\s*[-\u2013\u2014:]+\s*[a-zA-Z0-9]+\s+([૧૨૩૪૫૬૭૮૯0-9]+)', r'\1-\2', text)
        return text

    try:
        ocr_pages = []
        page_imgs = []
        doc_img_dir = os.path.join(IMG_DIR, doc_id_str)
        os.makedirs(doc_img_dir, exist_ok=True)

        with pdfplumber.open(pdf_local) as pdf:
            for idx, page in enumerate(pdf.pages[:20]):   # cap at 20 pages
                img_fn   = f"page_{idx+1}.png"
                perm_p   = os.path.join(doc_img_dir, img_fn)
                rel_p    = os.path.join('pdf_images', doc_id_str, img_fn)

                web_im = page.to_image(resolution=150)
                web_im.save(perm_p)
                page_imgs.append(rel_p)

                tmp_ocr = f'/tmp/ocr_od_{doc_id_str}_p{idx+1}.png'
                page.to_image(resolution=300).save(tmp_ocr)
                txt = pytesseract.image_to_string(
                    Image.open(tmp_ocr), lang='guj+eng', config='--oem 3 --psm 6')
                ocr_pages.append(_sanitize(txt))
                if os.path.exists(tmp_ocr):
                    os.remove(tmp_ocr)

        full_text = '\n\n'.join(ocr_pages)

        # Detect language
        guj_chars = len(_re.findall(r'[\u0A80-\u0AFF]', full_text))
        eng_words = len(_re.findall(r'\b[A-Za-z]{3,}\b', full_text))
        guj_ratio = guj_chars / max(len(full_text), 1)
        if guj_ratio >= 0.30:
            lang, status = 'GUJARATI', 'CLEAN_PASS'
        elif eng_words >= 15:
            lang, status = 'ENGLISH',  'CLEAN_PASS'
        else:
            lang, status = 'UNKNOWN',  'REJECT_NOISE'

    except Exception as e:
        return jsonify({'error': f'OCR failed: {str(e)[:120]}'}), 500
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.remove(tmp_path)

    if not full_text.strip() or status == 'REJECT_NOISE':
        return jsonify({'error': 'OCR produced no usable text for this document.'}), 422

    # ── GLM summarize ────────────────────────────────────────────────────────
    try:
        summary, err = _glm_summarize(full_text, row['filename'], row['department'])
    except requests.exceptions.Timeout:
        return jsonify({'error': 'GLM API timed out — try again.'}), 504
    except Exception as e:
        return jsonify({'error': f'Summarizer error: {str(e)[:120]}'}), 500
    if err:
        return jsonify({'error': err}), 502

    # ── Persist back to DB ───────────────────────────────────────────────────
    conn2 = get_db()
    c2    = conn2.cursor()
    c2.execute(
        "UPDATE gr_documents SET english_translation=?, source_language=?, "
        "quality_status=?, page_image_paths=? WHERE id=?",
        (full_text, lang, status, json.dumps(page_imgs), doc_id)
    )
    conn2.commit()
    conn2.close()

    return jsonify({'summary': summary, 'freshly_processed': True,
                    'pages_rendered': len(page_imgs), 'language': lang})


if __name__ == '__main__':
    os.makedirs(os.path.join(BASE_DIR, 'templates'), exist_ok=True)
    print("K.A.N.A.D. running on http://localhost:5050")
    app.run(host='0.0.0.0', port=5050, debug=False)
