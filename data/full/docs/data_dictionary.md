# Data dictionary

Generated from `src/oryva/schema.py` (single source of truth). Every field lists type, required/optional, allowed values, unit, uniqueness and validation rule.

## UnitOfMeasure  _(support)_

Units of measure.

**Primary key:** `uom_code`

| Field | Type | Req. | Allowed values | Unit | Uniqueness | Validation rule |
|---|---|---|---|---|---|---|
| `uom_code` | str | required | regex ^[A-Z]{2,5}$ | - | PK (unique) | text; not null; matches ^[A-Z]{2,5}$ |
| `uom_name` | str | required | free | - | - | text; not null |
| `uom_class` | str | required | COUNT, MASS | - | - | text; not null; in {COUNT, MASS} |

## Location  _(core)_

Stocking locations (plants, distribution centres, stores).

**Primary key:** `location_id`

| Field | Type | Req. | Allowed values | Unit | Uniqueness | Validation rule |
|---|---|---|---|---|---|---|
| `location_id` | str | required | regex ^LOC-\d{3}$ | - | PK (unique) | text; not null; matches ^LOC-\d{3}$ |
| `location_name` | str | required | free | - | - | text; not null |
| `location_type` | str | required | PLANT, DC, STORE | - | - | text; not null; in {PLANT, DC, STORE} |
| `region` | str | required | NORTH, SOUTH, EAST, WEST, CENTRAL | - | - | text; not null; in {NORTH, SOUTH, EAST, WEST, CENTRAL} |
| `country` | str | required | free | - | - | text; not null |
| `status` | str | required | ACTIVE, INACTIVE | - | - | text; not null; in {ACTIVE, INACTIVE} |
| `effective_from` | date | required | regex ^\d{4}-\d{2}-\d{2}$ | - | - | ISO date YYYY-MM-DD; not null; matches ^\d{4}-\d{2}-\d{2}$ |
| `effective_to` | date | optional | regex ^\d{4}-\d{2}-\d{2}$ | - | - | ISO date YYYY-MM-DD; may be empty; matches ^\d{4}-\d{2}-\d{2}$ |

## Carrier  _(support)_

Transport carriers.

**Primary key:** `carrier_id`

| Field | Type | Req. | Allowed values | Unit | Uniqueness | Validation rule |
|---|---|---|---|---|---|---|
| `carrier_id` | str | required | regex ^CAR-\d{2}$ | - | PK (unique) | text; not null; matches ^CAR-\d{2}$ |
| `carrier_name` | str | required | free | - | - | text; not null |
| `mode` | str | required | ROAD, RAIL, SEA, AIR | - | - | text; not null; in {ROAD, RAIL, SEA, AIR} |
| `sourcing_region` | str | required | LOCAL, REGIONAL, OVERSEAS | - | - | text; not null; in {LOCAL, REGIONAL, OVERSEAS} |

## Supplier  _(core)_

Suppliers.

**Primary key:** `supplier_id`

| Field | Type | Req. | Allowed values | Unit | Uniqueness | Validation rule |
|---|---|---|---|---|---|---|
| `supplier_id` | str | required | regex ^SUP-\d{4}$ | - | PK (unique) | text; not null; matches ^SUP-\d{4}$ |
| `supplier_name` | str | required | free | - | - | text; not null |
| `country` | str | required | free | - | - | text; not null |
| `region` | str | required | LOCAL, REGIONAL, OVERSEAS | - | - | text; not null; in {LOCAL, REGIONAL, OVERSEAS} |
| `tier` | str | required | STRATEGIC, PREFERRED, STANDARD | - | - | text; not null; in {STRATEGIC, PREFERRED, STANDARD} |
| `status` | str | required | ACTIVE, ON_HOLD, INACTIVE | - | - | text; not null; in {ACTIVE, ON_HOLD, INACTIVE} |
| `currency` | str | required | USD | - | - | text; not null; in {USD} |
| `payment_terms_days` | int | required | free | days | - | integer; not null; >= 0; <= 180 |
| `onboarded_date` | date | required | regex ^\d{4}-\d{2}-\d{2}$ | - | - | ISO date YYYY-MM-DD; not null; matches ^\d{4}-\d{2}-\d{2}$ |
| `effective_from` | date | required | regex ^\d{4}-\d{2}-\d{2}$ | - | - | ISO date YYYY-MM-DD; not null; matches ^\d{4}-\d{2}-\d{2}$ |
| `effective_to` | date | optional | regex ^\d{4}-\d{2}-\d{2}$ | - | - | ISO date YYYY-MM-DD; may be empty; matches ^\d{4}-\d{2}-\d{2}$ |

## SKU  _(core)_

Stock-keeping units.

**Primary key:** `sku_id`

| Field | Type | Req. | Allowed values | Unit | Uniqueness | Validation rule |
|---|---|---|---|---|---|---|
| `sku_id` | str | required | regex ^SKU-\d{6}$ | - | PK (unique) | text; not null; matches ^SKU-\d{6}$ |
| `sku_name` | str | required | free | - | - | text; not null |
| `product_family` | str | required | regex ^FAM-\d{2}$ | - | - | text; not null; matches ^FAM-\d{2}$ |
| `sku_type` | str | required | FINISHED_MAKE, FINISHED_BUY, COMPONENT | - | - | text; not null; in {FINISHED_MAKE, FINISHED_BUY, COMPONENT} |
| `base_uom` | str | required | EA, KG | - | - | text; not null; in {EA, KG}; FK -> UnitOfMeasure.uom_code |
| `unit_cost` | float | required | free | USD/base UoM | - | decimal; not null; >= 0.01 |
| `unit_price` | float | required | free | USD/base UoM | - | decimal; not null; >= 0.01; unit_price >= unit_cost |
| `service_level_target` | float | required | free | fraction | - | decimal; not null; >= 0.5; <= 0.999; derived: by criticality: A=0.98,B=0.95,C=0.90 |
| `criticality` | str | required | A, B, C | - | - | text; not null; in {A, B, C}; derived: ABC class from cumulative forecast revenue (80/15/5) |
| `lifecycle_status` | str | required | NEW, ACTIVE, PHASING_OUT, DISCONTINUED | - | - | text; not null; in {NEW, ACTIVE, PHASING_OUT, DISCONTINUED} |
| `effective_from` | date | required | regex ^\d{4}-\d{2}-\d{2}$ | - | - | ISO date YYYY-MM-DD; not null; matches ^\d{4}-\d{2}-\d{2}$ |
| `effective_to` | date | optional | regex ^\d{4}-\d{2}-\d{2}$ | - | - | ISO date YYYY-MM-DD; may be empty; matches ^\d{4}-\d{2}-\d{2}$ |

