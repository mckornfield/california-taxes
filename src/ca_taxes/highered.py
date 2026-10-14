"""Groupings for IPEDS finance data on California public higher education (data/raw/ipeds/).

IPEDS reports each institution's expenses by *function* (what the money was for) and, separately, by *natural
class* (salaries, fringe benefits, everything else); revenues by source. The labels below are this site's.
Break points in the filings: through FY2009 depreciation and interest are their own lines and plant operation and
maintenance (O&M) is its own function; FY2010-2015 depreciation and interest are spread across functions but O&M is still
its own line (F1C081); from FY2016 O&M is spread across functions too.
"""

SYSTEMS = ["UC", "CSU", "Community colleges"]

FUNCTION_COLUMNS = {  # IPEDS variable -> label
    "F1C011": "Instruction",
    "F1C021": "Research",
    "F1C031": "Public service",
    "F1C051": "Academic support (libraries, deans, museums)",
    "F1C061": "Student services (admissions, advising, aid administration)",
    "F1C071": "Institutional support (administration)",
    "F1C101": "Scholarships and fellowships",
    "F1C111": "Auxiliary enterprises (housing, dining, bookstores)",
    "F1C121": "Hospitals and clinical care",
    "F1C131": "Independent operations",
    "F1C141": "Other, unassigned (grows after FY2016)",
    "F1C081": "Plant operation and maintenance (own line to FY2015)",
}
RESIDUAL = "Depreciation, interest and other (own line to FY2009)"
FUNCTION_ORDER = list(FUNCTION_COLUMNS.values()) + [RESIDUAL]
# the 'core' mission: spending that is not hospitals, housing/dining/bookstores, independent operations or aid
CORE = ["Instruction", "Research", "Public service", "Academic support (libraries, deans, museums)",
        "Student services (admissions, advising, aid administration)", "Institutional support (administration)",
        "Plant operation and maintenance (own line to FY2015)"]

REVENUE_GROUPS = {  # label -> IPEDS variables
    "Tuition and fees": ["F1B01"],
    "State appropriations": ["F1B11"],
    "State grants and contracts": ["F1B03", "F1B14"],
    "Local property taxes (community colleges)": ["F1B12", "F1B15"],
    "Federal grants, contracts and Pell": ["F1B02", "F1B10", "F1B13"],
    "Hospitals, clinics and professional fees": ["F1B06", "F1B07", "F1B26"],
    "Housing, dining and other sales": ["F1B05", "F1B08"],
    "Gifts and private grants": ["F1B04", "F1B16"],
    "Capital appropriations and grants": ["F1B20", "F1B21"],
    "Investment income and other": ["F1B17", "F1B18", "F1B22", "F1B23"],
}
REVENUE_ORDER = list(REVENUE_GROUPS)
