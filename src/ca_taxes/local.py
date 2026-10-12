"""Classifiers that give State Controller local-government data a stable scheme.

SCO reporting formats changed in FY2016-17 (categories were merged, enterprise
funds got their own categories), so raw categories are not comparable across the
break. These keyword rules map each era onto one set of groups; build_processed.py
prints the share left in 'Other' so a drift in SCO's labels shows up.
"""
from __future__ import annotations

import re

# ---- revenue by source -------------------------------------------------------------

_INTERGOV = re.compile(r"intergovernmental|aid from other|other governmental agencies|in-lieu taxes|^federal$|^state$", re.I)


def revenue_group(category: str) -> str:
    c = category.strip()
    if _INTERGOV.search(c):
        return "Intergovernmental (state & federal aid)"
    if re.search(r"\btax", c, re.I) or c.lower().startswith("taxes"):
        return "Taxes"
    if re.search(r"charges for|current service", c, re.I):
        return "Charges for services"
    if re.search(r"enterprise|hospital|utilit|transit|self insurance", c, re.I):
        return "Enterprise & utility operations"
    if re.search(r"internal service", c, re.I):
        return "Internal service funds"
    if re.search(r"governmental funds|transportation", c, re.I):
        return "Other"  # special districts post-FY2017 report by fund type, not source
    return "Fees, fines, assessments & other"


# ---- tax type from line_description (cities, counties) -----------------------------

def tax_type(line: str) -> str:
    s = line.lower()
    if "in-lieu of vehicle" in s or "in lieu of vechicle" in s or "in lieu of vehicle" in s:
        return "Property tax in lieu of VLF"
    if "transfer" in s:
        return "Other taxes"  # real property transfer tax
    if re.search(r"property|secured|countywide|county wide|less.then county|supplemental|voter.approved|abx1|parcel", s):
        return "Property tax"
    if "sales" in s:
        return "Sales & use tax"
    if re.search(r"transient|lodging|occupancy", s):
        return "Hotel (transient occupancy) tax"
    if "utility users" in s:
        return "Utility users tax"
    if "business license" in s:
        return "Business license tax"
    if "franchise" in s:
        return "Franchise fees"
    return "Other taxes"


def is_tax_category(category: str) -> bool:
    """Tax rows only: SCO's tax-ish categories also include 'in-lieu' intergovernmental lines."""
    return revenue_group(category) == "Taxes"


# ---- spending by function ----------------------------------------------------------

def _spending_rule(text: str) -> str | None:
    text = text.lower()
    if re.search(r"enterprise|activity/enterprise|conduit", text):
        return "Enterprise & utility operations"
    if "internal service" in text:
        return "Internal service funds"
    if re.search(r"debt service|capital outlay", text):
        return "Debt service & capital outlay"
    if re.search(r"police|fire|public safety|public protection|detention|sheriff|district attorney|"
                 r"probation|animal|coroner|court|disaster|corrections|protective|judicial|"
                 r"flood control|inspection|construction and engineering", text):
        return "Public safety"
    if re.search(r"public assistance|welfare|aid programs|general relief|veterans|social", text):
        return "Public assistance & social services"
    if re.search(r"hospital|health|sanitation|medical|mental|cemeter|ambulance", text):
        return "Health & sanitation"
    if re.search(r"road|street|highway|transportation|public ways|airport|parking|transit|waterways", text):
        return "Transportation & public works"
    if re.search(r"community development|planning|housing|redevelopment|economic|"
                 r"community promotion|conservation|agricultur", text):
        return "Community development & housing"
    if re.search(r"culture|leisure|recreation|library|education|parks|community centers|museum", text):
        return "Parks, recreation & libraries"
    if re.search(r"general government|general$|legislative|administration|assessor|auditor|elections|"
                 r"counsel|treasurer|clerk|personnel|finance|property management|plant acquisition|"
                 r"communications|other general|retirement|insurance|city (manager|attorney)", text):
        return "General government"
    if re.search(r"public utilities|utility|electric|gas|water|sewer|refuse|solid waste", text):
        return "Enterprise & utility operations"
    return None


def spending_group(kind: str, category: str, sub1: str) -> str:
    """Stable groups for both reporting eras. subcategory_1 is the finest consistent label;
    the category is only a fallback because post-FY2017 categories are merged (e.g.
    'General Government and Public Safety')."""
    return _spending_rule(sub1.replace("_Current Expenditures", "")) or _spending_rule(category) or "Other"
