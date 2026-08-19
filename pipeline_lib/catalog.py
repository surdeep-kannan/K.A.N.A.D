"""Static classification registry for pdf_raw/<source> folders.

corpus_manifest.json (built by build_corpus_manifest.py) tells you how many
files a source has and its fetch status. It doesn't say what *kind* of
source it is -- this module fills that gap for the API/frontend layer: which
jurisdiction it belongs to (Central Government vs Gujarat State) and what
document type it mostly contains (the PS's "Document Categorization Module").

Sources not listed here fall back to DEFAULT_CLASSIFICATION rather than
raising, since pdf_raw/ gets new folders added by fetch scripts over time.
"""

CENTRAL = "Central Government"
GUJARAT_STATE = "Gujarat State"
MIXED = "Central + Gujarat State"

GR_CIRCULAR = "Government Resolution / Circular"
GAZETTE = "Gazette Notification"
JUDGMENT = "Court Judgment"
ACT_RULE = "Act / Rule"
UNCLASSIFIED = "Unclassified"

DEFAULT_CLASSIFICATION = {
    "display_name": None,  # filled in from the source key if absent
    "jurisdiction": GUJARAT_STATE,
    "doc_type": GR_CIRCULAR,
}

CATALOG = {
    # Central Government
    "egazette_central": {"display_name": "Central Gazette (egazette.gov.in)", "jurisdiction": CENTRAL, "doc_type": GAZETTE},
    "mha_central": {"display_name": "Ministry of Home Affairs", "jurisdiction": CENTRAL, "doc_type": GR_CIRCULAR},

    # Mixed -- disambiguated per-document via the manifest's "collection" field
    "india_code": {"display_name": "India Code (Acts & Rules)", "jurisdiction": MIXED, "doc_type": ACT_RULE},

    # Judicial
    "gujarat_hc_judgments": {"display_name": "Gujarat High Court Judgments", "jurisdiction": GUJARAT_STATE, "doc_type": JUDGMENT},

    # Gujarat gazette
    "egazette_state": {"display_name": "Gujarat State Gazette", "jurisdiction": GUJARAT_STATE, "doc_type": GAZETTE},

    # Gujarat GAD divisions
    "gad_personnel": {"display_name": "GAD - Personnel Division", "jurisdiction": GUJARAT_STATE, "doc_type": GR_CIRCULAR},
    "gad_planning": {"display_name": "GAD - Planning Division", "jurisdiction": GUJARAT_STATE, "doc_type": GR_CIRCULAR},
    "gad_admin_reforms": {"display_name": "GAD - Administrative Reforms & Training (ARTD)", "jurisdiction": GUJARAT_STATE, "doc_type": GR_CIRCULAR},

    # Gujarat departments with real content
    "home_department": {"display_name": "Home Department", "jurisdiction": GUJARAT_STATE, "doc_type": GR_CIRCULAR},
    "labour_employment": {"display_name": "Labour & Employment Department", "jurisdiction": GUJARAT_STATE, "doc_type": GR_CIRCULAR},
    "labour_deeper": {"display_name": "Labour & Employment Department", "jurisdiction": GUJARAT_STATE, "doc_type": GR_CIRCULAR},
    "gudm_urban_dev": {"display_name": "Urban Development & Urban Housing Department", "jurisdiction": GUJARAT_STATE, "doc_type": GR_CIRCULAR},
    "urban_dev": {"display_name": "Urban Development & Urban Housing Department", "jurisdiction": GUJARAT_STATE, "doc_type": GR_CIRCULAR},
    "panchayat_rural_housing": {"display_name": "Panchayat, Rural Housing & Rural Development Department", "jurisdiction": GUJARAT_STATE, "doc_type": GR_CIRCULAR},
    "panchayat_deeper": {"display_name": "Panchayat, Rural Housing & Rural Development Department", "jurisdiction": GUJARAT_STATE, "doc_type": GR_CIRCULAR},
    "forest_environment": {"display_name": "Forests & Environment Department", "jurisdiction": GUJARAT_STATE, "doc_type": GR_CIRCULAR},
    "health_family_welfare": {"display_name": "Health & Family Welfare Department", "jurisdiction": GUJARAT_STATE, "doc_type": GR_CIRCULAR},
    "sports_youth": {"display_name": "Sports, Youth & Cultural Activities Department", "jurisdiction": GUJARAT_STATE, "doc_type": GR_CIRCULAR},
    "climate_change": {"display_name": "Climate Change Department", "jurisdiction": GUJARAT_STATE, "doc_type": GR_CIRCULAR},
    "women_child_dev": {"display_name": "Women & Child Development Department", "jurisdiction": GUJARAT_STATE, "doc_type": GR_CIRCULAR},
    "revenue_circulars": {"display_name": "Revenue Department", "jurisdiction": GUJARAT_STATE, "doc_type": GR_CIRCULAR},
    "ports_transport": {"display_name": "Ports & Transport Department", "jurisdiction": GUJARAT_STATE, "doc_type": GR_CIRCULAR},
    "info_broadcasting": {"display_name": "Information & Broadcasting Department", "jurisdiction": GUJARAT_STATE, "doc_type": GR_CIRCULAR},
    "roads_buildings": {"display_name": "Roads & Buildings Department", "jurisdiction": GUJARAT_STATE, "doc_type": GR_CIRCULAR},
    "food_civil_supplies": {"display_name": "Food, Civil Supplies & Consumer Affairs Department", "jurisdiction": GUJARAT_STATE, "doc_type": GR_CIRCULAR},
    "finance_alt": {"display_name": "Finance Department", "jurisdiction": GUJARAT_STATE, "doc_type": GR_CIRCULAR},
    "central_sample": {"display_name": "Central Government (sample)", "jurisdiction": CENTRAL, "doc_type": UNCLASSIFIED},

    # Blocked -- covered via external_sources.json / external_link, zero local files
    "revenue_department": {"display_name": "Revenue Department", "jurisdiction": GUJARAT_STATE, "doc_type": GR_CIRCULAR},
    "finance_department": {"display_name": "Finance Department", "jurisdiction": GUJARAT_STATE, "doc_type": GR_CIRCULAR},
    "education": {"display_name": "Education Department", "jurisdiction": GUJARAT_STATE, "doc_type": GR_CIRCULAR},
    "industries_mines": {"display_name": "Industries & Mines Department", "jurisdiction": GUJARAT_STATE, "doc_type": GR_CIRCULAR},
    "legal_department": {"display_name": "Legal Department", "jurisdiction": GUJARAT_STATE, "doc_type": GR_CIRCULAR},
    "legislative_parliamentary": {"display_name": "Legislative & Parliamentary Affairs Department", "jurisdiction": GUJARAT_STATE, "doc_type": ACT_RULE},
    "agri_cooperation": {"display_name": "Agriculture, Farmers Welfare & Cooperation Department", "jurisdiction": GUJARAT_STATE, "doc_type": GR_CIRCULAR},
    "social_justice": {"display_name": "Social Justice & Empowerment Department", "jurisdiction": GUJARAT_STATE, "doc_type": GR_CIRCULAR},
    "narmada_water": {"display_name": "Narmada, Water Resources, Water Supply & Kalpsar Department", "jurisdiction": GUJARAT_STATE, "doc_type": GR_CIRCULAR},
    "gad_nri": {"display_name": "NRI Division (GAD)", "jurisdiction": GUJARAT_STATE, "doc_type": GR_CIRCULAR},
    "women_child_deeper": {"display_name": "Women & Child Development Department", "jurisdiction": GUJARAT_STATE, "doc_type": GR_CIRCULAR},
    "rural_dev": {"display_name": "Commissionerate of Rural Development", "jurisdiction": GUJARAT_STATE, "doc_type": GR_CIRCULAR},

    # Third-party mirrors, deliberately not crawled
    "aggregator_gujaratgr": {"display_name": "GujaratGR.in (third-party mirror, not crawled)", "jurisdiction": GUJARAT_STATE, "doc_type": UNCLASSIFIED},
    "aggregator_grportal": {"display_name": "GR Portal (third-party mirror, not crawled)", "jurisdiction": GUJARAT_STATE, "doc_type": UNCLASSIFIED},

    "_root_untracked": {"display_name": "Untracked (loose files in pdf_raw/)", "jurisdiction": GUJARAT_STATE, "doc_type": UNCLASSIFIED},
}


def classify(source_key):
    entry = CATALOG.get(source_key, {})
    display_name = entry.get("display_name") or source_key.replace("_", " ").title()
    return {
        "display_name": display_name,
        "jurisdiction": entry.get("jurisdiction", DEFAULT_CLASSIFICATION["jurisdiction"]),
        "doc_type": entry.get("doc_type", DEFAULT_CLASSIFICATION["doc_type"]),
    }