## UoMConversion  _(support)_

SKU-specific pack conversion to base UoM.

**Primary key:** `conversion_id`

| Field | Type | Req. | Allowed values | Unit | Uniqueness | Validation rule |
|---|---|---|---|---|---|---|
| `conversion_id` | str | required | regex ^UOMC-SKU-\d{6}-[A-Z]+$ | - | PK (unique) | text; not null; matches ^UOMC-SKU-\d{6}-[A-Z]+$ |
| `sku_id` | str | required | free | - | - | text; not null; FK -> SKU.sku_id |
| `from_uom` | str | required | CASE, BAG | - | - | text; not null; in {CASE, BAG}; FK -> UnitOfMeasure.uom_code |
| `to_uom` | str | required | EA, KG | - | - | text; not null; in {EA, KG}; FK -> UnitOfMeasure.uom_code |
| `factor` | float | required | free | to_uom per from_uom | - | decimal; not null; >= 1; factor >= 1 |

## SKULocation  _(support)_

Assortment bridge (N:M SKU<->Location).

**Primary key:** `sku_id, location_id`

| Field | Type | Req. | Allowed values | Unit | Uniqueness | Validation rule |
|---|---|---|---|---|---|---|
| `sku_id` | str | required | free | - | PK part (composite unique) | text; not null; FK -> SKU.sku_id |
| `location_id` | str | required | free | - | PK part (composite unique) | text; not null; FK -> Location.location_id |
| `stocking_status` | str | required | ACTIVE, INACTIVE | - | - | text; not null; in {ACTIVE, INACTIVE}; ACTIVE pairs carry demand for all 52 weeks; INACTIVE pairs carry none |
| `effective_from` | date | required | regex ^\d{4}-\d{2}-\d{2}$ | - | - | ISO date YYYY-MM-DD; not null; matches ^\d{4}-\d{2}-\d{2}$ |
| `effective_to` | date | optional | regex ^\d{4}-\d{2}-\d{2}$ | - | - | ISO date YYYY-MM-DD; may be empty; matches ^\d{4}-\d{2}-\d{2}$ |

## SKUSupplier  _(support)_

Sourcing bridge (N:M SKU<->Supplier).

**Primary key:** `sku_id, supplier_id`

| Field | Type | Req. | Allowed values | Unit | Uniqueness | Validation rule |
|---|---|---|---|---|---|---|
| `sku_id` | str | required | free | - | PK part (composite unique) | text; not null; FK -> SKU.sku_id |
| `supplier_id` | str | required | free | - | PK part (composite unique) | text; not null; FK -> Supplier.supplier_id |
| `is_preferred` | int | required | 0, 1 | - | - | integer; not null; in {0, 1} |
| `approval_status` | str | required | APPROVED, BLOCKED | - | - | text; not null; in {APPROVED, BLOCKED} |
| `unit_price` | float | required | free | USD/base UoM | - | decimal; not null; >= 0.01 |
| `effective_from` | date | required | regex ^\d{4}-\d{2}-\d{2}$ | - | - | ISO date YYYY-MM-DD; not null; matches ^\d{4}-\d{2}-\d{2}$ |
| `effective_to` | date | optional | regex ^\d{4}-\d{2}-\d{2}$ | - | - | ISO date YYYY-MM-DD; may be empty; matches ^\d{4}-\d{2}-\d{2}$ |

## SKUSubstitute  _(support)_

Substitute bridge (N:M SKU<->SKU) with approval workflow.

**Primary key:** `sku_id, substitute_sku_id, effective_from`

| Field | Type | Req. | Allowed values | Unit | Uniqueness | Validation rule |
|---|---|---|---|---|---|---|
| `sku_id` | str | required | free | - | PK part (composite unique) | text; not null; FK -> SKU.sku_id |
| `substitute_sku_id` | str | required | free | - | PK part (composite unique) | text; not null; FK -> SKU.sku_id; != sku_id |
| `substitution_ratio` | float | required | free | substitute units per original unit | - | decimal; not null; >= 0.5; <= 3 |
| `approval_status` | str | required | APPROVED, PENDING, REJECTED, EXPIRED | - | - | text; not null; in {APPROVED, PENDING, REJECTED, EXPIRED} |
| `approved_by_role` | str | optional | SUPPLIER, PLANNER, CARRIER_WAREHOUSE, LOGISTICS_ANALYST, OPS_MANAGER, SYSTEM | - | - | text; may be empty; in {SUPPLIER, PLANNER, CARRIER_WAREHOUSE, LOGISTICS_ANALYST, OPS_MANAGER, SYSTEM}; required when APPROVED |
| `approved_date` | date | optional | regex ^\d{4}-\d{2}-\d{2}$ | - | - | ISO date YYYY-MM-DD; may be empty; matches ^\d{4}-\d{2}-\d{2}$; required when APPROVED; <= as_of_date |
| `cost_penalty_pct` | float | required | free | % | - | decimal; not null; >= 0; <= 100 |
| `effective_from` | date | required | regex ^\d{4}-\d{2}-\d{2}$ | - | PK part (composite unique) | ISO date YYYY-MM-DD; not null; matches ^\d{4}-\d{2}-\d{2}$ |
| `effective_to` | date | optional | regex ^\d{4}-\d{2}-\d{2}$ | - | - | ISO date YYYY-MM-DD; may be empty; matches ^\d{4}-\d{2}-\d{2}$ |

## BillOfMaterial  _(support)_

BOM header for FINISHED_MAKE SKUs.

**Primary key:** `bom_id`

| Field | Type | Req. | Allowed values | Unit | Uniqueness | Validation rule |
|---|---|---|---|---|---|---|
| `bom_id` | str | required | regex ^BOM-\d{6}$ | - | PK (unique) | text; not null; matches ^BOM-\d{6}$ |
| `parent_sku_id` | str | required | free | - | - | text; not null; FK -> SKU.sku_id |
| `bom_version` | int | required | free | - | - | integer; not null; >= 1 |
| `run_time_hours_per_unit` | float | required | free | hours/unit | - | decimal; not null; >= 0.0001 |
| `lot_size` | int | required | free | units | - | integer; not null; >= 1 |
| `effective_from` | date | required | regex ^\d{4}-\d{2}-\d{2}$ | - | - | ISO date YYYY-MM-DD; not null; matches ^\d{4}-\d{2}-\d{2}$ |
| `effective_to` | date | optional | regex ^\d{4}-\d{2}-\d{2}$ | - | - | ISO date YYYY-MM-DD; may be empty; matches ^\d{4}-\d{2}-\d{2}$ |

## BOMLine  _(support)_

BOM bridge (N:M parent<->component).

**Primary key:** `bom_id, component_sku_id`

