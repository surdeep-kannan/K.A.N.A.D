import os, glob, shutil

PDF_RAW_DIR = '/home/surdeep/Documents/K.A.N.A.D/production_pipeline/pdf_raw'
BATCH_DIR = '/home/surdeep/Documents/K.A.N.A.D/production_pipeline/pdf_curated_batch'

def prepare_curated_batch():
    if os.path.exists(BATCH_DIR):
        shutil.rmtree(BATCH_DIR)
    os.makedirs(BATCH_DIR, exist_ok=True)
    
    print("=== BUILDING BALANCED MULTI-DEPARTMENT DEMO BATCH ===")
    
    # 1. Selected Home Department GRs (Diverse subjects: FSL, Coastal Security, Police Vacancy, Welfare)
    home_selection = [
        "gr_01.pdf", "gr_02.pdf", "gr_05.pdf", "gr_06.pdf", "gr_07.pdf",
        "gr_08.pdf", "gr_09.pdf", "gr_10.pdf", "gr_11.pdf", "gr_12.pdf",
        "gr_13.pdf", "gr_14.pdf", "gr_15.pdf",
        "scraped_live_gr_02.pdf", "scraped_live_gr_03.pdf" # Recent 2023/2024 Home Dept GRs
    ]
    
    # 2. Selected GAD Personnel GRs (Administrative reforms, MCC, Electoral guidelines)
    gad_selection = [
        "gad_personnel_gr_01.pdf", "gad_personnel_gr_02.pdf", "gad_personnel_gr_08.pdf"
    ]
    
    copied_count = 0
    
    print("\n[1/2] Processing Home Department Subset:")
    for fname in home_selection:
        src = os.path.join(PDF_RAW_DIR, fname)
        if os.path.exists(src):
            dest = os.path.join(BATCH_DIR, fname)
            shutil.copy(src, dest)
            print(f"  -> Added: {fname}")
            copied_count += 1
            
    print("\n[2/2] Processing GAD Department Subset:")
    for fname in gad_selection:
        src = os.path.join(PDF_RAW_DIR, fname)
        if os.path.exists(src):
            dest = os.path.join(BATCH_DIR, fname)
            shutil.copy(src, dest)
            print(f"  -> Added: {fname}")
            copied_count += 1
            
    print(f"\n=== CURATED BATCH READY: {copied_count} total documents saved to: {BATCH_DIR} ===")

if __name__ == '__main__':
    prepare_curated_batch()
