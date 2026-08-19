import os, sys, requests, json, time, re, sqlite3
import pdfplumber
import pytesseract
from PIL import Image

BASE_DIR = '/home/surdeep/Documents/K.A.N.A.D/production_pipeline'
PDF_DIR = os.path.join(BASE_DIR, 'pdf_raw')
IMG_DIR = os.path.join(BASE_DIR, 'pdf_images')
OUT_DIR = os.path.join(BASE_DIR, 'translated_en')
DB_PATH = os.path.join(BASE_DIR, 'database', 'gujarat_gr_intel.db')

for d in [PDF_DIR, IMG_DIR, OUT_DIR, os.path.dirname(DB_PATH)]:
    os.makedirs(d, exist_ok=True)

# 1. Database Init with Source Verification & Per-Field Confidence Schema
def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS gr_documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT UNIQUE,
            title TEXT,
            doc_type TEXT,
            department TEXT,
            gr_number TEXT,
            gr_date TEXT,
            source_language TEXT,
            quality_status TEXT,
            date_confidence TEXT,
            gr_number_confidence TEXT,
            english_translation TEXT,
            source_pdf_path TEXT,
            page_image_paths TEXT,
            source_url TEXT,
            processed_timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    # Migration helper if columns missing on existing DB
    cursor.execute("PRAGMA table_info(gr_documents)")
    existing_cols = [col[1] for col in cursor.fetchall()]
    if "source_pdf_path" not in existing_cols:
        cursor.execute("ALTER TABLE gr_documents ADD COLUMN source_pdf_path TEXT")
    if "page_image_paths" not in existing_cols:
        cursor.execute("ALTER TABLE gr_documents ADD COLUMN page_image_paths TEXT")
    if "source_url" not in existing_cols:
        cursor.execute("ALTER TABLE gr_documents ADD COLUMN source_url TEXT")
    conn.commit()
    conn.close()