| Field | Type | Req. | Allowed values | Unit | Uniqueness | Validation rule |
|---|---|---|---|---|---|---|
| `bom_id` | str | required | free | - | PK part (composite unique) | text; not null; FK -> BillOfMaterial.bom_id |
| `component_sku_id` | str | required | free | - | PK part (composite unique) | text; not null; FK -> SKU.sku_id |
| `qty_per` | int | required | free | component base UoM per parent unit | - | integer; not null; >= 1 |
| `scrap_pct` | float | required | free | fraction | - | decimal; not null; >= 0; <= 0.5 |

## WorkCenter  _(support)_

Production work centres (plants only).

**Primary key:** `work_center_id`

| Field | Type | Req. | Allowed values | Unit | Uniqueness | Validation rule |
|---|---|---|---|---|---|---|
| `work_center_id` | str | required | regex ^WC-LOC-\d{3}-\d{2}$ | - | PK (unique) | text; not null; matches ^WC-LOC-\d{3}-\d{2}$ |
| `location_id` | str | required | free | - | - | text; not null; FK -> Location.location_id |
| `work_center_name` | str | required | free | - | - | text; not null |
| `status` | str | required | ACTIVE, INACTIVE | - | - | text; not null; in {ACTIVE, INACTIVE} |

## ProductionCapacity  _(support)_

Weekly available hours per work centre.

**Primary key:** `prod_capacity_id`

| Field | Type | Req. | Allowed values | Unit | Uniqueness | Validation rule |
|---|---|---|---|---|---|---|
| `prod_capacity_id` | str | required | regex ^PCAP-\d{6}$ | - | PK (unique) | text; not null; matches ^PCAP-\d{6}$ |
| `work_center_id` | str | required | free | - | - | text; not null; FK -> WorkCenter.work_center_id |
| `iso_week` | str | required | regex ^20\d{2}W\d{2}$ | - | - | text; not null; matches ^20\d{2}W\d{2}$ |
| `week_start_date` | date | required | regex ^\d{4}-\d{2}-\d{2}$ | - | - | ISO date YYYY-MM-DD; not null; matches ^\d{4}-\d{2}-\d{2}$ |
| `available_hours` | float | required | free | hours/week | - | decimal; not null; >= 0 |

## ForecastDemand  _(core)_

Weekly forecast demand per SKU-location.

**Primary key:** `demand_id`

| Field | Type | Req. | Allowed values | Unit | Uniqueness | Validation rule |
|---|---|---|---|---|---|---|
| `demand_id` | str | required | regex ^DEM-SKU-\d{6}-LOC-\d{3}-2026W\d{2}$ | - | PK (unique) | text; not null; matches ^DEM-SKU-\d{6}-LOC-\d{3}-2026W\d{2}$; derived: 'DEM-'+sku_id+'-'+location_id+'-'+iso_week |
| `sku_id` | str | required | free | - | - | text; not null; FK -> SKU.sku_id |
| `location_id` | str | required | free | - | - | text; not null; FK -> Location.location_id |
| `iso_week` | str | required | regex ^20\d{2}W\d{2}$ | - | - | text; not null; matches ^20\d{2}W\d{2}$ |
| `week_start_date` | date | required | regex ^\d{4}-\d{2}-\d{2}$ | - | - | ISO date YYYY-MM-DD; not null; matches ^\d{4}-\d{2}-\d{2}$ |
| `forecast_qty` | int | required | free | base UoM | - | integer; not null; >= 0 |
| `demand_driver` | str | required | BASELINE, SEASONAL, PROMO, SPIKE | - | - | text; not null; in {BASELINE, SEASONAL, PROMO, SPIKE}; derived: SPIKE if unplanned uplift, else PROMO if promo window, else SEASONAL if seasonal factor>=1.2, else BASELINE |
| `forecast_stdev` | float | required | free | base UoM | - | decimal; not null; >= 0 |

## Inventory  _(core)_

On-hand inventory snapshot at as_of_date (inbound = open POs/production).

**Primary key:** `inventory_id`

| Field | Type | Req. | Allowed values | Unit | Uniqueness | Validation rule |
|---|---|---|---|---|---|---|
| `inventory_id` | str | required | regex ^INV-SKU-\d{6}-LOC-\d{3}$ | - | PK (unique) | text; not null; matches ^INV-SKU-\d{6}-LOC-\d{3}$ |
| `sku_id` | str | required | free | - | - | text; not null; FK -> SKU.sku_id |
| `location_id` | str | required | free | - | - | text; not null; FK -> Location.location_id |
| `as_of_date` | date | required | regex ^\d{4}-\d{2}-\d{2}$ | - | - | ISO date YYYY-MM-DD; not null; matches ^\d{4}-\d{2}-\d{2}$ |
| `on_hand_qty` | int | required | free | base UoM | - | integer; not null; >= 0 |
| `allocated_qty` | int | required | free | base UoM | - | integer; not null; >= 0 |
| `quality_hold_qty` | int | required | free | base UoM | - | integer; not null; >= 0 |
| `safety_stock_qty` | int | required | free | base UoM | - | integer; not null; >= 0 |
| `available_qty` | int | required | free | base UoM | - | integer; not null; derived: on_hand_qty - allocated_qty - quality_hold_qty |
| `inventory_status` | str | required | AVAILABLE, QUALITY_HOLD | - | - | text; not null; in {AVAILABLE, QUALITY_HOLD} |

## SupplierCapacity  _(core)_

Effective-dated supplier weekly capacity, MOQ and order multiple. If windows overlap the row with the latest effective_from wins.

**Primary key:** `capacity_id`

| Field | Type | Req. | Allowed values | Unit | Uniqueness | Validation rule |
|---|---|---|---|---|---|---|
| `capacity_id` | str | required | regex ^SCAP-\d{6}$ | - | PK (unique) | text; not null; matches ^SCAP-\d{6}$ |
| `supplier_id` | str | required | free | - | - | text; not null; FK -> Supplier.supplier_id |
| `product_family` | str | required | regex ^FAM-\d{2}$ | - | - | text; not null; matches ^FAM-\d{2}$ |
| `weekly_capacity_qty` | int | required | free | base UoM/week | - | integer; not null; >= 1 |
| `min_order_qty` | int | required | free | base UoM | - | integer; not null; >= 1 |
| `order_multiple` | int | required | free | base UoM | - | integer; not null; >= 1 |
| `capacity_uom` | str | required | EA, KG, MIXED | - | - | text; not null; in {EA, KG, MIXED}; capacity expressed in each SKU's base UoM |
| `status` | str | required | ACTIVE, INACTIVE | - | - | text; not null; in {ACTIVE, INACTIVE} |
| `effective_from` | date | required | regex ^\d{4}-\d{2}-\d{2}$ | - | - | ISO date YYYY-MM-DD; not null; matches ^\d{4}-\d{2}-\d{2}$ |
| `effective_to` | date | optional | regex ^\d{4}-\d{2}-\d{2}$ | - | - | ISO date YYYY-MM-DD; may be empty; matches ^\d{4}-\d{2}-\d{2}$ |

