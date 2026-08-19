import sqlite3, os, json

DB_PATH = '/home/surdeep/Documents/K.A.N.A.D/production_pipeline/database/gujarat_gr_intel.db'
VECTOR_STORE_DIR = '/home/surdeep/Documents/K.A.N.A.D/production_pipeline/vector_store'
os.makedirs(VECTOR_STORE_DIR, exist_ok=True)

# Keyword & Rule-based Department & Topic Classifier
TOPIC_RULES = {
    "Coastal Security & Maritime": ["coastal", "boat", "interceptor", "marine", "ats", "sea", "maritime"],
    "Forensic Science & Fees": ["forensic", "fsl", "fee", "laboratory", "brain finger", "narco", "specimen"],
    "Police Personnel & Vacancy": ["police", "vacancy", "allowance", "constable", "headquarters", "civilian"],
    "Disability & Social Welfare": ["disability", "reservation", "handicapped", "social justice", "welfare"]
}

def classify_document(title, text):
    content = (title + " " + text).lower()
    matched_topics = []
    for topic, keywords in TOPIC_RULES.items():
        if any(kw in content for kw in keywords):
            matched_topics.append(topic)
    return matched_topics if matched_topics else ["General Administration"]

def prepare_rag_ingestion():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Query only validated non-garbled documents for vector RAG store
    cursor.execute("""
        SELECT filename, department, gr_number, gr_date, quality_status, english_translation 
        FROM gr_documents 
        WHERE quality_status IN ('CLEAN_PASS', 'PARTIAL_METADATA_PASS')
    """)
    rows = cursor.fetchall()
    
    rag_payload = []
    print(f"=== PREPARING RAG INGESTION STORE ({len(rows)} VALIDATED DOCS) ===")
    
    for row in rows:
        fname, dept, gr_no, gr_date, q_status, text = row
        topics = classify_document(fname, text)
        
        # Chunk text into ~500 character chunks for high-granularity vector search
        chunks = [text[i:i+600] for i in range(0, len(text), 500)]
        
        doc_entry = {
            "metadata": {
                "filename": fname,
                "department": dept,
                "gr_number": gr_no,
                "gr_date": gr_date,
                "quality_status": q_status,
                "topics": topics,
                "chunk_count": len(chunks)
            },
            "chunks": chunks
        }
        rag_payload.append(doc_entry)
        print(f"Ingested {fname}: {dept} | Topics: {topics} | Chunks: {len(chunks)}")
        
    out_path = os.path.join(VECTOR_STORE_DIR, 'rag_documents_manifest.json')
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(rag_payload, f, indent=2)
        
    print(f"\nRAG Ingestion Manifest saved successfully to: {out_path}")
    conn.close()

if __name__ == '__main__':
    prepare_rag_ingestion()
