"""Deterministic, zero-padded, immutable ID builders and their regexes (PDF section 4).

Mandatory patterns:  SKU-000001 | DEM-<sku>-<location>-2026W01 | PO-2026-000001 |
SHORT-2026-000001 | MIT-<shortage-id>-01.   Other IDs follow the same rules (decision D4/D5).
"""
from __future__ import annotations

import re

SKU_RE = r"SKU-\d{6}"
LOC_RE = r"LOC-\d{3}"
SUP_RE = r"SUP-\d{4}"
WEEK_RE = r"2026W\d{2}"
PO_RE = r"PO-2026-\d{6}"
SHORT_RE = r"SHORT-2026-\d{6}"

PATTERNS = {
    "sku_id": rf"^{SKU_RE}$",
    "location_id": rf"^{LOC_RE}$",
    "supplier_id": rf"^{SUP_RE}$",
    "demand_id": rf"^DEM-{SKU_RE}-{LOC_RE}-{WEEK_RE}$",
    "po_id": rf"^{PO_RE}$",
    "shortage_id": rf"^{SHORT_RE}$",
    "mitigation_id": rf"^MIT-{SHORT_RE}-\d{{2}}$",
    "inventory_id": rf"^INV-{SKU_RE}-{LOC_RE}$",
    "capacity_id": r"^SCAP-\d{6}$",
    "lead_time_id": r"^LT-\d{6}$",
    "production_plan_id": r"^PP-2026-\d{6}$",
    "bom_id": r"^BOM-\d{6}$",
    "work_center_id": rf"^WC-{LOC_RE}-\d{{2}}$",
    "prod_capacity_id": r"^PCAP-\d{6}$",
    "carrier_id": r"^CAR-\d{2}$",
    "run_id": r"^RUN-\d{4}$",
}


def sku(n: int) -> str:
    return f"SKU-{n:06d}"


def loc(n: int) -> str:
    return f"LOC-{n:03d}"


def sup(n: int) -> str:
    return f"SUP-{n:04d}"


def dem(sku_id: str, loc_id: str, week_label: str) -> str:
    return f"DEM-{sku_id}-{loc_id}-{week_label}"


def po(n: int) -> str:
    return f"PO-2026-{n:06d}"


def short(n: int) -> str:
    return f"SHORT-2026-{n:06d}"


def mit(shortage_id: str, n: int) -> str:
    return f"MIT-{shortage_id}-{n:02d}"


def inv(sku_id: str, loc_id: str) -> str:
    return f"INV-{sku_id}-{loc_id}"


def counter(prefix: str, n: int, width: int = 6) -> str:
    return f"{prefix}-{n:0{width}d}"


def matches(kind: str, value: str) -> bool:
    return re.match(PATTERNS[kind], value) is not None