## LeadTime  _(core)_

Effective-dated lead time per supplier-SKU (optional ship-to override).

**Primary key:** `lead_time_id`

| Field | Type | Req. | Allowed values | Unit | Uniqueness | Validation rule |
|---|---|---|---|---|---|---|
| `lead_time_id` | str | required | regex ^LT-\d{6}$ | - | PK (unique) | text; not null; matches ^LT-\d{6}$ |
| `supplier_id` | str | required | free | - | - | text; not null; FK -> Supplier.supplier_id |
| `sku_id` | str | required | free | - | - | text; not null; FK -> SKU.sku_id |
| `ship_to_location_id` | str | optional | free | - | - | text; may be empty; FK -> Location.location_id; empty = default for all locations |
| `production_days` | int | required | free | days | - | integer; not null; >= 0 |
| `transit_days` | int | required | free | days | - | integer; not null; >= 0 |
| `total_lead_days` | int | required | free | days | - | integer; not null; >= 0; derived: production_days + transit_days |
| `p90_lead_days` | int | required | free | days | - | integer; not null; >= 0; >= total_lead_days |
| `transport_mode` | str | required | ROAD, RAIL, SEA, AIR | - | - | text; not null; in {ROAD, RAIL, SEA, AIR} |
| `effective_from` | date | required | regex ^\d{4}-\d{2}-\d{2}$ | - | - | ISO date YYYY-MM-DD; not null; matches ^\d{4}-\d{2}-\d{2}$ |
| `effective_to` | date | optional | regex ^\d{4}-\d{2}-\d{2}$ | - | - | ISO date YYYY-MM-DD; may be empty; matches ^\d{4}-\d{2}-\d{2}$ |

## PurchaseOrder  _(core)_

Inbound purchase orders (single-line; 1 SKU per PO).

**Primary key:** `po_id`

| Field | Type | Req. | Allowed values | Unit | Uniqueness | Validation rule |
|---|---|---|---|---|---|---|
| `po_id` | str | required | regex ^PO-2026-\d{6}$ | - | PK (unique) | text; not null; matches ^PO-2026-\d{6}$ |
| `supplier_id` | str | required | free | - | - | text; not null; FK -> Supplier.supplier_id |
| `sku_id` | str | required | free | - | - | text; not null; FK -> SKU.sku_id |
| `ship_to_location_id` | str | required | free | - | - | text; not null; FK -> Location.location_id |
| `carrier_id` | str | optional | free | - | - | text; may be empty; FK -> Carrier.carrier_id; assigned once shipped |
| `created_date` | date | required | regex ^\d{4}-\d{2}-\d{2}$ | - | - | ISO date YYYY-MM-DD; not null; matches ^\d{4}-\d{2}-\d{2}$; <= as_of_date and <= order_date |
| `order_date` | date | required | regex ^\d{4}-\d{2}-\d{2}$ | - | - | ISO date YYYY-MM-DD; not null; matches ^\d{4}-\d{2}-\d{2}$ |
| `requested_date` | date | required | regex ^\d{4}-\d{2}-\d{2}$ | - | - | ISO date YYYY-MM-DD; not null; matches ^\d{4}-\d{2}-\d{2}$; >= order_date |
| `promised_date` | date | required | regex ^\d{4}-\d{2}-\d{2}$ | - | - | ISO date YYYY-MM-DD; not null; matches ^\d{4}-\d{2}-\d{2}$; >= requested_date |
| `eta_date` | date | required | regex ^\d{4}-\d{2}-\d{2}$ | - | - | ISO date YYYY-MM-DD; not null; matches ^\d{4}-\d{2}-\d{2}$; derived: promised_date + sum(delay_days of DELAYED events) |
| `actual_receipt_date` | date | optional | regex ^\d{4}-\d{2}-\d{2}$ | - | - | ISO date YYYY-MM-DD; may be empty; matches ^\d{4}-\d{2}-\d{2}$; derived: eta_date when status=RECEIVED |
| `order_qty` | int | required | free | order_uom | - | integer; not null; >= 1 |
| `order_uom` | str | required | free | - | - | text; not null; FK -> UnitOfMeasure.uom_code |
| `qty_base` | int | required | free | base UoM | - | integer; not null; derived: order_qty * conversion factor(sku, order_uom) |
| `unit_price` | float | required | free | USD/base UoM | - | decimal; not null; >= 0.01 |
| `total_cost` | float | required | free | USD | - | decimal; not null; derived: round(qty_base * unit_price, 2) |
| `supplier_ref_no` | str | required | free | - | - | text; not null; supplier document number; the same number on two POs for the same supplier/SKU/ship-to/promised date means the inbound is double counted |
| `status` | str | required | PLANNED, CONFIRMED, IN_TRANSIT, DELAYED, RECEIVED, CANCELLED | - | - | text; not null; in {PLANNED, CONFIRMED, IN_TRANSIT, DELAYED, RECEIVED, CANCELLED}; derived: to_status of the latest PurchaseOrderEvent |

## ProductionPlan  _(core)_

Weekly requested production quantity per make-SKU/plant.

**Primary key:** `production_plan_id`

| Field | Type | Req. | Allowed values | Unit | Uniqueness | Validation rule |
|---|---|---|---|---|---|---|
| `production_plan_id` | str | required | regex ^PP-2026-\d{6}$ | - | PK (unique) | text; not null; matches ^PP-2026-\d{6}$ |
| `sku_id` | str | required | free | - | - | text; not null; FK -> SKU.sku_id |
| `location_id` | str | required | free | - | - | text; not null; FK -> Location.location_id |
| `work_center_id` | str | required | free | - | - | text; not null; FK -> WorkCenter.work_center_id |
| `bom_id` | str | required | free | - | - | text; not null; FK -> BillOfMaterial.bom_id |
| `iso_week` | str | required | regex ^20\d{2}W\d{2}$ | - | - | text; not null; matches ^20\d{2}W\d{2}$ |
| `week_start_date` | date | required | regex ^\d{4}-\d{2}-\d{2}$ | - | - | ISO date YYYY-MM-DD; not null; matches ^\d{4}-\d{2}-\d{2}$ |
| `planned_qty` | int | required | free | base UoM | - | integer; not null; >= 1; multiple of BOM lot_size |
| `required_hours` | float | required | free | hours | - | decimal; not null; derived: planned_qty * BillOfMaterial.run_time_hours_per_unit |
| `status` | str | required | PLANNED, FIRMED, RELEASED, COMPLETED, CANCELLED | - | - | text; not null; in {PLANNED, FIRMED, RELEASED, COMPLETED, CANCELLED}; derived: to_status of the latest ProductionPlanEvent |

