"""Schema registry = single source of truth (data dictionary, SQL DDL, validators).

For every field: type, required/optional, allowed values, units, uniqueness, validation rule.
Derived fields carry `derived` (the formula they must reconcile to).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from . import ids

DATE = r"^\d{4}-\d{2}-\d{2}$"
WEEKLBL = r"^20\d{2}W\d{2}$"


@dataclass
class Field:
    name: str
    typ: str  # str | int | float | date
    req: bool = True
    allowed: tuple | None = None
    unit: str = "-"
    uniq: bool = False
    rule: str = ""
    fk: str | None = None
    pat: str | None = None
    mn: float | None = None
    mx: float | None = None
    derived: str = ""
    desc: str = ""


@dataclass
class Table:
    name: str
    kind: str  # core | support | event | derived | label
    desc: str
    pk: list
    fields: list = field(default_factory=list)

    @property
    def cols(self):
        return [f.name for f in self.fields]

    def f(self, name):
        return next(x for x in self.fields if x.name == name)


def S(n, req=True, allowed=None, **k):
    return Field(n, "str", req, tuple(allowed) if allowed else None, **k)


def I(n, req=True, **k):  # noqa: E743
    return Field(n, "int", req, **k)


def F(n, req=True, **k):
    return Field(n, "float", req, **k)


def D(n, req=True, **k):
    return Field(n, "date", req, pat=DATE, **k)


def idf(n, kind, req=True, **k):
    return S(n, req, pat=ids.PATTERNS[kind], **k)


FAM = r"^FAM-\d{2}$"
EFF = [D("effective_from", desc="Effective start (inclusive)"),
       D("effective_to", False, desc="Effective end (exclusive); empty = open-ended")]
ACTORS = ("SUPPLIER", "PLANNER", "CARRIER_WAREHOUSE", "LOGISTICS_ANALYST", "OPS_MANAGER", "SYSTEM")
PO_STATUS = ("PLANNED", "CONFIRMED", "IN_TRANSIT", "DELAYED", "RECEIVED", "CANCELLED")
SH_STATUS = ("DETECTED", "ANALYZED", "NEEDS_REVIEW", "MITIGATION_PROPOSED", "MITIGATION_APPROVED",
             "RESOLVED", "ACCEPTED_BACKORDER")
MIT_STATUS = ("PROPOSED", "APPROVED", "REJECTED", "EXECUTED")
PP_STATUS = ("PLANNED", "FIRMED", "RELEASED", "COMPLETED", "CANCELLED")
OPT_TYPES = ("EXPEDITE_PO", "NEW_PO", "ALT_SUPPLIER_PO", "SUBSTITUTE_SKU", "LOCATION_TRANSFER",
             "PRODUCTION_REPLAN", "PARTIAL_FILL_BACKORDER")
CAUSES = ("INBOUND_LATE_TRANSPORT", "INBOUND_LATE_SUPPLIER", "SUPPLIER_CAPACITY", "INBOUND_CANCELLED",
          "PRODUCTION_CAPACITY", "PRODUCTION_PLAN_CANCELLED", "DEMAND_SPIKE", "PRODUCTION_PLAN_SHORTFALL",
          "INBOUND_QTY_SHORTFALL", "INSUFFICIENT_LEAD_TIME", "NO_INBOUND_PLANNED")
ISSUES = ("INBOUND_DOUBLE_COUNT", "SUBSTITUTE_NOT_APPROVED", "SUPPLIER_CAPACITY_EXCEEDED",
          "SHORTAGE_MISSING_LEAD_TIME", "UOM_MISMATCH")

T: dict[str, Table] = {}


def add(t: Table):
    T[t.name] = t


# ----------------------------------------------------------------------------- master data
add(Table("UnitOfMeasure", "support", "Units of measure.", ["uom_code"], [
    S("uom_code", pat=r"^[A-Z]{2,5}$", uniq=True, desc="UoM code"),
    S("uom_name"), S("uom_class", allowed=("COUNT", "MASS")),
]))
add(Table("Location", "core", "Stocking locations (plants, distribution centres, stores).", ["location_id"], [
    idf("location_id", "location_id", uniq=True, desc="LOC-001"),
    S("location_name"),
    S("location_type", allowed=("PLANT", "DC", "STORE")),
    S("region", allowed=("NORTH", "SOUTH", "EAST", "WEST", "CENTRAL")),
    S("country"),
    S("status", allowed=("ACTIVE", "INACTIVE")),
    *EFF,
]))
add(Table("Carrier", "support", "Transport carriers.", ["carrier_id"], [
    idf("carrier_id", "carrier_id", uniq=True), S("carrier_name"),
    S("mode", allowed=("ROAD", "RAIL", "SEA", "AIR")),
    S("sourcing_region", allowed=("LOCAL", "REGIONAL", "OVERSEAS")),
]))
add(Table("Supplier", "core", "Suppliers.", ["supplier_id"], [
    idf("supplier_id", "supplier_id", uniq=True),
    S("supplier_name"), S("country"),
    S("region", allowed=("LOCAL", "REGIONAL", "OVERSEAS"), desc="Sourcing region"),
    S("tier", allowed=("STRATEGIC", "PREFERRED", "STANDARD")),
    S("status", allowed=("ACTIVE", "ON_HOLD", "INACTIVE")),
    S("currency", allowed=("USD",)),
    I("payment_terms_days", unit="days", mn=0, mx=180),
    D("onboarded_date"),
    *EFF,
]))
add(Table("SKU", "core", "Stock-keeping units.", ["sku_id"], [
    idf("sku_id", "sku_id", uniq=True, desc="SKU-000001"),
    S("sku_name"),
    S("product_family", pat=FAM),
    S("sku_type", allowed=("FINISHED_MAKE", "FINISHED_BUY", "COMPONENT")),
    S("base_uom", fk="UnitOfMeasure.uom_code", allowed=("EA", "KG")),
    F("unit_cost", unit="USD/base UoM", mn=0.01),
    F("unit_price", unit="USD/base UoM", mn=0.01, rule="unit_price >= unit_cost"),
    F("service_level_target", unit="fraction", mn=0.5, mx=0.999, derived="by criticality: A=0.98,B=0.95,C=0.90"),
    S("criticality", allowed=("A", "B", "C"), derived="ABC class from cumulative forecast revenue (80/15/5)"),
    S("lifecycle_status", allowed=("NEW", "ACTIVE", "PHASING_OUT", "DISCONTINUED")),
    *EFF,
]))
add(Table("UoMConversion", "support", "SKU-specific pack conversion to base UoM.", ["conversion_id"], [
    S("conversion_id", uniq=True, pat=r"^UOMC-SKU-\d{6}-[A-Z]+$"),
    S("sku_id", fk="SKU.sku_id"),
    S("from_uom", fk="UnitOfMeasure.uom_code", allowed=("CASE", "BAG")),
    S("to_uom", fk="UnitOfMeasure.uom_code", allowed=("EA", "KG")),
    F("factor", unit="to_uom per from_uom", mn=1, rule="factor >= 1"),
]))
add(Table("SKULocation", "support", "Assortment bridge (N:M SKU<->Location).", ["sku_id", "location_id"], [
    S("sku_id", fk="SKU.sku_id"), S("location_id", fk="Location.location_id"),
    S("stocking_status", allowed=("ACTIVE", "INACTIVE"),
      rule="ACTIVE pairs carry demand for all 52 weeks; INACTIVE pairs carry none"),
    *EFF,
]))
add(Table("SKUSupplier", "support", "Sourcing bridge (N:M SKU<->Supplier).", ["sku_id", "supplier_id"], [
    S("sku_id", fk="SKU.sku_id"), S("supplier_id", fk="Supplier.supplier_id"),
    I("is_preferred", allowed=(0, 1)),
    S("approval_status", allowed=("APPROVED", "BLOCKED")),
    F("unit_price", unit="USD/base UoM", mn=0.01),
    *EFF,
]))
add(Table("SKUSubstitute", "support", "Substitute bridge (N:M SKU<->SKU) with approval workflow.",
          ["sku_id", "substitute_sku_id", "effective_from"], [
    S("sku_id", fk="SKU.sku_id"), S("substitute_sku_id", fk="SKU.sku_id", rule="!= sku_id"),
    F("substitution_ratio", unit="substitute units per original unit", mn=0.5, mx=3),
    S("approval_status", allowed=("APPROVED", "PENDING", "REJECTED", "EXPIRED")),
    S("approved_by_role", False, allowed=ACTORS, rule="required when APPROVED"),
    D("approved_date", False, rule="required when APPROVED; <= as_of_date"),
    F("cost_penalty_pct", unit="%", mn=0, mx=100),
    D("effective_from"), D("effective_to", False),
]))
add(Table("BillOfMaterial", "support", "BOM header for FINISHED_MAKE SKUs.", ["bom_id"], [
    idf("bom_id", "bom_id", uniq=True), S("parent_sku_id", fk="SKU.sku_id"),
    I("bom_version", mn=1), F("run_time_hours_per_unit", unit="hours/unit", mn=0.0001),
    I("lot_size", unit="units", mn=1), *EFF,
]))
add(Table("BOMLine", "support", "BOM bridge (N:M parent<->component).", ["bom_id", "component_sku_id"], [
    S("bom_id", fk="BillOfMaterial.bom_id"), S("component_sku_id", fk="SKU.sku_id"),
    I("qty_per", unit="component base UoM per parent unit", mn=1),
    F("scrap_pct", unit="fraction", mn=0, mx=0.5),
]))
add(Table("WorkCenter", "support", "Production work centres (plants only).", ["work_center_id"], [
    idf("work_center_id", "work_center_id", uniq=True), S("location_id", fk="Location.location_id"),
    S("work_center_name"), S("status", allowed=("ACTIVE", "INACTIVE")),
]))
add(Table("ProductionCapacity", "support", "Weekly available hours per work centre.", ["prod_capacity_id"], [
    idf("prod_capacity_id", "prod_capacity_id", uniq=True),
    S("work_center_id", fk="WorkCenter.work_center_id"),
    S("iso_week", pat=WEEKLBL), D("week_start_date"),
    F("available_hours", unit="hours/week", mn=0),
]))

# ----------------------------------------------------------------------------- 11 core entities (rest)
add(Table("ForecastDemand", "core", "Weekly forecast demand per SKU-location.", ["demand_id"], [
    idf("demand_id", "demand_id", uniq=True, derived="'DEM-'+sku_id+'-'+location_id+'-'+iso_week"),
    S("sku_id", fk="SKU.sku_id"), S("location_id", fk="Location.location_id"),
    S("iso_week", pat=WEEKLBL), D("week_start_date"),
    I("forecast_qty", unit="base UoM", mn=0),
    S("demand_driver", allowed=("BASELINE", "SEASONAL", "PROMO", "SPIKE"),
      derived="SPIKE if unplanned uplift, else PROMO if promo window, else SEASONAL if seasonal factor>=1.2, else BASELINE"),
    F("forecast_stdev", unit="base UoM", mn=0),
]))
add(Table("Inventory", "core", "On-hand inventory snapshot at as_of_date (inbound = open POs/production).",
          ["inventory_id"], [
    idf("inventory_id", "inventory_id", uniq=True),
    S("sku_id", fk="SKU.sku_id"), S("location_id", fk="Location.location_id"),
    D("as_of_date"),
    I("on_hand_qty", unit="base UoM", mn=0), I("allocated_qty", unit="base UoM", mn=0),
    I("quality_hold_qty", unit="base UoM", mn=0), I("safety_stock_qty", unit="base UoM", mn=0),
    I("available_qty", unit="base UoM", derived="on_hand_qty - allocated_qty - quality_hold_qty"),
    S("inventory_status", allowed=("AVAILABLE", "QUALITY_HOLD")),
]))
add(Table("SupplierCapacity", "core", "Effective-dated supplier weekly capacity, MOQ and order multiple. "
          "If windows overlap the row with the latest effective_from wins.", ["capacity_id"], [
    idf("capacity_id", "capacity_id", uniq=True), S("supplier_id", fk="Supplier.supplier_id"),
    S("product_family", pat=FAM),
    I("weekly_capacity_qty", unit="base UoM/week", mn=1),
    I("min_order_qty", unit="base UoM", mn=1), I("order_multiple", unit="base UoM", mn=1),
    S("capacity_uom", allowed=("EA", "KG", "MIXED"), rule="capacity expressed in each SKU's base UoM"),
    S("status", allowed=("ACTIVE", "INACTIVE")),
    D("effective_from"), D("effective_to", False),
]))
add(Table("LeadTime", "core", "Effective-dated lead time per supplier-SKU (optional ship-to override).",
          ["lead_time_id"], [
    idf("lead_time_id", "lead_time_id", uniq=True),
    S("supplier_id", fk="Supplier.supplier_id"), S("sku_id", fk="SKU.sku_id"),
    S("ship_to_location_id", False, fk="Location.location_id", rule="empty = default for all locations"),
    I("production_days", unit="days", mn=0), I("transit_days", unit="days", mn=0),
    I("total_lead_days", unit="days", mn=0, derived="production_days + transit_days"),
    I("p90_lead_days", unit="days", mn=0, rule=">= total_lead_days"),
    S("transport_mode", allowed=("ROAD", "RAIL", "SEA", "AIR")),
    D("effective_from"), D("effective_to", False),
]))
add(Table("PurchaseOrder", "core", "Inbound purchase orders (single-line; 1 SKU per PO).", ["po_id"], [
    idf("po_id", "po_id", uniq=True),
    S("supplier_id", fk="Supplier.supplier_id"), S("sku_id", fk="SKU.sku_id"),
    S("ship_to_location_id", fk="Location.location_id"),
    S("carrier_id", False, fk="Carrier.carrier_id", rule="assigned once shipped"),
    D("created_date", rule="<= as_of_date and <= order_date"),
    D("order_date"), D("requested_date", rule=">= order_date"),
    D("promised_date", rule=">= requested_date"),
    D("eta_date", derived="promised_date + sum(delay_days of DELAYED events)"),
    D("actual_receipt_date", False, derived="eta_date when status=RECEIVED"),
    I("order_qty", unit="order_uom", mn=1), S("order_uom", fk="UnitOfMeasure.uom_code"),
    I("qty_base", unit="base UoM", derived="order_qty * conversion factor(sku, order_uom)"),
    F("unit_price", unit="USD/base UoM", mn=0.01),
    F("total_cost", unit="USD", derived="round(qty_base * unit_price, 2)"),
    S("supplier_ref_no", rule="supplier document number; the same number on two POs for the same "
                              "supplier/SKU/ship-to/promised date means the inbound is double counted"),
    S("status", allowed=PO_STATUS, derived="to_status of the latest PurchaseOrderEvent"),
]))
add(Table("ProductionPlan", "core", "Weekly requested production quantity per make-SKU/plant.",
          ["production_plan_id"], [
    idf("production_plan_id", "production_plan_id", uniq=True),
    S("sku_id", fk="SKU.sku_id"), S("location_id", fk="Location.location_id"),
    S("work_center_id", fk="WorkCenter.work_center_id"), S("bom_id", fk="BillOfMaterial.bom_id"),
    S("iso_week", pat=WEEKLBL), D("week_start_date"),
    I("planned_qty", unit="base UoM", mn=1, rule="multiple of BOM lot_size"),
    F("required_hours", unit="hours", derived="planned_qty * BillOfMaterial.run_time_hours_per_unit"),
    S("status", allowed=PP_STATUS, derived="to_status of the latest ProductionPlanEvent"),
]))
add(Table("Shortage", "core", "Projected shortage episodes (output of the planning engine).",
          ["shortage_id"], [
    idf("shortage_id", "shortage_id", uniq=True),
    S("run_id", fk="PlanRun.run_id"),
    S("sku_id", fk="SKU.sku_id"), S("location_id", fk="Location.location_id"),
    S("first_short_week", pat=WEEKLBL), S("last_short_week", pat=WEEKLBL), S("peak_short_week", pat=WEEKLBL),
    D("need_by_date", derived="Monday of first_short_week"),
    I("episode_weeks", mn=1),
    S("shortage_type", allowed=("STOCKOUT", "SAFETY_STOCK_BREACH")),
    I("shortage_qty", unit="base UoM", mn=1, derived="max over episode of (safety_stock - projected_balance)"),
    F("value_at_risk", unit="USD", derived="shortage_qty * unit_price"),
    F("priority_score", unit="0-100"), I("priority_rank", mn=1),
    S("primary_cause_code", allowed=CAUSES, derived="cause with the largest contribution"),
    S("data_quality_flag", allowed=("NONE",) + ISSUES[0:1] + ISSUES[2:5]),
    S("status", allowed=SH_STATUS, derived="to_status of latest ShortageEvent"),
]))
add(Table("MitigationOption", "core", "Candidate mitigations with cost/service trade-offs.",
          ["mitigation_id"], [
    idf("mitigation_id", "mitigation_id", uniq=True, derived="'MIT-'+shortage_id+'-'+NN"),
    S("shortage_id", fk="Shortage.shortage_id"),
    S("option_type", allowed=OPT_TYPES),
    S("supplier_id", False, fk="Supplier.supplier_id"),
    S("alt_sku_id", False, fk="SKU.sku_id"),
    S("source_location_id", False, fk="Location.location_id"),
    S("ref_po_id", False, fk="PurchaseOrder.po_id"),
    S("production_plan_id", False, fk="ProductionPlan.production_plan_id"),
    I("qty", unit="base UoM of the option's SKU", mn=0, rule="after MOQ / multiple / lot rounding"),
    I("covered_qty", unit="shortage-SKU base UoM", mn=0),
    F("unit_cost", unit="USD/base UoM", mn=0),
    F("expedite_premium", unit="USD", mn=0), F("freight_cost", unit="USD", mn=0),
    F("excess_cost", unit="USD", mn=0), F("penalty_cost", unit="USD", mn=0),
    F("total_cost", unit="USD", derived="expedite_premium+freight_cost+excess_cost+penalty_cost (incremental cost)"),
    F("cost_delta_vs_baseline", unit="USD", derived="total_cost - backorder option total_cost"),
    I("lead_days", False, unit="days", mn=0),
    D("earliest_arrival_date", False), I("weeks_late", False, mn=0),
    F("fill_rate_pct", unit="%", mn=0, mx=100, derived="100*covered/shortage_qty*(1-min(1,weeks_late/episode_weeks))"),
    I("capacity_available_qty", False, unit="base UoM", mn=0),
    S("capacity_check", allowed=("PASS", "FAIL", "NA")),
    S("policy_check", allowed=("PASS", "FAIL")),
    S("policy_reason", False),
    S("lead_time_check", allowed=("OK", "LATE", "MISSING", "NA")),
    S("approval_required_role", allowed=("PLANNER", "OPS_MANAGER")),
    I("is_recommendable", allowed=(0, 1)), I("rank", mn=1), I("is_recommended", allowed=(0, 1)),
    S("status", allowed=MIT_STATUS, derived="to_status of latest MitigationEvent"),
]))

# ----------------------------------------------------------------------------- event tables (append-only)
add(Table("PurchaseOrderEvent", "event", "Append-only PO state changes.", ["event_id"], [
    S("event_id", uniq=True, pat=r"^POE-\d{6}$"), S("po_id", fk="PurchaseOrder.po_id"),
    S("event_type", allowed=("CREATED", "CONFIRMED", "SHIPPED", "DELAYED", "RECEIVED", "CANCELLED")),
    S("from_status", False, allowed=PO_STATUS), S("to_status", allowed=PO_STATUS),
    D("event_date", rule="<= as_of_date"), S("actor_role", allowed=ACTORS),
    I("delay_days", False, unit="days", mn=1, rule="DELAYED only"), S("reason_code", False),
]))
add(Table("TransportEvent", "event", "Carrier tracking events.", ["event_id"], [
    S("event_id", uniq=True, pat=r"^TRE-\d{6}$"), S("po_id", fk="PurchaseOrder.po_id"),
    S("carrier_id", fk="Carrier.carrier_id"),
    S("event_type", allowed=("DEPARTED", "DELAYED", "ARRIVED")),
    D("event_date", rule="<= as_of_date"), I("delay_days", False, unit="days", mn=1),
    S("reason_code", False, allowed=("WEATHER", "PORT_CONGESTION", "CUSTOMS", "BREAKDOWN", "DOCUMENTATION")),
    S("actor_role", allowed=ACTORS),
]))
add(Table("InventoryEvent", "event", "Inventory receipts/issues/adjustments.", ["event_id"], [
    S("event_id", uniq=True, pat=r"^INE-\d{6}$"), S("sku_id", fk="SKU.sku_id"),
    S("location_id", fk="Location.location_id"),
    S("event_type", allowed=("RECEIPT", "ISSUE", "ADJUSTMENT")), I("qty", unit="base UoM"),
    D("event_date", rule="<= as_of_date"), S("po_id", False, fk="PurchaseOrder.po_id"),
    S("actor_role", allowed=ACTORS),
]))
add(Table("ProductionPlanEvent", "event", "Append-only production plan state changes.", ["event_id"], [
    S("event_id", uniq=True, pat=r"^PPE-\d{6}$"),
    S("production_plan_id", fk="ProductionPlan.production_plan_id"),
    S("from_status", False, allowed=PP_STATUS), S("to_status", allowed=PP_STATUS),
    D("event_date", rule="<= as_of_date"), S("actor_role", allowed=ACTORS),
]))
add(Table("ShortageEvent", "event", "Append-only shortage lifecycle.", ["event_id"], [
    S("event_id", uniq=True, pat=r"^SHE-\d{6}$"), S("shortage_id", fk="Shortage.shortage_id"),
    S("from_status", False, allowed=SH_STATUS), S("to_status", allowed=SH_STATUS),
    D("event_date"), S("actor_role", allowed=ACTORS), S("comment", False),
]))
add(Table("MitigationEvent", "event", "Append-only mitigation lifecycle.", ["event_id"], [
    S("event_id", uniq=True, pat=r"^MIE-\d{6}$"), S("mitigation_id", fk="MitigationOption.mitigation_id"),
    S("from_status", False, allowed=MIT_STATUS), S("to_status", allowed=MIT_STATUS),
    D("event_date"), S("actor_role", allowed=ACTORS), S("comment", False),
]))

# ----------------------------------------------------------------------------- planning outputs (derived)
add(Table("PlanRun", "derived", "One planning run.", ["run_id"], [
    idf("run_id", "run_id", uniq=True), D("as_of_date"), I("seed"), S("profile"),
    S("engine_version"), S("policy_hash"), I("n_pairs", mn=0), I("n_shortages", mn=0),
]))
add(Table("ProjectedBalance", "derived", "Week-by-week projected available balance (PAB).",
          ["run_id", "sku_id", "location_id", "iso_week"], [
    S("run_id", fk="PlanRun.run_id"), S("sku_id", fk="SKU.sku_id"), S("location_id", fk="Location.location_id"),
    S("iso_week", pat=WEEKLBL), D("week_start_date"),
    I("opening_qty", derived="previous closing_qty; week 1 = Inventory.available_qty"),
    I("gross_demand_qty", mn=0, derived="ForecastDemand.forecast_qty"),
    I("dependent_demand_qty", mn=0, derived="BOM explosion of capacity-limited production"),
    I("scheduled_receipts_qty", mn=0, derived="sum qty_base of open, non-duplicate POs by ETA week"),
    I("production_receipts_qty", mn=0, derived="capacity-limited planned production"),
    I("closing_qty", derived="opening + receipts + production - gross - dependent"),
    I("safety_stock_qty", mn=0), I("shortfall_qty", mn=0, derived="max(0, safety_stock - closing)"),
]))
add(Table("SupplierCapacityLedger", "derived", "Committed vs. available supplier capacity by order week.",
          ["run_id", "supplier_id", "product_family", "week_start_date"], [
    S("run_id", fk="PlanRun.run_id"), S("supplier_id", fk="Supplier.supplier_id"),
    S("product_family", pat=FAM), D("week_start_date"), S("iso_week"),
    I("committed_qty", mn=0), I("capacity_qty", mn=0),
    F("utilisation_pct", mn=0, derived="100*committed/capacity"),
    I("remaining_qty", mn=0, derived="max(0, capacity-committed)"),
    S("status", allowed=("OK", "EXCEEDED")),
]))
add(Table("ShortageCause", "derived", "Evidence bridge: shortage <-> source records (N:M).",
          ["shortage_id", "cause_seq"], [
    S("shortage_id", fk="Shortage.shortage_id"), I("cause_seq", mn=1),
    S("cause_code", allowed=CAUSES), I("contribution_qty", mn=1),
    S("source_table"), S("source_id"), S("explanation"),
]))
add(Table("DataQualityFinding", "derived", "Exceptions raised by the planning engine data-quality gate.",
          ["finding_id"], [
    S("finding_id", uniq=True, pat=r"^DQF-\d{6}$"), S("run_id", fk="PlanRun.run_id"),
    S("issue_type", allowed=ISSUES + ("UOM_FACTOR_MISSING",)), S("entity"), S("record_id"),
    S("related_record_ids", False), I("impact_qty", False), S("detail"),
]))

# ----------------------------------------------------------------------------- ground truth (separate file)
GROUND_TRUTH_COLS = ["label_id", "label_class", "issue_type", "entity", "record_id", "related_record_ids",
                     "injected_field", "original_value", "injected_value", "expected_detection",
                     "expected_decision", "impact_qty", "rule_ref", "seed"]

CORE = ["SKU", "Location", "ForecastDemand", "Inventory", "Supplier", "SupplierCapacity", "LeadTime",
        "PurchaseOrder", "ProductionPlan", "Shortage", "MitigationOption"]
INPUT_TABLES = [n for n, t in T.items() if t.kind in ("core", "support", "event")
                and n not in ("Shortage", "MitigationOption", "ShortageEvent", "MitigationEvent")]
OUTPUT_TABLES = ["PlanRun", "ProjectedBalance", "SupplierCapacityLedger", "Shortage", "ShortageCause",
                 "MitigationOption", "ShortageEvent", "MitigationEvent", "DataQualityFinding"]
ALL_TABLES = INPUT_TABLES + OUTPUT_TABLES

SQL_TYPE = {"str": "TEXT", "int": "INTEGER", "float": "REAL", "date": "TEXT"}


def ddl() -> str:
    out = []
    for name in ALL_TABLES:
        t = T[name]
        lines = []
        for f in t.fields:
            lines.append(f'  "{f.name}" {SQL_TYPE[f.typ]}{" NOT NULL" if f.req else ""}')
        lines.append(f'  PRIMARY KEY ({", ".join(chr(34)+c+chr(34) for c in t.pk)})')
        for f in t.fields:
            if f.fk:
                pt, pc = f.fk.split(".")
                lines.append(f'  FOREIGN KEY ("{f.name}") REFERENCES "{pt}"("{pc}")')
        out.append(f'CREATE TABLE "{name}" (\n' + ",\n".join(lines) + "\n);")
    return "\n\n".join(out) + "\n"


def rule_text(f: Field) -> str:
    parts = [{"str": "text", "int": "integer", "float": "decimal", "date": "ISO date YYYY-MM-DD"}[f.typ]]
    parts.append("not null" if f.req else "may be empty")
    if f.allowed:
        parts.append("in {" + ", ".join(str(a) for a in f.allowed) + "}")
    if f.pat:
        parts.append(f"matches {f.pat}")
    if f.mn is not None:
        parts.append(f">= {f.mn:g}")
    if f.mx is not None:
        parts.append(f"<= {f.mx:g}")
    if f.fk:
        parts.append(f"FK -> {f.fk}")
    if f.rule:
        parts.append(f.rule)
    if f.derived:
        parts.append(f"derived: {f.derived}")
    return "; ".join(parts)


def dictionary_rows() -> list[dict]:
    rows = []
    for name in ALL_TABLES:
        t = T[name]
        for f in t.fields:
            pk = f.name in t.pk
            uniq = "PK (unique)" if (pk and len(t.pk) == 1) else ("PK part (composite unique)" if pk else
                                                                    ("unique" if f.uniq else "-"))
            rows.append({
                "table": name, "table_kind": t.kind, "field": f.name, "type": f.typ,
                "required": "required" if f.req else "optional",
                "allowed_values": ", ".join(str(a) for a in f.allowed) if f.allowed else (f"regex {f.pat}" if f.pat else "free"),
                "unit": f.unit, "uniqueness": uniq, "validation_rule": rule_text(f),
            })
    return rows
