"""Crosswalks for California's Standardized Account Code Structure (SACS), used with data/raw/cde/.

SACS codes every school expenditure by *object* (what was bought) and *function* (what it was for).
Object ranges: 1xxx certificated (teacher-type) salaries, 2xxx classified (other staff) salaries, 3xxx
employee benefits, 4xxx books and supplies, 5xxx services and operating, 6xxx capital outlay,
7xxx other outgo. The groupings below are this site's, built from the code titles CDE publishes
(data/raw/cde/sacs_object_codes.csv); they are chosen to separate pensions, health benefits, teacher
pay and supplies.
"""

# Funds whose spending is not school spending: pass-through and internal accounting, or fiduciary
EXCLUDED_FUNDS = {"08", "10", "66", "67", "71", "72", "73", "76", "95", "96", "97"}
# 08 student activity, 10 special-ed pass-through, 66 warehouse revolving, 67 self-insurance,
# 71 retiree benefit trust, 73 foundation trust, 76 warrant/pass-through, 95 student body, 72/96/97 obsolete.
# Without these, statewide totals double count (fund 76 alone is ~$39B of 'funds distributed to others').

# Objects that move money between agencies or funds rather than buy something
EXCLUDED_OBJECT_PREFIXES = ("72", "73", "75", "76")  # transfers to other agencies, indirect-cost transfers, funds distributed, interfund transfers

GROUPS = [  # order used on charts
    "Teachers' salaries", "Other certificated salaries", "Classified staff salaries", "Pensions", "Health insurance",
    "Other benefits", "Books and supplies", "Food", "Services and operating", "Capital outlay", "Debt service and other",
]


def object_group(code: str) -> str | None:
    """Group for an expenditure object code, or None if it is not an expenditure (revenue, balance sheet) or is excluded."""
    if not code or code[0] not in "1234567" or code.startswith(EXCLUDED_OBJECT_PREFIXES):
        return None
    if code.startswith("11"):
        return "Teachers' salaries"
    if code[0] == "1":
        return "Other certificated salaries"  # pupil support (counselors, nurses), administrators, other
    if code[0] == "2":
        return "Classified staff salaries"  # aides, support, clerical, administrators
    if code[0] == "3":
        if code[:2] in ("31", "32"):
            return "Pensions"  # STRS (31xx) and PERS (32xx), employer contributions
        if code[:2] == "34":
            return "Health insurance"  # health and welfare benefits
        return "Other benefits"  # Social Security/Medicare, unemployment, workers' comp, retiree health (OPEB), other
    if code[0] == "4":
        return "Food" if code.startswith("47") else "Books and supplies"
    if code[0] == "5":
        return "Services and operating"
    if code[0] == "6":
        return "Capital outlay"
    return "Debt service and other"  # tuition and excess-cost payments, debt service (interest and principal), other


def object_category(code: str) -> str | None:
    """Finer label for the detail charts."""
    g = object_group(code)
    if g is None:
        return None
    fine = {
        "1100": "Teachers", "1200": "Pupil support (counselors, nurses)", "1300": "Supervisors and administrators", "1900": "Other certificated",
        "2100": "Instructional aides", "2200": "Support (custodians, drivers, food workers)", "2300": "Supervisors and administrators (classified)",
        "2400": "Clerical, technical, office", "2900": "Other classified",
        "3101": "STRS (teachers' retirement)", "3102": "STRS (teachers' retirement)", "3201": "PERS (classified retirement)", "3202": "PERS (classified retirement)",
        "3301": "Social Security and Medicare", "3302": "Social Security and Medicare", "3311": "Social Security and Medicare", "3312": "Social Security and Medicare",
        "3401": "Health and welfare", "3402": "Health and welfare",
        "4100": "Textbooks and core curricula", "4200": "Other books and reference", "4300": "Materials and supplies", "4400": "Equipment (noncapitalized)", "4700": "Food",
        "5100": "Subagreements for services", "5500": "Utilities and housekeeping", "5600": "Rentals, repairs, leases", "5800": "Professional and consulting services",
        "5400": "Insurance", "5450": "Insurance", "5440": "Insurance",
    }
    if code in fine:
        return fine[code]
    if g == "Other benefits":
        return "Unemployment, workers' comp, retiree health, other"
    if g == "Services and operating":
        return "Travel, dues, communications, other"
    if g == "Capital outlay":
        return "Capital outlay"
    if g == "Debt service and other":
        return "Debt principal" if code in ("7433", "7439") else ("Debt interest" if code in ("7434", "7438") else "Tuition, excess-cost payments, other")
    return g


def function_group(code: str) -> str:
    """Group for a SACS function code (what the money was for)."""
    n = int(code) if code.isdigit() else 0
    if 1000 <= n < 2000:
        return "Classroom instruction (incl. special ed)"
    if n in (2700,):
        return "School administration"
    if 2000 <= n < 3000:
        return "Instructional support (curriculum, library, supervision)"
    if n == 3600:
        return "Pupil transportation"
    if n == 3700:
        return "Food services"
    if 3000 <= n < 4000:
        return "Pupil services (counseling, health, psychology)"
    if 4000 <= n < 7000:
        return "Ancillary, community and enterprise"
    if 7000 <= n < 8000:
        return "General administration and data processing"
    if n == 8500:
        return "Facilities construction"
    if 8000 <= n < 9000:
        return "Plant maintenance and operations"
    if n in (9100, 9200) or 9000 <= n < 10000:
        return "Debt service and transfers"
    return "Other"


FUNCTION_ORDER = [
    "Classroom instruction (incl. special ed)", "Instructional support (curriculum, library, supervision)", "School administration",
    "Pupil services (counseling, health, psychology)", "Pupil transportation", "Food services", "Ancillary, community and enterprise",
    "General administration and data processing", "Plant maintenance and operations", "Facilities construction", "Debt service and transfers", "Other",
]