## PurchaseOrderEvent  _(event)_

Append-only PO state changes.

**Primary key:** `event_id`

| Field | Type | Req. | Allowed values | Unit | Uniqueness | Validation rule |
|---|---|---|---|---|---|---|
| `event_id` | str | required | regex ^POE-\d{6}$ | - | PK (unique) | text; not null; matches ^POE-\d{6}$ |
| `po_id` | str | required | free | - | - | text; not null; FK -> PurchaseOrder.po_id |
| `event_type` | str | required | CREATED, CONFIRMED, SHIPPED, DELAYED, RECEIVED, CANCELLED | - | - | text; not null; in {CREATED, CONFIRMED, SHIPPED, DELAYED, RECEIVED, CANCELLED} |
| `from_status` | str | optional | PLANNED, CONFIRMED, IN_TRANSIT, DELAYED, RECEIVED, CANCELLED | - | - | text; may be empty; in {PLANNED, CONFIRMED, IN_TRANSIT, DELAYED, RECEIVED, CANCELLED} |
| `to_status` | str | required | PLANNED, CONFIRMED, IN_TRANSIT, DELAYED, RECEIVED, CANCELLED | - | - | text; not null; in {PLANNED, CONFIRMED, IN_TRANSIT, DELAYED, RECEIVED, CANCELLED} |
| `event_date` | date | required | regex ^\d{4}-\d{2}-\d{2}$ | - | - | ISO date YYYY-MM-DD; not null; matches ^\d{4}-\d{2}-\d{2}$; <= as_of_date |
| `actor_role` | str | required | SUPPLIER, PLANNER, CARRIER_WAREHOUSE, LOGISTICS_ANALYST, OPS_MANAGER, SYSTEM | - | - | text; not null; in {SUPPLIER, PLANNER, CARRIER_WAREHOUSE, LOGISTICS_ANALYST, OPS_MANAGER, SYSTEM} |
| `delay_days` | int | optional | free | days | - | integer; may be empty; >= 1; DELAYED only |
| `reason_code` | str | optional | free | - | - | text; may be empty |

## TransportEvent  _(event)_

Carrier tracking events.

**Primary key:** `event_id`

| Field | Type | Req. | Allowed values | Unit | Uniqueness | Validation rule |
|---|---|---|---|---|---|---|
| `event_id` | str | required | regex ^TRE-\d{6}$ | - | PK (unique) | text; not null; matches ^TRE-\d{6}$ |
| `po_id` | str | required | free | - | - | text; not null; FK -> PurchaseOrder.po_id |
| `carrier_id` | str | required | free | - | - | text; not null; FK -> Carrier.carrier_id |
| `event_type` | str | required | DEPARTED, DELAYED, ARRIVED | - | - | text; not null; in {DEPARTED, DELAYED, ARRIVED} |
| `event_date` | date | required | regex ^\d{4}-\d{2}-\d{2}$ | - | - | ISO date YYYY-MM-DD; not null; matches ^\d{4}-\d{2}-\d{2}$; <= as_of_date |
| `delay_days` | int | optional | free | days | - | integer; may be empty; >= 1 |
| `reason_code` | str | optional | WEATHER, PORT_CONGESTION, CUSTOMS, BREAKDOWN, DOCUMENTATION | - | - | text; may be empty; in {WEATHER, PORT_CONGESTION, CUSTOMS, BREAKDOWN, DOCUMENTATION} |
| `actor_role` | str | required | SUPPLIER, PLANNER, CARRIER_WAREHOUSE, LOGISTICS_ANALYST, OPS_MANAGER, SYSTEM | - | - | text; not null; in {SUPPLIER, PLANNER, CARRIER_WAREHOUSE, LOGISTICS_ANALYST, OPS_MANAGER, SYSTEM} |

## InventoryEvent  _(event)_

Inventory receipts/issues/adjustments.

**Primary key:** `event_id`

| Field | Type | Req. | Allowed values | Unit | Uniqueness | Validation rule |
|---|---|---|---|---|---|---|
| `event_id` | str | required | regex ^INE-\d{6}$ | - | PK (unique) | text; not null; matches ^INE-\d{6}$ |
| `sku_id` | str | required | free | - | - | text; not null; FK -> SKU.sku_id |
| `location_id` | str | required | free | - | - | text; not null; FK -> Location.location_id |
| `event_type` | str | required | RECEIPT, ISSUE, ADJUSTMENT | - | - | text; not null; in {RECEIPT, ISSUE, ADJUSTMENT} |
| `qty` | int | required | free | base UoM | - | integer; not null |
| `event_date` | date | required | regex ^\d{4}-\d{2}-\d{2}$ | - | - | ISO date YYYY-MM-DD; not null; matches ^\d{4}-\d{2}-\d{2}$; <= as_of_date |
| `po_id` | str | optional | free | - | - | text; may be empty; FK -> PurchaseOrder.po_id |
| `actor_role` | str | required | SUPPLIER, PLANNER, CARRIER_WAREHOUSE, LOGISTICS_ANALYST, OPS_MANAGER, SYSTEM | - | - | text; not null; in {SUPPLIER, PLANNER, CARRIER_WAREHOUSE, LOGISTICS_ANALYST, OPS_MANAGER, SYSTEM} |

## ProductionPlanEvent  _(event)_

Append-only production plan state changes.

**Primary key:** `event_id`

| Field | Type | Req. | Allowed values | Unit | Uniqueness | Validation rule |
|---|---|---|---|---|---|---|
| `event_id` | str | required | regex ^PPE-\d{6}$ | - | PK (unique) | text; not null; matches ^PPE-\d{6}$ |
| `production_plan_id` | str | required | free | - | - | text; not null; FK -> ProductionPlan.production_plan_id |
| `from_status` | str | optional | PLANNED, FIRMED, RELEASED, COMPLETED, CANCELLED | - | - | text; may be empty; in {PLANNED, FIRMED, RELEASED, COMPLETED, CANCELLED} |
| `to_status` | str | required | PLANNED, FIRMED, RELEASED, COMPLETED, CANCELLED | - | - | text; not null; in {PLANNED, FIRMED, RELEASED, COMPLETED, CANCELLED} |
| `event_date` | date | required | regex ^\d{4}-\d{2}-\d{2}$ | - | - | ISO date YYYY-MM-DD; not null; matches ^\d{4}-\d{2}-\d{2}$; <= as_of_date |
| `actor_role` | str | required | SUPPLIER, PLANNER, CARRIER_WAREHOUSE, LOGISTICS_ANALYST, OPS_MANAGER, SYSTEM | - | - | text; not null; in {SUPPLIER, PLANNER, CARRIER_WAREHOUSE, LOGISTICS_ANALYST, OPS_MANAGER, SYSTEM} |

