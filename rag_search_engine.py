import json, os, re, math
import sqlite3

MANIFEST_PATH = '/home/surdeep/Documents/K.A.N.A.D/production_pipeline/vector_store/rag_documents_manifest.json'
DB_PATH = '/home/surdeep/Documents/K.A.N.A.D/production_pipeline/database/gujarat_gr_intel.db'

# Simple BM25 / TF-IDF Keyword & Metadata Hybrid Search Engine for fast RAG retrieval without heavy dependencies
class MinimalRAGEngine:
    def __init__(self, manifest_path):
        with open(manifest_path, 'r', encoding='utf-8') as f:
            self.docs = json.load(f)
            
    def search(self, query, top_k=3, topic_filter=None):
        query_words = set(re.findall(r'\w+', query.lower()))
        results = []
        
        for doc in self.docs:
            meta = doc['metadata']
            if topic_filter and topic_filter not in meta['topics']:
                continue
                
            for idx, chunk in enumerate(doc['chunks']):
                chunk_words = re.findall(r'\w+', chunk.lower())
                score = 0
                for w in query_words:
                    score += chunk_words.count(w)
                    
                # Boost score if query matches metadata directly
                if any(w in str(meta['gr_number']).lower() for w in query_words):
                    score += 5
                if any(w in str(meta['department']).lower() for w in query_words):
                    score += 2
                    
                if score > 0:
                    results.append({
                        "score": score,
                        "filename": meta['filename'],
                        "department": meta['department'],
                        "gr_number": meta['gr_number'],
                        "gr_date": meta['gr_date'],
                        "topics": meta['topics'],
                        "chunk_index": idx,
                        "text": chunk
                    })
                    
        results.sort(key=lambda x: x['score'], reverse=True)
        return results[:top_k]

if __name__ == '__main__':
    rag = MinimalRAGEngine(MANIFEST_PATH)
    
    test_queries = [
        "interceptor boats coastal security",
        "forensic science lab fee rates",
        "disability reservation in police department"
    ]
    
    print("=== HYBRID RAG SEARCH ENGINE DEMONSTRATION ===")
    for q in test_queries:
        print(f"\nQuery: '{q}'")
        res = rag.search(q, top_k=2)
        for r in res:
            print(f" -> Score: {r['score']} | {r['filename']} ({r['gr_number']}) | Date: {r['gr_date']}")
            print(f"    Excerpt: {r['text'][:120]}...")
