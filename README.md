# K.A.N.A.D. — Gujarat Legal AI & Document Intelligence Platform

**K.A.N.A.D.** (Knowledgeable Automated Network for Administrative Decisions) is a legal search, document discovery, and AI-powered intelligence platform built for Gujarat Government Resolutions (GRs), police orders, pension circulars, and administrative decrees.

---

## 🌟 Key Features

- **Home & Police Department Prioritized Feed**: Smart SQL sorting prioritizes verified Home Department, Police orders, and pension circulars.
- **Dedicated Document Detail View**: Detailed view for every resolution (`/doc/<id>`) with rendered page previews and language-specific AI summary tabs (**English**, **ગુજરાતી**, **હિન્દી**).
- **RAG-based AI Legal Assistant**: Integrated floating chat assistant on all pages, providing clean context-anchored answers from the document corpus without model reasoning noise.
- **Zero-Latency Client Caching**: Full client-side caching (`localStorage`) for AI briefings and search feeds to minimize server overhead.
- **Official Government Links & PDF Downloads**: Direct access to live government sources and instant local PDF downloads.

---

## 🛠️ Architecture & Tech Stack

- **Backend**: Python 3 / Flask
- **Database**: SQLite3 (`database/gujarat_gr_intel.db`)
- **LLM Serving**: Zoho Catalyst QuickML (GLM-4.7-flash)
- **Frontend**: Responsive Vanilla HTML5, CSS3 design system, and JavaScript (ES6+)

---

## 🚀 Quickstart Guide

### 1. Environment Setup
```bash
# Clone the repository
git clone https://github.com/surdeep-kannan/K.A.N.A.D.git
cd K.A.N.A.D

# Install dependencies
pip install -r requirements.txt
```

### 2. Configure Credentials
Ensure secrets are configured in `config/secrets.env` (or environment variables):
```env
ZOHO_CLIENT_ID=your_client_id
ZOHO_CLIENT_SECRET=your_client_secret
ZOHO_REFRESH_TOKEN=your_refresh_token
ZOHO_PROJECT_ID=your_project_id
ZOHO_ORG_ID=your_org_id
```

### 3. Launch Application
```bash
python3 app.py
```
Open **`http://localhost:5050`** in your browser.

---

## 📁 Repository Structure

```
├── app.py                      # Core Flask web application & API endpoints
├── database/                   # SQLite database (gujarat_gr_intel.db)
├── templates/                  # HTML templates (index.html, document_detail.html)
├── config/                     # Environment configuration & secrets handling
├── pdf_raw/                    # Sample Government Resolution PDFs
├── build_corpus_manifest.py    # Pipeline ingestion and corpus manifest script
└── README.md                   # Project documentation
```

---

## 📜 License
Developed for Gujarat Government Resolution & Police Intelligence Hackathon.