## PlanRun  _(derived)_

One planning run.

**Primary key:** `run_id`

| Field | Type | Req. | Allowed values | Unit | Uniqueness | Validation rule |
|---|---|---|---|---|---|---|
| `run_id` | str | required | regex ^RUN-\d{4}$ | - | PK (unique) | text; not null; matches ^RUN-\d{4}$ |
| `as_of_date` | date | required | regex ^\d{4}-\d{2}-\d{2}$ | - | - | ISO date YYYY-MM-DD; not null; matches ^\d{4}-\d{2}-\d{2}$ |
| `seed` | int | required | free | - | - | integer; not null |
| `profile` | str | required | free | - | - | text; not null |
| `engine_version` | str | required | free | - | - | text; not null |
| `policy_hash` | str | required | free | - | - | text; not null |
| `n_pairs` | int | required | free | - | - | integer; not null; >= 0 |
| `n_shortages` | int | required | free | - | - | integer; not null; >= 0 |

## ProjectedBalance  _(derived)_

Week-by-week projected available balance (PAB).

**Primary key:** `run_id, sku_id, location_id, iso_week`

| Field | Type | Req. | Allowed values | Unit | Uniqueness | Validation rule |
|---|---|---|---|---|---|---|
| `run_id` | str | required | free | - | PK part (composite unique) | text; not null; FK -> PlanRun.run_id |
| `sku_id` | str | required | free | - | PK part (composite unique) | text; not null; FK -> SKU.sku_id |
| `location_id` | str | required | free | - | PK part (composite unique) | text; not null; FK -> Location.location_id |
| `iso_week` | str | required | regex ^20\d{2}W\d{2}$ | - | PK part (composite unique) | text; not null; matches ^20\d{2}W\d{2}$ |
| `week_start_date` | date | required | regex ^\d{4}-\d{2}-\d{2}$ | - | - | ISO date YYYY-MM-DD; not null; matches ^\d{4}-\d{2}-\d{2}$ |
| `opening_qty` | int | required | free | - | - | integer; not null; derived: previous closing_qty; week 1 = Inventory.available_qty |
| `gross_demand_qty` | int | required | free | - | - | integer; not null; >= 0; derived: ForecastDemand.forecast_qty |
| `dependent_demand_qty` | int | required | free | - | - | integer; not null; >= 0; derived: BOM explosion of capacity-limited production |
| `scheduled_receipts_qty` | int | required | free | - | - | integer; not null; >= 0; derived: sum qty_base of open, non-duplicate POs by ETA week |
| `production_receipts_qty` | int | required | free | - | - | integer; not null; >= 0; derived: capacity-limited planned production |
| `closing_qty` | int | required | free | - | - | integer; not null; derived: opening + receipts + production - gross - dependent |
| `safety_stock_qty` | int | required | free | - | - | integer; not null; >= 0 |
| `shortfall_qty` | int | required | free | - | - | integer; not null; >= 0; derived: max(0, safety_stock - closing) |

## SupplierCapacityLedger  _(derived)_

Committed vs. available supplier capacity by order week.

**Primary key:** `run_id, supplier_id, product_family, week_start_date`

| Field | Type | Req. | Allowed values | Unit | Uniqueness | Validation rule |
|---|---|---|---|---|---|---|
| `run_id` | str | required | free | - | PK part (composite unique) | text; not null; FK -> PlanRun.run_id |
| `supplier_id` | str | required | free | - | PK part (composite unique) | text; not null; FK -> Supplier.supplier_id |
| `product_family` | str | required | regex ^FAM-\d{2}$ | - | PK part (composite unique) | text; not null; matches ^FAM-\d{2}$ |
| `week_start_date` | date | required | regex ^\d{4}-\d{2}-\d{2}$ | - | PK part (composite unique) | ISO date YYYY-MM-DD; not null; matches ^\d{4}-\d{2}-\d{2}$ |
| `iso_week` | str | required | free | - | - | text; not null |
| `committed_qty` | int | required | free | - | - | integer; not null; >= 0 |
| `capacity_qty` | int | required | free | - | - | integer; not null; >= 0 |
| `utilisation_pct` | float | required | free | - | - | decimal; not null; >= 0; derived: 100*committed/capacity |
| `remaining_qty` | int | required | free | - | - | integer; not null; >= 0; derived: max(0, capacity-committed) |
| `status` | str | required | OK, EXCEEDED | - | - | text; not null; in {OK, EXCEEDED} |

## Shortage  _(core)_

Projected shortage episodes (output of the planning engine).

**Primary key:** `shortage_id`