# 2. Secure OAuth & Credential Isolation Helper
def load_secrets():
    env_file = os.path.join(BASE_DIR, 'config', 'secrets.env')
    secrets = {}
    if os.path.exists(env_file):
        with open(env_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    k, v = line.split('=', 1)
                    secrets[k.strip()] = v.strip().strip('"').strip("'")
    return secrets

def get_zoho_token():
    sec = load_secrets()
    client_id = os.getenv('ZOHO_CLIENT_ID', sec.get('ZOHO_CLIENT_ID'))
    client_secret = os.getenv('ZOHO_CLIENT_SECRET', sec.get('ZOHO_CLIENT_SECRET'))
    refresh_token = os.getenv('ZOHO_REFRESH_TOKEN', sec.get('ZOHO_REFRESH_TOKEN'))
    
    resp = requests.post('https://accounts.zoho.in/oauth/v2/token', data={
        'grant_type': 'refresh_token',
        'client_id': client_id,
        'client_secret': client_secret,
        'refresh_token': refresh_token,
    })
    return resp.json().get('access_token')

def get_zoho_headers():
    sec = load_secrets()
    token = get_zoho_token()
    return {
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json',
        'CATALYST-ORG': os.getenv('ZOHO_ORG_ID', sec.get('ZOHO_ORG_ID', '60074744957'))
    }, os.getenv('ZOHO_PROJECT_ID', sec.get('ZOHO_PROJECT_ID', '46930000000013048'))

def sanitize_ocr_text(text):
    # Generalized pattern: Any Gujarati word followed by hyphen, stray Latin digit/noise, then Gujarati/Latin numbers
    # e.g., 'ફેઝ- 4 ૨' -> 'ફેઝ-૨', 'તબક્કા- 1 ૩' -> 'તબક્કા-૩'
    text = re.sub(r'([\u0A80-\u0AFF]+)\s*[-–—:]+\s*[a-zA-Z0-9]+\s+([૧૨૩૪૫૬૭૮૯0-9]+)', r'\1-\2', text)
    return text

# 3. Dual-Pass OCR & Quality Classifier with Permanent Page Image Persistence
def process_pdf_ocr(pdf_path):
    fname = os.path.basename(pdf_path)
    doc_id = os.path.splitext(fname)[0]
    ocr_pages = []
    
    doc_img_dir = os.path.join(IMG_DIR, doc_id)
    os.makedirs(doc_img_dir, exist_ok=True)
    
    page_img_rel_paths = []
    
    with pdfplumber.open(pdf_path) as pdf:
        for idx, page in enumerate(pdf.pages):
            img_filename = f"page_{idx+1}.png"
            perm_img_path = os.path.join(doc_img_dir, img_filename)
            rel_img_path = os.path.join("pdf_images", doc_id, img_filename)
            
            # Render and save permanent 150 DPI image for web viewer
            web_im = page.to_image(resolution=150)
            web_im.save(perm_img_path)
            page_img_rel_paths.append(rel_img_path)
            
            # Temporary crop/OCR at 300 DPI for high fidelity
            tmp_ocr_path = f"/tmp/ocr_tmp_{doc_id}_p{idx+1}.png"
            ocr_im = page.to_image(resolution=300)
            ocr_im.save(tmp_ocr_path)
            
            page_text = pytesseract.image_to_string(Image.open(tmp_ocr_path), lang='guj+eng', config='--oem 3 --psm 6')
            page_text = sanitize_ocr_text(page_text)
            ocr_pages.append(page_text)
            
            if os.path.exists(tmp_ocr_path):
                os.remove(tmp_ocr_path)
            
    full_ocr_text = "\n\n".join(ocr_pages)
    
    total_len = len(full_ocr_text)
    guj_chars = len(re.findall(r'[\u0A80-\u0AFF]', full_ocr_text))
    eng_words = len(re.findall(r'\b[A-Za-z]{3,}\b', full_ocr_text))
    guj_ratio = guj_chars / total_len if total_len > 0 else 0
    
    status = "REJECT_NOISE"
    lang = "UNKNOWN"
    if guj_ratio >= 0.30:
        lang, status = "GUJARATI", "PASS"
    elif guj_ratio < 0.15 and eng_words >= 15:
        lang, status = "ENGLISH", "PASS"
        
    return full_ocr_text, lang, status, page_img_rel_paths

# 4. Targeted High-DPI (400 DPI) Dynamic Multi-Scale Header Crop Parser
def extract_high_dpi_header_gr(pdf_path):
    try:
        with pdfplumber.open(pdf_path) as pdf:
            page = pdf.pages[0]
            w, h = page.width, page.height
            # Dynamic crop from top to 45% height (covers long subject titles without missing header block)
            crop_box = (0, 0, w, int(h * 0.45))
            cropped = page.crop(crop_box)
            high_dpi_img = cropped.to_image(resolution=400)
            
            crop_tmp_path = f"/tmp/crop_gr_{os.path.basename(pdf_path)}.png"
            high_dpi_img.save(crop_tmp_path)
            
            # High-resolution PSM 6 OCR targeting alphanumeric legal codes
            crop_text = pytesseract.image_to_string(Image.open(crop_tmp_path), lang='guj+eng', config='--oem 3 --psm 6')
            
            # Slice strictly BEFORE References / Preamble
            ref_match = re.search(r'(?:વંચાણે\s*લીધા|વંચાણમાં\s*લીધા|વંચાણે|વંચાણમાં|અંચાણે|આમુખ|Reference:|\n\s*\|?\s*[૧1][\.\)])', crop_text, re.IGNORECASE)
            if ref_match:
                crop_text = crop_text[:ref_match.start()]
                
            gr_match = re.search(r'(?:ઠરાવ\s*ક્રમાંક|ઠરાવ\s*SUIS|ઠરાવ|ક્રમાંક|BALL\s*SULS[^\n]*|No[\.\s:]+)[\s:]*([^\n\r\|]+)', crop_text, re.IGNORECASE)
            if gr_match:
                raw_val = gr_match.group(1).strip()
                clean_val = re.sub(r'^(?:ઠરાવ\s*ક્રમાંક|ઠરાવ\s*SUIS|ઠરાવ|ક્રમાંક|No[\.\s:]+)[\s:]*', '', raw_val, flags=re.IGNORECASE).strip()
                if len(clean_val) >= 4:
                    return clean_val
    except Exception as e:
        pass
    return None

# 5. Strict Multi-Keyword Header Boundary Parser
def parse_header_metadata(text, pdf_path=None):
    header_text = text
    ref_match = re.search(r'(?:વંચાણે\s*લીધા|વંચાણમાં\s*લીધા|વંચાણે|વંચાણમાં|અંચાણે|આમુખ|Reference:|\n\s*\|?\s*[૧1][\.\)])', text, re.IGNORECASE)
    
    if ref_match:
        header_text = text[:ref_match.start()]
    else:
        header_text = '\n'.join(text.split('\n')[:12])

    # Attempt targeted high-DPI crop OCR for GR number if PDF path is provided
    header_gr = None
    if pdf_path:
        header_gr = extract_high_dpi_header_gr(pdf_path)

    # Fallback to general page OCR text if high-DPI crop OCR didn't catch a valid match
    if not header_gr:
        gr_match = re.search(r'(?:ઠરાવ\s*ક્રમાંક|ઠરાવ\s*SUIS|ઠરાવ|ક્રમાંક|BALL\s*SULS[^\n]*|No[\.\s:]+)[\s:]*([^\n\r\|]+)', header_text, re.IGNORECASE)
        if gr_match:
            raw_val = gr_match.group(1).strip()
            clean_val = re.sub(r'^(?:ઠરાવ\s*ક્રમાંક|ઠરાવ\s*SUIS|ઠરાવ|ક્રમાંક|No[\.\s:]+)[\s:]*', '', raw_val, flags=re.IGNORECASE).strip()
            header_gr = clean_val

    # Extract Document Date strictly from Header Block
    date_match = re.search(r'(?:તારીખ|તા[.\s:]*|ad:?)[\s:]*([૦-૯0-9A-Za-z\s\/.-]+)', header_text, re.IGNORECASE)
    header_date = None
    if date_match:
        raw_d = date_match.group(1).strip().split('\n')[0]
        d_clean = re.search(r'([૦-૯0-9A-Za-z\u0A80-\u0AFF]{1,2}[\/\.-][૦-૯0-9A-Za-z\u0A80-\u0AFF]{1,2}[\/\.-][૦-૯0-9A-Za-z\u0A80-\u0AFF]{2,4}|\d{1,2}\s+[A-Za-z]{3,9}\s+\d{2,4})', raw_d)
        if d_clean:
            header_date = d_clean.group(1).strip()
            
    if not header_date:
        d_search = re.search(r'([૦-૯0-9A-Za-z\u0A80-\u0AFF]{1,2}[\/\.-][૦-૯0-9A-Za-z\u0A80-\u0AFF]{1,2}[\/\.-][૦-૯0-9A-Za-z\u0A80-\u0AFF]{2,4}|\d{1,2}\s+[A-Za-z]{3,9}\s+\d{2,4})', header_text)
        header_date = d_search.group(1).strip() if d_search else None

    dept_name = "Government of Gujarat, Home Department" if ("ગૃહ વિભાગ" in header_text or "Home Department" in header_text) else "Government of Gujarat"

    # Plausible Identifier Gate
    is_valid_gr = False
    if header_gr and len(header_gr) >= 4:
        if re.search(r'[0-9\u0A80-\u0AFF]', header_gr) and ('/' in header_gr or '-' in header_gr) and 'સચિવાલય' not in header_gr and 'BALL' not in header_gr:
            is_valid_gr = True

    date_conf = "HIGH_CONFIDENCE" if (header_date and len(header_date) >= 6) else "LOW_CONFIDENCE"
    gr_conf = "HIGH_CONFIDENCE" if is_valid_gr else "LOW_CONFIDENCE"
    clean_gr = header_gr if is_valid_gr else "Low Confidence / Parse Body"

    if date_conf == "HIGH_CONFIDENCE" and gr_conf == "HIGH_CONFIDENCE":
        overall_status = "CLEAN_PASS"
    elif date_conf == "HIGH_CONFIDENCE" or gr_conf == "HIGH_CONFIDENCE":
        overall_status = "PARTIAL_METADATA_PASS"
    else:
        overall_status = "LOW_CONFIDENCE_METADATA"

    return {
        "department": dept_name,
        "gr_number": clean_gr,
        "gr_date": header_date if header_date else "Low Confidence / Parse Body",
        "date_confidence": date_conf,
        "gr_number_confidence": gr_conf,
        "overall_status": overall_status
    }

# 6. Bulk Body Text Translation via Zoho GLM 4.7
def translate_glm(text, pdf_path=None):
    headers, project_id = get_zoho_headers()
    url = f'https://api.catalyst.zoho.in/quickml/v1/project/{project_id}/glm/chat'
    
    meta = parse_header_metadata(text, pdf_path)

    prompt = (
        "Translate the following official Gujarati Government Resolution into clean, fluent, professional English paragraphs.\n\n"
        "CRITICAL TRANSLATION ACCURACY RULES:\n"
        "1. NUMERAL ACCURACY: Pay extreme attention to Gujarati digits (e.g. છ=6, ૪=4, ૭=7, ૮=8). Do NOT confuse 'છ' (6) with 4.\n"
        "2. PROPER NOUNS & LOCATIONS: Transliterate Gujarati place names accurately (e.g. છારોડી = Charodi, not Chanchalguda).\n"
        "3. LITERAL FIDELITY: Translate official titles and financial amounts (rupees, dates, deadlines) literally without inventing external places or terms.\n"
        "4. Output ONLY clean narrative English paragraphs without step-by-step breakdowns or meta-commentary.\n\n"
        f"GUJARATI SOURCE TEXT:\n{text[:4500]}"
    )

    payload = {
        'model': 'crm-di-glm47b_30b_it',
        'messages': [
            {'role': 'user', 'content': prompt}
        ],
        'temperature': 0.0,
        'max_tokens': 3000
    }
    
    try:
        r = requests.post(url, headers=headers, json=payload, timeout=90)
        if r.status_code == 200:
            res_text = r.json().get('response', '')
            
            if '</think>' in res_text:
                res_text = res_text.split('</think>')[-1].strip()
            
            # Strip GLM reasoning preambles if present
            if "**Analyze the Request:**" in res_text:
                res_text = res_text.split("*Preamble:*")[-1] if "*Preamble:*" in res_text else res_text
            
            # Clean up residual markdown formatting lines
            lines = res_text.split('\n')
            clean_lines = []
            for line in lines:
                if '->' in line:
                    line = line.split('->')[-1].strip()
                line = re.sub(r'^\s*[\*\-\•\d\.]+\s*', '', line).strip()
                line = re.sub(r'^\*+[^*]+\*+:\s*', '', line).strip()
                if line and not line.startswith("Analyze the") and not line.startswith("Header:") and not line.startswith("Reference:"):
                    clean_lines.append(line)
                    
            clean_text = ' '.join(clean_lines).strip()
            # Final sanitize of leftover meta-text headers
            clean_text = re.sub(r'^.*?Preamble\.\s*', '', clean_text)
            meta["translation"] = clean_text
            return meta
    except Exception as e:
        print(f"GLM Translation Error: {e}")
    return None

# Main Execution Loop
if __name__ == '__main__':
    init_db()
    PDF_DIR = "/home/surdeep/Documents/K.A.N.A.D/production_pipeline/pdf_curated_batch"
    pdf_files = sorted([os.path.join(PDF_DIR, f) for f in os.listdir(PDF_DIR) if f.endswith('.pdf')])
    print(f"Found {len(pdf_files)} curated documents in pipeline processing queue.")
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    for pdf_path in pdf_files:
        fname = os.path.basename(pdf_path)
        print(f"\nProcessing {fname}...")
        try:
            ocr_text, lang, status, page_imgs = process_pdf_ocr(pdf_path)
        except Exception as err:
            print(f"Skipping corrupted PDF {fname}: {err}")
            continue
        
        json_page_imgs = json.dumps(page_imgs)
        rel_pdf_path = os.path.relpath(pdf_path, BASE_DIR)
        
        # Source Web URL Mapping Lookup (reads url_manifest.json if available or fallback to domain)
        source_url = None
        manifest_file = os.path.join(BASE_DIR, 'config', 'pdf_source_urls.json')
        if os.path.exists(manifest_file):
            try:
                with open(manifest_file, 'r') as mf:
                    url_map = json.load(mf)
                    source_url = url_map.get(fname)
            except Exception:
                pass
        
        if status == "REJECT_NOISE":
            print(f"   [QUARANTINED] {fname} - Corrupted OCR Noise.")
            cursor.execute("""
                INSERT OR REPLACE INTO gr_documents (
                    filename, source_language, quality_status, date_confidence, gr_number_confidence, 
                    english_translation, source_pdf_path, page_image_paths, source_url
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (fname, lang, "REJECTED_GARBLED_OCR", "LOW_CONFIDENCE", "LOW_CONFIDENCE", "Quarantined due to corrupted OCR / non-standard font.", rel_pdf_path, json_page_imgs, source_url))
            conn.commit()
            continue
            
        if lang == "ENGLISH":
            print(f"   [DIRECT INGESTION] {fname} - Native English Document.")
            out_file = os.path.join(OUT_DIR, f"{os.path.splitext(fname)[0]}_en.txt")
            with open(out_file, 'w', encoding='utf-8') as f:
                f.write(ocr_text)
            cursor.execute("""
                INSERT OR REPLACE INTO gr_documents (
                    filename, source_language, quality_status, date_confidence, gr_number_confidence, 
                    english_translation, source_pdf_path, page_image_paths, source_url
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (fname, "ENGLISH", "CLEAN_PASS", "HIGH_CONFIDENCE", "HIGH_CONFIDENCE", ocr_text, rel_pdf_path, json_page_imgs, source_url))
            conn.commit()
            continue
            
        print(f"   [GLM 4.7 TRANSLATING] {fname}...")
        parsed = translate_glm(ocr_text, pdf_path)
        
        if parsed:
            dept = parsed.get("department", "Government of Gujarat")
            gr_no = parsed.get("gr_number", "Low Confidence / Parse Body")
            gr_date = parsed.get("gr_date", "Low Confidence / Parse Body")
            date_conf = parsed.get("date_confidence", "LOW_CONFIDENCE")
            gr_conf = parsed.get("gr_number_confidence", "LOW_CONFIDENCE")
            overall_st = parsed.get("overall_status", "PARTIAL_METADATA_PASS")
            trans_text = parsed.get("translation", "")
            
            out_file = os.path.join(OUT_DIR, f"{os.path.splitext(fname)[0]}_en.txt")
            with open(out_file, 'w', encoding='utf-8') as f:
                f.write(f"Department: {dept}\nResolution No: {gr_no}\nDate: {gr_date}\n\n{trans_text}")
                
            cursor.execute("""
                INSERT OR REPLACE INTO gr_documents (
                    filename, department, gr_number, gr_date, source_language, 
                    quality_status, date_confidence, gr_number_confidence, english_translation,
                    source_pdf_path, page_image_paths, source_url
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (fname, dept, gr_no, gr_date, "GUJARATI", overall_st, date_conf, gr_conf, trans_text, rel_pdf_path, json_page_imgs, source_url))
            conn.commit()
            print(f"   [SUCCESS] Saved {fname} -> {os.path.basename(out_file)} (Status: {overall_st})")
        else:
            print(f"   [FAILED] GLM API Error on {fname}")
            
    conn.close()
    print("\n=== PIPELINE RUN COMPLETE ===")
