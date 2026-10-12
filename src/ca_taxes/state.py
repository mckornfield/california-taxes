"""Crosswalk from LAO's two revenue taxonomies to one stable tax-type scheme.

The LAO archive (1950-51 to 2015-16) and the current file (2016-17 on) use
different category/source names and slightly different accounting (the archive
reconciles to the Controller; the current file follows the Budget's schedules),
so the series has a visible level shift at 2015-16 -> 2016-17. We keep both
and flag the break rather than try to splice them.
"""
from __future__ import annotations

# source name (either file) -> (tax_type, group). group: Tax | Fee / other | Transfers
_TAX_TYPE = {
    # Major taxes
    "Personal Income Tax": "Personal income tax",
    "Corporation Tax": "Corporation tax",
    "Retail Sales and Use Tax": "Sales & use tax",
    "Retail Sales and Use Tax (Fiscal Recovery)": "Sales & use tax",
    "Retail Sales and Use Tax (Realignment)": "Sales & use tax",
    "Retail Sales and Use Tax - 2011 Realignment": "Sales & use tax",
    "Retail Sales and Use Tax - 1991 Realignment": "Sales & use tax",
    "Retail Sales and Use Tax - Medi-Cal Managed Care": "Sales & use tax",
    "Insurance Gross Premium Tax": "Insurance tax",
    "Insurance Gross Premiums Tax": "Insurance tax",
    "Cigarette Tax": "Tobacco taxes",
    "Alcoholic Beverages Taxes & Fees": "Alcohol taxes",
    "Estate, Inheritance & Gift Tax": "Estate & gift tax",
    "Motor Vehicle Fuel Tax (Gasoline)": "Motor fuel taxes",
    "Motor Vehicle Fuel Tax (Diesel)": "Motor fuel taxes",
    "Motor Vehicles - Fuel Tax (Gasoline)": "Motor fuel taxes",
    "Motor Vehicles - Fuel Tax (Diesel)": "Motor fuel taxes",
    "Motor Vehicle Registration": "Vehicle fees",
    "Motor Vehicle License (In-Lieu) Fees": "Vehicle fees",
    "Trailer Coach License (In-Lieu) Fees": "Vehicle fees",
    "Cannabis Excise & Cultivation Tax": "Cannabis taxes",
    "Cannabis Excise and Cultivation Tax": "Cannabis taxes",
    "Telecommunications Tax": "Other taxes",
    "Horse Racing (Pari-mutual License Fees)": "Other taxes",
    "Miscellaneous Tax Revenue": "Other taxes",
    "Other Regulatory Taxes": "Other taxes",
}
_PREFIX = [  # (startswith, tax_type)
    ("Motor Vehicles - ", "Vehicle fees"),
    ("Transportation Improvement Fee", "Vehicle fees"),
    ("Road Improvement Fee", "Vehicle fees"),
    ("Identification Card Fees", "Vehicle fees"),
    ("Mobilehome In-Lieu", "Other taxes"),
    ("Jet Fuel Tax", "Motor fuel taxes"),
    ("Alcoholic Beverage Excise Tax", "Alcohol taxes"),
    ("Excise Tax - Spirits", "Alcohol taxes"),
    ("Excise Tax - Beer", "Alcohol taxes"),
    ("Excise Tax - Bear", "Alcohol taxes"),  # sic: typo in LAO's source rows
    ("Excise Tax - Wine", "Alcohol taxes"),
    ("Excise Tax - Tobacco", "Tobacco taxes"),
    ("Excise Tax - ", "Other taxes"),
    ("Retail Sales and Use Tax", "Sales & use tax"),
]
_TAXES = {"Personal income tax", "Corporation tax", "Sales & use tax", "Insurance tax", "Tobacco taxes",
          "Alcohol taxes", "Estate & gift tax", "Motor fuel taxes", "Vehicle fees", "Cannabis taxes",
          "Other taxes"}
_TRANSFER_CATS = {"Transfers & Loans", "Transfers and Loans", "SCO Adjustments"}


def classify(category: str, source: str) -> tuple[str, str]:
    """Return (tax_type, group) for one LAO revenue row."""
    if category in _TRANSFER_CATS:
        return "Transfers, loans & adjustments", "Transfers"
    if source in _TAX_TYPE:
        t = _TAX_TYPE[source]
    else:
        t = next((v for p, v in _PREFIX if source.startswith(p)), None)
    if t is not None:
        return t, "Tax"
    if category.startswith("Investment") or source.startswith("Income from") or source.startswith("Investment"):
        return "Investment income", "Fee / other"
    return "Fees, fines & other revenue", "Fee / other"


# DOF reorganized agencies several times since 1984-85; collapse to a stable set.
_AGENCY = {
    "Business, Consumer Services, and Housing": "Business, housing & commerce",
    "Business And Consumer Services": "Business, housing & commerce",
    "Housing And Homelessness": "Business, housing & commerce",
    "Trade and Commerce Agency": "Business, housing & commerce",
    "Legislative, Judicial, and Executive": "Legislative, judicial & executive",
    "General Government": "General government",
    "Government Operations": "General government",
}


def spending_area(agency: str, debt_service: str) -> str:
    """Stable spending area; GO bond debt service is split out of every agency."""
    if debt_service == "GO Debt Service":
        return "Debt service (GO bonds)"
    return _AGENCY.get(agency, agency)