| Field | Type | Req. | Allowed values | Unit | Uniqueness | Validation rule |
|---|---|---|---|---|---|---|
| `shortage_id` | str | required | regex ^SHORT-2026-\d{6}$ | - | PK (unique) | text; not null; matches ^SHORT-2026-\d{6}$ |
| `run_id` | str | required | free | - | - | text; not null; FK -> PlanRun.run_id |
| `sku_id` | str | required | free | - | - | text; not null; FK -> SKU.sku_id |
| `location_id` | str | required | free | - | - | text; not null; FK -> Location.location_id |
| `first_short_week` | str | required | regex ^20\d{2}W\d{2}$ | - | - | text; not null; matches ^20\d{2}W\d{2}$ |
| `last_short_week` | str | required | regex ^20\d{2}W\d{2}$ | - | - | text; not null; matches ^20\d{2}W\d{2}$ |
| `peak_short_week` | str | required | regex ^20\d{2}W\d{2}$ | - | - | text; not null; matches ^20\d{2}W\d{2}$ |
| `need_by_date` | date | required | regex ^\d{4}-\d{2}-\d{2}$ | - | - | ISO date YYYY-MM-DD; not null; matches ^\d{4}-\d{2}-\d{2}$; derived: Monday of first_short_week |
| `episode_weeks` | int | required | free | - | - | integer; not null; >= 1 |
| `shortage_type` | str | required | STOCKOUT, SAFETY_STOCK_BREACH | - | - | text; not null; in {STOCKOUT, SAFETY_STOCK_BREACH} |
| `shortage_qty` | int | required | free | base UoM | - | integer; not null; >= 1; derived: max over episode of (safety_stock - projected_balance) |
| `value_at_risk` | float | required | free | USD | - | decimal; not null; derived: shortage_qty * unit_price |
| `priority_score` | float | required | free | 0-100 | - | decimal; not null |
| `priority_rank` | int | required | free | - | - | integer; not null; >= 1 |
| `primary_cause_code` | str | required | INBOUND_LATE_TRANSPORT, INBOUND_LATE_SUPPLIER, SUPPLIER_CAPACITY, INBOUND_CANCELLED, PRODUCTION_CAPACITY, PRODUCTION_PLAN_CANCELLED, DEMAND_SPIKE, PRODUCTION_PLAN_SHORTFALL, INBOUND_QTY_SHORTFALL, INSUFFICIENT_LEAD_TIME, NO_INBOUND_PLANNED | - | - | text; not null; in {INBOUND_LATE_TRANSPORT, INBOUND_LATE_SUPPLIER, SUPPLIER_CAPACITY, INBOUND_CANCELLED, PRODUCTION_CAPACITY, PRODUCTION_PLAN_CANCELLED, DEMAND_SPIKE, PRODUCTION_PLAN_SHORTFALL, INBOUND_QTY_SHORTFALL, INSUFFICIENT_LEAD_TIME, NO_INBOUND_PLANNED}; derived: cause with the largest contribution |
| `data_quality_flag` | str | required | NONE, INBOUND_DOUBLE_COUNT, SUPPLIER_CAPACITY_EXCEEDED, SHORTAGE_MISSING_LEAD_TIME, UOM_MISMATCH | - | - | text; not null; in {NONE, INBOUND_DOUBLE_COUNT, SUPPLIER_CAPACITY_EXCEEDED, SHORTAGE_MISSING_LEAD_TIME, UOM_MISMATCH} |
| `status` | str | required | DETECTED, ANALYZED, NEEDS_REVIEW, MITIGATION_PROPOSED, MITIGATION_APPROVED, RESOLVED, ACCEPTED_BACKORDER | - | - | text; not null; in {DETECTED, ANALYZED, NEEDS_REVIEW, MITIGATION_PROPOSED, MITIGATION_APPROVED, RESOLVED, ACCEPTED_BACKORDER}; derived: to_status of latest ShortageEvent |

## ShortageCause  _(derived)_

Evidence bridge: shortage <-> source records (N:M).

**Primary key:** `shortage_id, cause_seq`

| Field | Type | Req. | Allowed values | Unit | Uniqueness | Validation rule |
|---|---|---|---|---|---|---|
| `shortage_id` | str | required | free | - | PK part (composite unique) | text; not null; FK -> Shortage.shortage_id |
| `cause_seq` | int | required | free | - | PK part (composite unique) | integer; not null; >= 1 |
| `cause_code` | str | required | INBOUND_LATE_TRANSPORT, INBOUND_LATE_SUPPLIER, SUPPLIER_CAPACITY, INBOUND_CANCELLED, PRODUCTION_CAPACITY, PRODUCTION_PLAN_CANCELLED, DEMAND_SPIKE, PRODUCTION_PLAN_SHORTFALL, INBOUND_QTY_SHORTFALL, INSUFFICIENT_LEAD_TIME, NO_INBOUND_PLANNED | - | - | text; not null; in {INBOUND_LATE_TRANSPORT, INBOUND_LATE_SUPPLIER, SUPPLIER_CAPACITY, INBOUND_CANCELLED, PRODUCTION_CAPACITY, PRODUCTION_PLAN_CANCELLED, DEMAND_SPIKE, PRODUCTION_PLAN_SHORTFALL, INBOUND_QTY_SHORTFALL, INSUFFICIENT_LEAD_TIME, NO_INBOUND_PLANNED} |
| `contribution_qty` | int | required | free | - | - | integer; not null; >= 1 |
| `source_table` | str | required | free | - | - | text; not null |
| `source_id` | str | required | free | - | - | text; not null |
| `explanation` | str | required | free | - | - | text; not null |

## MitigationOption  _(core)_

Candidate mitigations with cost/service trade-offs.

**Primary key:** `mitigation_id`

| Field | Type | Req. | Allowed values | Unit | Uniqueness | Validation rule |
|---|---|---|---|---|---|---|
| `mitigation_id` | str | required | regex ^MIT-SHORT-2026-\d{6}-\d{2}$ | - | PK (unique) | text; not null; matches ^MIT-SHORT-2026-\d{6}-\d{2}$; derived: 'MIT-'+shortage_id+'-'+NN |
| `shortage_id` | str | required | free | - | - | text; not null; FK -> Shortage.shortage_id |
| `option_type` | str | required | EXPEDITE_PO, NEW_PO, ALT_SUPPLIER_PO, SUBSTITUTE_SKU, LOCATION_TRANSFER, PRODUCTION_REPLAN, PARTIAL_FILL_BACKORDER | - | - | text; not null; in {EXPEDITE_PO, NEW_PO, ALT_SUPPLIER_PO, SUBSTITUTE_SKU, LOCATION_TRANSFER, PRODUCTION_REPLAN, PARTIAL_FILL_BACKORDER} |
| `supplier_id` | str | optional | free | - | - | text; may be empty; FK -> Supplier.supplier_id |
| `alt_sku_id` | str | optional | free | - | - | text; may be empty; FK -> SKU.sku_id |
| `source_location_id` | str | optional | free | - | - | text; may be empty; FK -> Location.location_id |
| `ref_po_id` | str | optional | free | - | - | text; may be empty; FK -> PurchaseOrder.po_id |
| `production_plan_id` | str | optional | free | - | - | text; may be empty; FK -> ProductionPlan.production_plan_id |
| `qty` | int | required | free | base UoM of the option's SKU | - | integer; not null; >= 0; after MOQ / multiple / lot rounding |
| `covered_qty` | int | required | free | shortage-SKU base UoM | - | integer; not null; >= 0 |
| `unit_cost` | float | required | free | USD/base UoM | - | decimal; not null; >= 0 |
| `expedite_premium` | float | required | free | USD | - | decimal; not null; >= 0 |
| `freight_cost` | float | required | free | USD | - | decimal; not null; >= 0 |
| `excess_cost` | float | required | free | USD | - | decimal; not null; >= 0 |
| `penalty_cost` | float | required | free | USD | - | decimal; not null; >= 0 |
| `total_cost` | float | required | free | USD | - | decimal; not null; derived: expedite_premium+freight_cost+excess_cost+penalty_cost (incremental cost) |
| `cost_delta_vs_baseline` | float | required | free | USD | - | decimal; not null; derived: total_cost - backorder option total_cost |
| `lead_days` | int | optional | free | days | - | integer; may be empty; >= 0 |
| `earliest_arrival_date` | date | optional | regex ^\d{4}-\d{2}-\d{2}$ | - | - | ISO date YYYY-MM-DD; may be empty; matches ^\d{4}-\d{2}-\d{2}$ |
| `weeks_late` | int | optional | free | - | - | integer; may be empty; >= 0 |
| `fill_rate_pct` | float | required | free | % | - | decimal; not null; >= 0; <= 100; derived: 100*covered/shortage_qty*(1-min(1,weeks_late/episode_weeks)) |
| `capacity_available_qty` | int | optional | free | base UoM | - | integer; may be empty; >= 0 |
| `capacity_check` | str | required | PASS, FAIL, NA | - | - | text; not null; in {PASS, FAIL, NA} |
| `policy_check` | str | required | PASS, FAIL | - | - | text; not null; in {PASS, FAIL} |
| `policy_reason` | str | optional | free | - | - | text; may be empty |
| `lead_time_check` | str | required | OK, LATE, MISSING, NA | - | - | text; not null; in {OK, LATE, MISSING, NA} |
| `approval_required_role` | str | required | PLANNER, OPS_MANAGER | - | - | text; not null; in {PLANNER, OPS_MANAGER} |
| `is_recommendable` | int | required | 0, 1 | - | - | integer; not null; in {0, 1} |
| `rank` | int | required | free | - | - | integer; not null; >= 1 |
| `is_recommended` | int | required | 0, 1 | - | - | integer; not null; in {0, 1} |
| `status` | str | required | PROPOSED, APPROVED, REJECTED, EXECUTED | - | - | text; not null; in {PROPOSED, APPROVED, REJECTED, EXECUTED}; derived: to_status of latest MitigationEvent |

## ShortageEvent  _(event)_

Append-only shortage lifecycle.

**Primary key:** `event_id`

| Field | Type | Req. | Allowed values | Unit | Uniqueness | Validation rule |
|---|---|---|---|---|---|---|
| `event_id` | str | required | regex ^SHE-\d{6}$ | - | PK (unique) | text; not null; matches ^SHE-\d{6}$ |
| `shortage_id` | str | required | free | - | - | text; not null; FK -> Shortage.shortage_id |
| `from_status` | str | optional | DETECTED, ANALYZED, NEEDS_REVIEW, MITIGATION_PROPOSED, MITIGATION_APPROVED, RESOLVED, ACCEPTED_BACKORDER | - | - | text; may be empty; in {DETECTED, ANALYZED, NEEDS_REVIEW, MITIGATION_PROPOSED, MITIGATION_APPROVED, RESOLVED, ACCEPTED_BACKORDER} |
| `to_status` | str | required | DETECTED, ANALYZED, NEEDS_REVIEW, MITIGATION_PROPOSED, MITIGATION_APPROVED, RESOLVED, ACCEPTED_BACKORDER | - | - | text; not null; in {DETECTED, ANALYZED, NEEDS_REVIEW, MITIGATION_PROPOSED, MITIGATION_APPROVED, RESOLVED, ACCEPTED_BACKORDER} |
| `event_date` | date | required | regex ^\d{4}-\d{2}-\d{2}$ | - | - | ISO date YYYY-MM-DD; not null; matches ^\d{4}-\d{2}-\d{2}$ |
| `actor_role` | str | required | SUPPLIER, PLANNER, CARRIER_WAREHOUSE, LOGISTICS_ANALYST, OPS_MANAGER, SYSTEM | - | - | text; not null; in {SUPPLIER, PLANNER, CARRIER_WAREHOUSE, LOGISTICS_ANALYST, OPS_MANAGER, SYSTEM} |
| `comment` | str | optional | free | - | - | text; may be empty |

## MitigationEvent  _(event)_

Append-only mitigation lifecycle.

**Primary key:** `event_id`

| Field | Type | Req. | Allowed values | Unit | Uniqueness | Validation rule |
|---|---|---|---|---|---|---|
| `event_id` | str | required | regex ^MIE-\d{6}$ | - | PK (unique) | text; not null; matches ^MIE-\d{6}$ |
| `mitigation_id` | str | required | free | - | - | text; not null; FK -> MitigationOption.mitigation_id |
| `from_status` | str | optional | PROPOSED, APPROVED, REJECTED, EXECUTED | - | - | text; may be empty; in {PROPOSED, APPROVED, REJECTED, EXECUTED} |
| `to_status` | str | required | PROPOSED, APPROVED, REJECTED, EXECUTED | - | - | text; not null; in {PROPOSED, APPROVED, REJECTED, EXECUTED} |
| `event_date` | date | required | regex ^\d{4}-\d{2}-\d{2}$ | - | - | ISO date YYYY-MM-DD; not null; matches ^\d{4}-\d{2}-\d{2}$ |
| `actor_role` | str | required | SUPPLIER, PLANNER, CARRIER_WAREHOUSE, LOGISTICS_ANALYST, OPS_MANAGER, SYSTEM | - | - | text; not null; in {SUPPLIER, PLANNER, CARRIER_WAREHOUSE, LOGISTICS_ANALYST, OPS_MANAGER, SYSTEM} |
| `comment` | str | optional | free | - | - | text; may be empty |

## DataQualityFinding  _(derived)_

Exceptions raised by the planning engine data-quality gate.

**Primary key:** `finding_id`

| Field | Type | Req. | Allowed values | Unit | Uniqueness | Validation rule |
|---|---|---|---|---|---|---|
| `finding_id` | str | required | regex ^DQF-\d{6}$ | - | PK (unique) | text; not null; matches ^DQF-\d{6}$ |
| `run_id` | str | required | free | - | - | text; not null; FK -> PlanRun.run_id |
| `issue_type` | str | required | INBOUND_DOUBLE_COUNT, SUBSTITUTE_NOT_APPROVED, SUPPLIER_CAPACITY_EXCEEDED, SHORTAGE_MISSING_LEAD_TIME, UOM_MISMATCH, UOM_FACTOR_MISSING | - | - | text; not null; in {INBOUND_DOUBLE_COUNT, SUBSTITUTE_NOT_APPROVED, SUPPLIER_CAPACITY_EXCEEDED, SHORTAGE_MISSING_LEAD_TIME, UOM_MISMATCH, UOM_FACTOR_MISSING} |
| `entity` | str | required | free | - | - | text; not null |
| `record_id` | str | required | free | - | - | text; not null |
| `related_record_ids` | str | optional | free | - | - | text; may be empty |
| `impact_qty` | int | optional | free | - | - | integer; may be empty |
| `detail` | str | required | free | - | - | text; not null |

## ground_truth (separate file, never an input)

Columns: `label_id`, `label_class`, `issue_type`, `entity`, `record_id`, `related_record_ids`, `injected_field`, `original_value`, `injected_value`, `expected_detection`, `expected_decision`, `impact_qty`, `rule_ref`, `seed`
