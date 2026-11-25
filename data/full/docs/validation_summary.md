# Validation summary

Profile **full**, seed **20261022**, as-of **2025-12-29**.

* Checks executed: **682**
* Unexpected failures (all non-labelled checks): **0**
* Labelled checks (fail only on injected ground-truth rows): **5**
* Validator failures == ground-truth anomalies for all 5 edge cases: **True**
* Engine detection precision = recall = 1.0 on all 5 edge cases (boundary cases not flagged): **True**
* Expected decisions taken for all 5 edge cases: **True**

## Results by category

| Category | Checks | Failed checks | Rows failing |
|---|---|---|---|
| acceptance | 18 | 0 | 0 |
| arithmetic | 11 | 0 | 0 |
| coverage | 6 | 0 | 0 |
| date_order | 26 | 0 | 0 |
| duplicate | 3 | 0 | 0 |
| edge_case | 5 | 0 | 0 |
| enum | 62 | 0 | 0 |
| foreign_key | 62 | 0 | 0 |
| format | 52 | 0 | 0 |
| id_pattern | 27 | 0 | 0 |
| lifecycle | 17 | 0 | 0 |
| primary_key | 32 | 0 | 0 |
| range | 70 | 0 | 0 |
| required | 254 | 0 | 0 |
| schema | 32 | 0 | 0 |
| volume | 5 | 0 | 0 |

## Labelled data-quality checks (expected to fail only on injected rows)

| Check | Table | Rows checked | Rows flagged |
|---|---|---|---|
| dq.duplicate_po | PurchaseOrder | 10000 | 45 |
| dq.uom_arithmetic | PurchaseOrder | 10000 | 30 |
| dq.capacity_ledger | SupplierCapacityLedger | 8266 | 30 |
| dq.lead_time_defined | LeadTime | 4301 | 60 |
| dq.substitute_approved | SKUSubstitute | 383 | 30 |

## Edge-case detection vs. ground truth

| Issue type | Labelled | Boundary | Flagged by engine | TP | FP | FN | Precision | Recall | Validator exact match |
|---|---|---|---|---|---|---|---|---|---|
| INBOUND_DOUBLE_COUNT | 45 | 1 | 45 | 45 | 0 | 0 | 1.0 | 1.0 | True |
| SUBSTITUTE_NOT_APPROVED | 30 | 0 | 30 | 30 | 0 | 0 | 1.0 | 1.0 | True |
| SUPPLIER_CAPACITY_EXCEEDED | 30 | 1 | 30 | 30 | 0 | 0 | 1.0 | 1.0 | True |
| SHORTAGE_MISSING_LEAD_TIME | 60 | 0 | 60 | 60 | 0 | 0 | 1.0 | 1.0 | True |
| UOM_MISMATCH | 30 | 0 | 30 | 30 | 0 | 0 | 1.0 | 1.0 | True |

## Expected decisions

| Issue type | Decision | Cases | As expected |
|---|---|---|---|
| SHORTAGE_MISSING_LEAD_TIME | FLAG_AND_BLOCK_MITIGATION | 30 | True |
| SUBSTITUTE_NOT_APPROVED | REJECT_OPTION_NEVER_RECOMMEND | 30 | True |
| INBOUND_DOUBLE_COUNT | EXCLUDE_DUPLICATE | 45 | True |
| UOM_MISMATCH | USE_CONVERTED_QUANTITY | 30 | True |
| SUPPLIER_CAPACITY_EXCEEDED | FLAG_AND_LIMIT_MITIGATION_CAPACITY | 30 | True |

## Planning KPIs

```json
{
  "by_primary_cause": {
    "DEMAND_SPIKE": 389,
    "INBOUND_CANCELLED": 104,
    "INBOUND_LATE_SUPPLIER": 71,
    "INBOUND_LATE_TRANSPORT": 42,
    "INBOUND_QTY_SHORTFALL": 408,
    "NO_INBOUND_PLANNED": 167,
    "PRODUCTION_CAPACITY": 75,
    "PRODUCTION_PLAN_CANCELLED": 233,
    "PRODUCTION_PLAN_SHORTFALL": 100,
    "SUPPLIER_CAPACITY": 11
  },
  "by_status": {
    "MITIGATION_PROPOSED": 1557,
    "NEEDS_REVIEW": 43
  },
  "by_type": {
    "SAFETY_STOCK_BREACH": 430,
    "STOCKOUT": 1170
  },
  "data_quality_findings": {
    "INBOUND_DOUBLE_COUNT": 45,
    "SHORTAGE_MISSING_LEAD_TIME": 60,
    "SUBSTITUTE_NOT_APPROVED": 30,
    "SUPPLIER_CAPACITY_EXCEEDED": 30,
    "UOM_MISMATCH": 30
  },
  "do_nothing_backorder_cost_usd": 30331882.16,
  "mean_recommended_fill_rate_pct": 97.74,
  "pct_shortages_with_2plus_options": 100.0,
  "pct_shortages_with_cause": 100.0,
  "recommended_incremental_cost_usd": 391295.76,
  "recommended_option_mix": {
    "ALT_SUPPLIER_PO": 188,
    "EXPEDITE_PO": 18,
    "LOCATION_TRANSFER": 550,
    "NEW_PO": 528,
    "PARTIAL_FILL_BACKORDER": 5,
    "PRODUCTION_REPLAN": 304,
    "SUBSTITUTE_SKU": 7
  },
  "shortages": 1600,
  "value_at_risk_usd": 18044561.72
}
```

## Data distributions (evaluation area A)

```json
{
  "demand_driver_mix_pct": {
    "BASELINE": 89.37,
    "PROMO": 0.3,
    "SEASONAL": 10.22,
    "SPIKE": 0.11
  },
  "lead_time_days": {
    "0.1": 9.0,
    "0.5": 18.0,
    "0.9": 46.0,
    "0.99": 62.0
  },
  "po_order_uom_mix": {
    "BAG": 133,
    "CASE": 3880,
    "EA": 4606,
    "KG": 1381
  },
  "po_status_mix": {
    "CANCELLED": 99,
    "CONFIRMED": 1587,
    "DELAYED": 44,
    "IN_TRANSIT": 296,
    "PLANNED": 7374,
    "RECEIVED": 600
  },
  "top_20pct_skus_demand_share": 0.788,
  "weekly_demand_per_pair": {
    "0.1": 1.08,
    "0.5": 9.88,
    "0.9": 56.44,
    "0.99": 189.89
  },
  "weeks_of_cover_at_as_of": {
    "0.1": 3.1,
    "0.5": 52.93,
    "0.9": 269.15,
    "0.99": 4011.14
  },
  "zero_demand_weeks_pct": 7.41
}
```

## Generation metadata

```json
{
  "actual_assortment_density": 0.1,
  "baseline_checks_clean": 677,
  "n_families": 12,
  "n_pairs_active": 14700,
  "n_pairs_inactive": 300,
  "n_pairs_total": 15000,
  "n_plants": 6
}
```

## Every check

| Category | Check | Table | Kind | Checked | Failed | Status |
|---|---|---|---|---|---|---|
| schema | schema.columns_match | UnitOfMeasure | rule | 3 | 0 | PASS |
| primary_key | pk.unique | UnitOfMeasure | rule | 4 | 0 | PASS |
| required | required.uom_code | UnitOfMeasure | rule | 4 | 0 | PASS |
| format | pattern.uom_code | UnitOfMeasure | rule | 4 | 0 | PASS |
| required | required.uom_name | UnitOfMeasure | rule | 4 | 0 | PASS |
| required | required.uom_class | UnitOfMeasure | rule | 4 | 0 | PASS |
| enum | enum.uom_class | UnitOfMeasure | rule | 4 | 0 | PASS |
| schema | schema.columns_match | Location | rule | 8 | 0 | PASS |
| primary_key | pk.unique | Location | rule | 50 | 0 | PASS |
| required | required.location_id | Location | rule | 50 | 0 | PASS |
| id_pattern | pattern.location_id | Location | rule | 50 | 0 | PASS |
| required | required.location_name | Location | rule | 50 | 0 | PASS |
| required | required.location_type | Location | rule | 50 | 0 | PASS |
| enum | enum.location_type | Location | rule | 50 | 0 | PASS |
| required | required.region | Location | rule | 50 | 0 | PASS |
| enum | enum.region | Location | rule | 50 | 0 | PASS |
| required | required.country | Location | rule | 50 | 0 | PASS |
| required | required.status | Location | rule | 50 | 0 | PASS |
| enum | enum.status | Location | rule | 50 | 0 | PASS |
| required | required.effective_from | Location | rule | 50 | 0 | PASS |
| format | pattern.effective_from | Location | rule | 50 | 0 | PASS |
| format | pattern.effective_to | Location | rule | 0 | 0 | PASS |
| schema | schema.columns_match | Carrier | rule | 4 | 0 | PASS |
| primary_key | pk.unique | Carrier | rule | 8 | 0 | PASS |
| required | required.carrier_id | Carrier | rule | 8 | 0 | PASS |
| id_pattern | pattern.carrier_id | Carrier | rule | 8 | 0 | PASS |
| required | required.carrier_name | Carrier | rule | 8 | 0 | PASS |
| required | required.mode | Carrier | rule | 8 | 0 | PASS |
| enum | enum.mode | Carrier | rule | 8 | 0 | PASS |
| required | required.sourcing_region | Carrier | rule | 8 | 0 | PASS |
| enum | enum.sourcing_region | Carrier | rule | 8 | 0 | PASS |
| schema | schema.columns_match | Supplier | rule | 11 | 0 | PASS |
| primary_key | pk.unique | Supplier | rule | 500 | 0 | PASS |
| required | required.supplier_id | Supplier | rule | 500 | 0 | PASS |
| id_pattern | pattern.supplier_id | Supplier | rule | 500 | 0 | PASS |
| required | required.supplier_name | Supplier | rule | 500 | 0 | PASS |
| required | required.country | Supplier | rule | 500 | 0 | PASS |
| required | required.region | Supplier | rule | 500 | 0 | PASS |
| enum | enum.region | Supplier | rule | 500 | 0 | PASS |
| required | required.tier | Supplier | rule | 500 | 0 | PASS |
| enum | enum.tier | Supplier | rule | 500 | 0 | PASS |
| required | required.status | Supplier | rule | 500 | 0 | PASS |
| enum | enum.status | Supplier | rule | 500 | 0 | PASS |
| required | required.currency | Supplier | rule | 500 | 0 | PASS |
| enum | enum.currency | Supplier | rule | 500 | 0 | PASS |
| required | required.payment_terms_days | Supplier | rule | 500 | 0 | PASS |
| range | min.payment_terms_days | Supplier | rule | 500 | 0 | PASS |
| range | max.payment_terms_days | Supplier | rule | 500 | 0 | PASS |
| required | required.onboarded_date | Supplier | rule | 500 | 0 | PASS |
| format | pattern.onboarded_date | Supplier | rule | 500 | 0 | PASS |
| required | required.effective_from | Supplier | rule | 500 | 0 | PASS |
| format | pattern.effective_from | Supplier | rule | 500 | 0 | PASS |
| format | pattern.effective_to | Supplier | rule | 0 | 0 | PASS |
| schema | schema.columns_match | SKU | rule | 12 | 0 | PASS |
| primary_key | pk.unique | SKU | rule | 3000 | 0 | PASS |
| required | required.sku_id | SKU | rule | 3000 | 0 | PASS |
| id_pattern | pattern.sku_id | SKU | rule | 3000 | 0 | PASS |
| required | required.sku_name | SKU | rule | 3000 | 0 | PASS |
| required | required.product_family | SKU | rule | 3000 | 0 | PASS |
| format | pattern.product_family | SKU | rule | 3000 | 0 | PASS |
| required | required.sku_type | SKU | rule | 3000 | 0 | PASS |
| enum | enum.sku_type | SKU | rule | 3000 | 0 | PASS |
| required | required.base_uom | SKU | rule | 3000 | 0 | PASS |
| enum | enum.base_uom | SKU | rule | 3000 | 0 | PASS |
| foreign_key | fk.base_uom->UnitOfMeasure.uom_code | SKU | rule | 3000 | 0 | PASS |
| required | required.unit_cost | SKU | rule | 3000 | 0 | PASS |
| range | min.unit_cost | SKU | rule | 3000 | 0 | PASS |
| required | required.unit_price | SKU | rule | 3000 | 0 | PASS |
| range | min.unit_price | SKU | rule | 3000 | 0 | PASS |
| required | required.service_level_target | SKU | rule | 3000 | 0 | PASS |
| range | min.service_level_target | SKU | rule | 3000 | 0 | PASS |
| range | max.service_level_target | SKU | rule | 3000 | 0 | PASS |
| required | required.criticality | SKU | rule | 3000 | 0 | PASS |
| enum | enum.criticality | SKU | rule | 3000 | 0 | PASS |
| required | required.lifecycle_status | SKU | rule | 3000 | 0 | PASS |
| enum | enum.lifecycle_status | SKU | rule | 3000 | 0 | PASS |
| required | required.effective_from | SKU | rule | 3000 | 0 | PASS |
| format | pattern.effective_from | SKU | rule | 3000 | 0 | PASS |
| format | pattern.effective_to | SKU | rule | 0 | 0 | PASS |
| schema | schema.columns_match | UoMConversion | rule | 5 | 0 | PASS |
| primary_key | pk.unique | UoMConversion | rule | 2400 | 0 | PASS |
| required | required.conversion_id | UoMConversion | rule | 2400 | 0 | PASS |
| id_pattern | pattern.conversion_id | UoMConversion | rule | 2400 | 0 | PASS |
| required | required.sku_id | UoMConversion | rule | 2400 | 0 | PASS |
| foreign_key | fk.sku_id->SKU.sku_id | UoMConversion | rule | 2400 | 0 | PASS |
| required | required.from_uom | UoMConversion | rule | 2400 | 0 | PASS |
| enum | enum.from_uom | UoMConversion | rule | 2400 | 0 | PASS |
| foreign_key | fk.from_uom->UnitOfMeasure.uom_code | UoMConversion | rule | 2400 | 0 | PASS |
| required | required.to_uom | UoMConversion | rule | 2400 | 0 | PASS |
| enum | enum.to_uom | UoMConversion | rule | 2400 | 0 | PASS |
| foreign_key | fk.to_uom->UnitOfMeasure.uom_code | UoMConversion | rule | 2400 | 0 | PASS |
| required | required.factor | UoMConversion | rule | 2400 | 0 | PASS |
| range | min.factor | UoMConversion | rule | 2400 | 0 | PASS |
| schema | schema.columns_match | SKULocation | rule | 5 | 0 | PASS |
| primary_key | pk.unique | SKULocation | rule | 15000 | 0 | PASS |
| required | required.sku_id | SKULocation | rule | 15000 | 0 | PASS |
| foreign_key | fk.sku_id->SKU.sku_id | SKULocation | rule | 15000 | 0 | PASS |
| required | required.location_id | SKULocation | rule | 15000 | 0 | PASS |
| foreign_key | fk.location_id->Location.location_id | SKULocation | rule | 15000 | 0 | PASS |
| required | required.stocking_status | SKULocation | rule | 15000 | 0 | PASS |
| enum | enum.stocking_status | SKULocation | rule | 15000 | 0 | PASS |
| required | required.effective_from | SKULocation | rule | 15000 | 0 | PASS |
| format | pattern.effective_from | SKULocation | rule | 15000 | 0 | PASS |
| format | pattern.effective_to | SKULocation | rule | 0 | 0 | PASS |
| schema | schema.columns_match | SKUSupplier | rule | 7 | 0 | PASS |
| primary_key | pk.unique | SKUSupplier | rule | 4301 | 0 | PASS |
| required | required.sku_id | SKUSupplier | rule | 4301 | 0 | PASS |
| foreign_key | fk.sku_id->SKU.sku_id | SKUSupplier | rule | 4301 | 0 | PASS |
| required | required.supplier_id | SKUSupplier | rule | 4301 | 0 | PASS |
| foreign_key | fk.supplier_id->Supplier.supplier_id | SKUSupplier | rule | 4301 | 0 | PASS |
| required | required.is_preferred | SKUSupplier | rule | 4301 | 0 | PASS |
| enum | enum.is_preferred | SKUSupplier | rule | 4301 | 0 | PASS |
| required | required.approval_status | SKUSupplier | rule | 4301 | 0 | PASS |
| enum | enum.approval_status | SKUSupplier | rule | 4301 | 0 | PASS |
| required | required.unit_price | SKUSupplier | rule | 4301 | 0 | PASS |
| range | min.unit_price | SKUSupplier | rule | 4301 | 0 | PASS |
| required | required.effective_from | SKUSupplier | rule | 4301 | 0 | PASS |
| format | pattern.effective_from | SKUSupplier | rule | 4301 | 0 | PASS |
| format | pattern.effective_to | SKUSupplier | rule | 0 | 0 | PASS |
| schema | schema.columns_match | SKUSubstitute | rule | 9 | 0 | PASS |
| primary_key | pk.unique | SKUSubstitute | rule | 383 | 0 | PASS |
| required | required.sku_id | SKUSubstitute | rule | 383 | 0 | PASS |
| foreign_key | fk.sku_id->SKU.sku_id | SKUSubstitute | rule | 383 | 0 | PASS |
| required | required.substitute_sku_id | SKUSubstitute | rule | 383 | 0 | PASS |
| foreign_key | fk.substitute_sku_id->SKU.sku_id | SKUSubstitute | rule | 383 | 0 | PASS |
| required | required.substitution_ratio | SKUSubstitute | rule | 383 | 0 | PASS |
| range | min.substitution_ratio | SKUSubstitute | rule | 383 | 0 | PASS |
| range | max.substitution_ratio | SKUSubstitute | rule | 383 | 0 | PASS |
| required | required.approval_status | SKUSubstitute | rule | 383 | 0 | PASS |
| enum | enum.approval_status | SKUSubstitute | rule | 383 | 0 | PASS |
| enum | enum.approved_by_role | SKUSubstitute | rule | 363 | 0 | PASS |
| format | pattern.approved_date | SKUSubstitute | rule | 363 | 0 | PASS |
| required | required.cost_penalty_pct | SKUSubstitute | rule | 383 | 0 | PASS |
| range | min.cost_penalty_pct | SKUSubstitute | rule | 383 | 0 | PASS |
| range | max.cost_penalty_pct | SKUSubstitute | rule | 383 | 0 | PASS |
| required | required.effective_from | SKUSubstitute | rule | 383 | 0 | PASS |
| format | pattern.effective_from | SKUSubstitute | rule | 383 | 0 | PASS |
| format | pattern.effective_to | SKUSubstitute | rule | 10 | 0 | PASS |
| schema | schema.columns_match | BillOfMaterial | rule | 7 | 0 | PASS |
| primary_key | pk.unique | BillOfMaterial | rule | 600 | 0 | PASS |
| required | required.bom_id | BillOfMaterial | rule | 600 | 0 | PASS |
| id_pattern | pattern.bom_id | BillOfMaterial | rule | 600 | 0 | PASS |
| required | required.parent_sku_id | BillOfMaterial | rule | 600 | 0 | PASS |
| foreign_key | fk.parent_sku_id->SKU.sku_id | BillOfMaterial | rule | 600 | 0 | PASS |
| required | required.bom_version | BillOfMaterial | rule | 600 | 0 | PASS |
| range | min.bom_version | BillOfMaterial | rule | 600 | 0 | PASS |
| required | required.run_time_hours_per_unit | BillOfMaterial | rule | 600 | 0 | PASS |
| range | min.run_time_hours_per_unit | BillOfMaterial | rule | 600 | 0 | PASS |
| required | required.lot_size | BillOfMaterial | rule | 600 | 0 | PASS |
| range | min.lot_size | BillOfMaterial | rule | 600 | 0 | PASS |
| required | required.effective_from | BillOfMaterial | rule | 600 | 0 | PASS |
| format | pattern.effective_from | BillOfMaterial | rule | 600 | 0 | PASS |
| format | pattern.effective_to | BillOfMaterial | rule | 0 | 0 | PASS |
| schema | schema.columns_match | BOMLine | rule | 4 | 0 | PASS |
| primary_key | pk.unique | BOMLine | rule | 1824 | 0 | PASS |
| required | required.bom_id | BOMLine | rule | 1824 | 0 | PASS |
| foreign_key | fk.bom_id->BillOfMaterial.bom_id | BOMLine | rule | 1824 | 0 | PASS |
| required | required.component_sku_id | BOMLine | rule | 1824 | 0 | PASS |
| foreign_key | fk.component_sku_id->SKU.sku_id | BOMLine | rule | 1824 | 0 | PASS |
| required | required.qty_per | BOMLine | rule | 1824 | 0 | PASS |
| range | min.qty_per | BOMLine | rule | 1824 | 0 | PASS |
| required | required.scrap_pct | BOMLine | rule | 1824 | 0 | PASS |
| range | min.scrap_pct | BOMLine | rule | 1824 | 0 | PASS |
| range | max.scrap_pct | BOMLine | rule | 1824 | 0 | PASS |
| schema | schema.columns_match | WorkCenter | rule | 4 | 0 | PASS |
| primary_key | pk.unique | WorkCenter | rule | 12 | 0 | PASS |
| required | required.work_center_id | WorkCenter | rule | 12 | 0 | PASS |
| id_pattern | pattern.work_center_id | WorkCenter | rule | 12 | 0 | PASS |
| required | required.location_id | WorkCenter | rule | 12 | 0 | PASS |
| foreign_key | fk.location_id->Location.location_id | WorkCenter | rule | 12 | 0 | PASS |
| required | required.work_center_name | WorkCenter | rule | 12 | 0 | PASS |
| required | required.status | WorkCenter | rule | 12 | 0 | PASS |
| enum | enum.status | WorkCenter | rule | 12 | 0 | PASS |
| schema | schema.columns_match | ProductionCapacity | rule | 5 | 0 | PASS |
| primary_key | pk.unique | ProductionCapacity | rule | 624 | 0 | PASS |
| required | required.prod_capacity_id | ProductionCapacity | rule | 624 | 0 | PASS |
| id_pattern | pattern.prod_capacity_id | ProductionCapacity | rule | 624 | 0 | PASS |
| required | required.work_center_id | ProductionCapacity | rule | 624 | 0 | PASS |
| foreign_key | fk.work_center_id->WorkCenter.work_center_id | ProductionCapacity | rule | 624 | 0 | PASS |
| required | required.iso_week | ProductionCapacity | rule | 624 | 0 | PASS |
| format | pattern.iso_week | ProductionCapacity | rule | 624 | 0 | PASS |
| required | required.week_start_date | ProductionCapacity | rule | 624 | 0 | PASS |
| format | pattern.week_start_date | ProductionCapacity | rule | 624 | 0 | PASS |
| required | required.available_hours | ProductionCapacity | rule | 624 | 0 | PASS |
| range | min.available_hours | ProductionCapacity | rule | 624 | 0 | PASS |
| schema | schema.columns_match | ForecastDemand | rule | 8 | 0 | PASS |
| primary_key | pk.unique | ForecastDemand | rule | 764400 | 0 | PASS |
| required | required.demand_id | ForecastDemand | rule | 764400 | 0 | PASS |
| id_pattern | pattern.demand_id | ForecastDemand | rule | 764400 | 0 | PASS |
| required | required.sku_id | ForecastDemand | rule | 764400 | 0 | PASS |
| foreign_key | fk.sku_id->SKU.sku_id | ForecastDemand | rule | 764400 | 0 | PASS |
| required | required.location_id | ForecastDemand | rule | 764400 | 0 | PASS |
| foreign_key | fk.location_id->Location.location_id | ForecastDemand | rule | 764400 | 0 | PASS |
| required | required.iso_week | ForecastDemand | rule | 764400 | 0 | PASS |
| format | pattern.iso_week | ForecastDemand | rule | 764400 | 0 | PASS |
| required | required.week_start_date | ForecastDemand | rule | 764400 | 0 | PASS |
| format | pattern.week_start_date | ForecastDemand | rule | 764400 | 0 | PASS |
| required | required.forecast_qty | ForecastDemand | rule | 764400 | 0 | PASS |
| range | min.forecast_qty | ForecastDemand | rule | 764400 | 0 | PASS |
| required | required.demand_driver | ForecastDemand | rule | 764400 | 0 | PASS |
| enum | enum.demand_driver | ForecastDemand | rule | 764400 | 0 | PASS |
| required | required.forecast_stdev | ForecastDemand | rule | 764400 | 0 | PASS |
| range | min.forecast_stdev | ForecastDemand | rule | 764400 | 0 | PASS |
| schema | schema.columns_match | Inventory | rule | 10 | 0 | PASS |
| primary_key | pk.unique | Inventory | rule | 14700 | 0 | PASS |
| required | required.inventory_id | Inventory | rule | 14700 | 0 | PASS |
| id_pattern | pattern.inventory_id | Inventory | rule | 14700 | 0 | PASS |
| required | required.sku_id | Inventory | rule | 14700 | 0 | PASS |
| foreign_key | fk.sku_id->SKU.sku_id | Inventory | rule | 14700 | 0 | PASS |
| required | required.location_id | Inventory | rule | 14700 | 0 | PASS |
| foreign_key | fk.location_id->Location.location_id | Inventory | rule | 14700 | 0 | PASS |
| required | required.as_of_date | Inventory | rule | 14700 | 0 | PASS |
| format | pattern.as_of_date | Inventory | rule | 14700 | 0 | PASS |
| required | required.on_hand_qty | Inventory | rule | 14700 | 0 | PASS |
| range | min.on_hand_qty | Inventory | rule | 14700 | 0 | PASS |
| required | required.allocated_qty | Inventory | rule | 14700 | 0 | PASS |
| range | min.allocated_qty | Inventory | rule | 14700 | 0 | PASS |
| required | required.quality_hold_qty | Inventory | rule | 14700 | 0 | PASS |
| range | min.quality_hold_qty | Inventory | rule | 14700 | 0 | PASS |
| required | required.safety_stock_qty | Inventory | rule | 14700 | 0 | PASS |
| range | min.safety_stock_qty | Inventory | rule | 14700 | 0 | PASS |
| required | required.available_qty | Inventory | rule | 14700 | 0 | PASS |
| required | required.inventory_status | Inventory | rule | 14700 | 0 | PASS |
| enum | enum.inventory_status | Inventory | rule | 14700 | 0 | PASS |
| schema | schema.columns_match | SupplierCapacity | rule | 10 | 0 | PASS |
| primary_key | pk.unique | SupplierCapacity | rule | 1066 | 0 | PASS |
| required | required.capacity_id | SupplierCapacity | rule | 1066 | 0 | PASS |
| id_pattern | pattern.capacity_id | SupplierCapacity | rule | 1066 | 0 | PASS |
| required | required.supplier_id | SupplierCapacity | rule | 1066 | 0 | PASS |
| foreign_key | fk.supplier_id->Supplier.supplier_id | SupplierCapacity | rule | 1066 | 0 | PASS |
| required | required.product_family | SupplierCapacity | rule | 1066 | 0 | PASS |
| format | pattern.product_family | SupplierCapacity | rule | 1066 | 0 | PASS |
| required | required.weekly_capacity_qty | SupplierCapacity | rule | 1066 | 0 | PASS |
| range | min.weekly_capacity_qty | SupplierCapacity | rule | 1066 | 0 | PASS |
| required | required.min_order_qty | SupplierCapacity | rule | 1066 | 0 | PASS |
| range | min.min_order_qty | SupplierCapacity | rule | 1066 | 0 | PASS |
| required | required.order_multiple | SupplierCapacity | rule | 1066 | 0 | PASS |
| range | min.order_multiple | SupplierCapacity | rule | 1066 | 0 | PASS |
| required | required.capacity_uom | SupplierCapacity | rule | 1066 | 0 | PASS |
| enum | enum.capacity_uom | SupplierCapacity | rule | 1066 | 0 | PASS |
| required | required.status | SupplierCapacity | rule | 1066 | 0 | PASS |
| enum | enum.status | SupplierCapacity | rule | 1066 | 0 | PASS |
| required | required.effective_from | SupplierCapacity | rule | 1066 | 0 | PASS |
| format | pattern.effective_from | SupplierCapacity | rule | 1066 | 0 | PASS |
| format | pattern.effective_to | SupplierCapacity | rule | 31 | 0 | PASS |
| schema | schema.columns_match | LeadTime | rule | 11 | 0 | PASS |
| primary_key | pk.unique | LeadTime | rule | 4453 | 0 | PASS |
| required | required.lead_time_id | LeadTime | rule | 4453 | 0 | PASS |
| id_pattern | pattern.lead_time_id | LeadTime | rule | 4453 | 0 | PASS |
| required | required.supplier_id | LeadTime | rule | 4453 | 0 | PASS |
| foreign_key | fk.supplier_id->Supplier.supplier_id | LeadTime | rule | 4453 | 0 | PASS |
| required | required.sku_id | LeadTime | rule | 4453 | 0 | PASS |
| foreign_key | fk.sku_id->SKU.sku_id | LeadTime | rule | 4453 | 0 | PASS |
| foreign_key | fk.ship_to_location_id->Location.location_id | LeadTime | rule | 212 | 0 | PASS |
| required | required.production_days | LeadTime | rule | 4453 | 0 | PASS |
| range | min.production_days | LeadTime | rule | 4453 | 0 | PASS |
| required | required.transit_days | LeadTime | rule | 4453 | 0 | PASS |
| range | min.transit_days | LeadTime | rule | 4453 | 0 | PASS |
| required | required.total_lead_days | LeadTime | rule | 4453 | 0 | PASS |
| range | min.total_lead_days | LeadTime | rule | 4453 | 0 | PASS |
| required | required.p90_lead_days | LeadTime | rule | 4453 | 0 | PASS |
| range | min.p90_lead_days | LeadTime | rule | 4453 | 0 | PASS |
| required | required.transport_mode | LeadTime | rule | 4453 | 0 | PASS |
| enum | enum.transport_mode | LeadTime | rule | 4453 | 0 | PASS |
| required | required.effective_from | LeadTime | rule | 4453 | 0 | PASS |
| format | pattern.effective_from | LeadTime | rule | 4453 | 0 | PASS |
| format | pattern.effective_to | LeadTime | rule | 0 | 0 | PASS |
| schema | schema.columns_match | PurchaseOrder | rule | 18 | 0 | PASS |
| primary_key | pk.unique | PurchaseOrder | rule | 10000 | 0 | PASS |
| required | required.po_id | PurchaseOrder | rule | 10000 | 0 | PASS |
| id_pattern | pattern.po_id | PurchaseOrder | rule | 10000 | 0 | PASS |
| required | required.supplier_id | PurchaseOrder | rule | 10000 | 0 | PASS |
| foreign_key | fk.supplier_id->Supplier.supplier_id | PurchaseOrder | rule | 10000 | 0 | PASS |
| required | required.sku_id | PurchaseOrder | rule | 10000 | 0 | PASS |
| foreign_key | fk.sku_id->SKU.sku_id | PurchaseOrder | rule | 10000 | 0 | PASS |
| required | required.ship_to_location_id | PurchaseOrder | rule | 10000 | 0 | PASS |
| foreign_key | fk.ship_to_location_id->Location.location_id | PurchaseOrder | rule | 10000 | 0 | PASS |
| foreign_key | fk.carrier_id->Carrier.carrier_id | PurchaseOrder | rule | 940 | 0 | PASS |
| required | required.created_date | PurchaseOrder | rule | 10000 | 0 | PASS |
| format | pattern.created_date | PurchaseOrder | rule | 10000 | 0 | PASS |
| required | required.order_date | PurchaseOrder | rule | 10000 | 0 | PASS |
| format | pattern.order_date | PurchaseOrder | rule | 10000 | 0 | PASS |
| required | required.requested_date | PurchaseOrder | rule | 10000 | 0 | PASS |
| format | pattern.requested_date | PurchaseOrder | rule | 10000 | 0 | PASS |
| required | required.promised_date | PurchaseOrder | rule | 10000 | 0 | PASS |
| format | pattern.promised_date | PurchaseOrder | rule | 10000 | 0 | PASS |
| required | required.eta_date | PurchaseOrder | rule | 10000 | 0 | PASS |
| format | pattern.eta_date | PurchaseOrder | rule | 10000 | 0 | PASS |
| format | pattern.actual_receipt_date | PurchaseOrder | rule | 600 | 0 | PASS |
| required | required.order_qty | PurchaseOrder | rule | 10000 | 0 | PASS |
| range | min.order_qty | PurchaseOrder | rule | 10000 | 0 | PASS |
| required | required.order_uom | PurchaseOrder | rule | 10000 | 0 | PASS |
| foreign_key | fk.order_uom->UnitOfMeasure.uom_code | PurchaseOrder | rule | 10000 | 0 | PASS |
| required | required.qty_base | PurchaseOrder | rule | 10000 | 0 | PASS |
| required | required.unit_price | PurchaseOrder | rule | 10000 | 0 | PASS |
| range | min.unit_price | PurchaseOrder | rule | 10000 | 0 | PASS |
| required | required.total_cost | PurchaseOrder | rule | 10000 | 0 | PASS |
| required | required.supplier_ref_no | PurchaseOrder | rule | 10000 | 0 | PASS |
| required | required.status | PurchaseOrder | rule | 10000 | 0 | PASS |
| enum | enum.status | PurchaseOrder | rule | 10000 | 0 | PASS |
| schema | schema.columns_match | ProductionPlan | rule | 10 | 0 | PASS |
| primary_key | pk.unique | ProductionPlan | rule | 35872 | 0 | PASS |
| required | required.production_plan_id | ProductionPlan | rule | 35872 | 0 | PASS |
| id_pattern | pattern.production_plan_id | ProductionPlan | rule | 35872 | 0 | PASS |
| required | required.sku_id | ProductionPlan | rule | 35872 | 0 | PASS |
| foreign_key | fk.sku_id->SKU.sku_id | ProductionPlan | rule | 35872 | 0 | PASS |
| required | required.location_id | ProductionPlan | rule | 35872 | 0 | PASS |
| foreign_key | fk.location_id->Location.location_id | ProductionPlan | rule | 35872 | 0 | PASS |
| required | required.work_center_id | ProductionPlan | rule | 35872 | 0 | PASS |
| foreign_key | fk.work_center_id->WorkCenter.work_center_id | ProductionPlan | rule | 35872 | 0 | PASS |
| required | required.bom_id | ProductionPlan | rule | 35872 | 0 | PASS |
| foreign_key | fk.bom_id->BillOfMaterial.bom_id | ProductionPlan | rule | 35872 | 0 | PASS |
| required | required.iso_week | ProductionPlan | rule | 35872 | 0 | PASS |
| format | pattern.iso_week | ProductionPlan | rule | 35872 | 0 | PASS |
| required | required.week_start_date | ProductionPlan | rule | 35872 | 0 | PASS |
| format | pattern.week_start_date | ProductionPlan | rule | 35872 | 0 | PASS |
| required | required.planned_qty | ProductionPlan | rule | 35872 | 0 | PASS |
| range | min.planned_qty | ProductionPlan | rule | 35872 | 0 | PASS |
| required | required.required_hours | ProductionPlan | rule | 35872 | 0 | PASS |
| required | required.status | ProductionPlan | rule | 35872 | 0 | PASS |
| enum | enum.status | ProductionPlan | rule | 35872 | 0 | PASS |
| schema | schema.columns_match | PurchaseOrderEvent | rule | 9 | 0 | PASS |
| primary_key | pk.unique | PurchaseOrderEvent | rule | 14344 | 0 | PASS |
| required | required.event_id | PurchaseOrderEvent | rule | 14344 | 0 | PASS |
| id_pattern | pattern.event_id | PurchaseOrderEvent | rule | 14344 | 0 | PASS |
| required | required.po_id | PurchaseOrderEvent | rule | 14344 | 0 | PASS |
| foreign_key | fk.po_id->PurchaseOrder.po_id | PurchaseOrderEvent | rule | 14344 | 0 | PASS |
| required | required.event_type | PurchaseOrderEvent | rule | 14344 | 0 | PASS |
| enum | enum.event_type | PurchaseOrderEvent | rule | 14344 | 0 | PASS |
| enum | enum.from_status | PurchaseOrderEvent | rule | 4344 | 0 | PASS |
| required | required.to_status | PurchaseOrderEvent | rule | 14344 | 0 | PASS |
| enum | enum.to_status | PurchaseOrderEvent | rule | 14344 | 0 | PASS |
| required | required.event_date | PurchaseOrderEvent | rule | 14344 | 0 | PASS |
| format | pattern.event_date | PurchaseOrderEvent | rule | 14344 | 0 | PASS |
| required | required.actor_role | PurchaseOrderEvent | rule | 14344 | 0 | PASS |
| enum | enum.actor_role | PurchaseOrderEvent | rule | 14344 | 0 | PASS |
| range | min.delay_days | PurchaseOrderEvent | rule | 178 | 0 | PASS |
| schema | schema.columns_match | TransportEvent | rule | 8 | 0 | PASS |
| primary_key | pk.unique | TransportEvent | rule | 1718 | 0 | PASS |
| required | required.event_id | TransportEvent | rule | 1718 | 0 | PASS |
| id_pattern | pattern.event_id | TransportEvent | rule | 1718 | 0 | PASS |
| required | required.po_id | TransportEvent | rule | 1718 | 0 | PASS |
| foreign_key | fk.po_id->PurchaseOrder.po_id | TransportEvent | rule | 1718 | 0 | PASS |
| required | required.carrier_id | TransportEvent | rule | 1718 | 0 | PASS |
| foreign_key | fk.carrier_id->Carrier.carrier_id | TransportEvent | rule | 1718 | 0 | PASS |
| required | required.event_type | TransportEvent | rule | 1718 | 0 | PASS |
| enum | enum.event_type | TransportEvent | rule | 1718 | 0 | PASS |
| required | required.event_date | TransportEvent | rule | 1718 | 0 | PASS |
| format | pattern.event_date | TransportEvent | rule | 1718 | 0 | PASS |
| range | min.delay_days | TransportEvent | rule | 178 | 0 | PASS |
| enum | enum.reason_code | TransportEvent | rule | 178 | 0 | PASS |
| required | required.actor_role | TransportEvent | rule | 1718 | 0 | PASS |
| enum | enum.actor_role | TransportEvent | rule | 1718 | 0 | PASS |
| schema | schema.columns_match | InventoryEvent | rule | 8 | 0 | PASS |
| primary_key | pk.unique | InventoryEvent | rule | 600 | 0 | PASS |
| required | required.event_id | InventoryEvent | rule | 600 | 0 | PASS |
| id_pattern | pattern.event_id | InventoryEvent | rule | 600 | 0 | PASS |
| required | required.sku_id | InventoryEvent | rule | 600 | 0 | PASS |
| foreign_key | fk.sku_id->SKU.sku_id | InventoryEvent | rule | 600 | 0 | PASS |
| required | required.location_id | InventoryEvent | rule | 600 | 0 | PASS |
| foreign_key | fk.location_id->Location.location_id | InventoryEvent | rule | 600 | 0 | PASS |
| required | required.event_type | InventoryEvent | rule | 600 | 0 | PASS |
| enum | enum.event_type | InventoryEvent | rule | 600 | 0 | PASS |
| required | required.qty | InventoryEvent | rule | 600 | 0 | PASS |
| required | required.event_date | InventoryEvent | rule | 600 | 0 | PASS |
| format | pattern.event_date | InventoryEvent | rule | 600 | 0 | PASS |
| foreign_key | fk.po_id->PurchaseOrder.po_id | InventoryEvent | rule | 600 | 0 | PASS |
| required | required.actor_role | InventoryEvent | rule | 600 | 0 | PASS |
| enum | enum.actor_role | InventoryEvent | rule | 600 | 0 | PASS |
| schema | schema.columns_match | ProductionPlanEvent | rule | 6 | 0 | PASS |
| primary_key | pk.unique | ProductionPlanEvent | rule | 42121 | 0 | PASS |
| required | required.event_id | ProductionPlanEvent | rule | 42121 | 0 | PASS |
| id_pattern | pattern.event_id | ProductionPlanEvent | rule | 42121 | 0 | PASS |
| required | required.production_plan_id | ProductionPlanEvent | rule | 42121 | 0 | PASS |
| foreign_key | fk.production_plan_id->ProductionPlan.production_plan_id | ProductionPlanEvent | rule | 42121 | 0 | PASS |
| enum | enum.from_status | ProductionPlanEvent | rule | 6249 | 0 | PASS |
| required | required.to_status | ProductionPlanEvent | rule | 42121 | 0 | PASS |
| enum | enum.to_status | ProductionPlanEvent | rule | 42121 | 0 | PASS |
| required | required.event_date | ProductionPlanEvent | rule | 42121 | 0 | PASS |
| format | pattern.event_date | ProductionPlanEvent | rule | 42121 | 0 | PASS |
| required | required.actor_role | ProductionPlanEvent | rule | 42121 | 0 | PASS |
| enum | enum.actor_role | ProductionPlanEvent | rule | 42121 | 0 | PASS |
| schema | schema.columns_match | PlanRun | rule | 8 | 0 | PASS |
| primary_key | pk.unique | PlanRun | rule | 1 | 0 | PASS |
| required | required.run_id | PlanRun | rule | 1 | 0 | PASS |
| id_pattern | pattern.run_id | PlanRun | rule | 1 | 0 | PASS |
| required | required.as_of_date | PlanRun | rule | 1 | 0 | PASS |
| format | pattern.as_of_date | PlanRun | rule | 1 | 0 | PASS |
| required | required.seed | PlanRun | rule | 1 | 0 | PASS |
| required | required.profile | PlanRun | rule | 1 | 0 | PASS |
| required | required.engine_version | PlanRun | rule | 1 | 0 | PASS |
| required | required.policy_hash | PlanRun | rule | 1 | 0 | PASS |
| required | required.n_pairs | PlanRun | rule | 1 | 0 | PASS |
| range | min.n_pairs | PlanRun | rule | 1 | 0 | PASS |
| required | required.n_shortages | PlanRun | rule | 1 | 0 | PASS |
| range | min.n_shortages | PlanRun | rule | 1 | 0 | PASS |
| schema | schema.columns_match | ProjectedBalance | rule | 13 | 0 | PASS |
| primary_key | pk.unique | ProjectedBalance | rule | 764400 | 0 | PASS |
| required | required.run_id | ProjectedBalance | rule | 764400 | 0 | PASS |
| foreign_key | fk.run_id->PlanRun.run_id | ProjectedBalance | rule | 764400 | 0 | PASS |
| required | required.sku_id | ProjectedBalance | rule | 764400 | 0 | PASS |
| foreign_key | fk.sku_id->SKU.sku_id | ProjectedBalance | rule | 764400 | 0 | PASS |
| required | required.location_id | ProjectedBalance | rule | 764400 | 0 | PASS |
| foreign_key | fk.location_id->Location.location_id | ProjectedBalance | rule | 764400 | 0 | PASS |
| required | required.iso_week | ProjectedBalance | rule | 764400 | 0 | PASS |
| format | pattern.iso_week | ProjectedBalance | rule | 764400 | 0 | PASS |
| required | required.week_start_date | ProjectedBalance | rule | 764400 | 0 | PASS |
| format | pattern.week_start_date | ProjectedBalance | rule | 764400 | 0 | PASS |
| required | required.opening_qty | ProjectedBalance | rule | 764400 | 0 | PASS |
| required | required.gross_demand_qty | ProjectedBalance | rule | 764400 | 0 | PASS |
| range | min.gross_demand_qty | ProjectedBalance | rule | 764400 | 0 | PASS |
| required | required.dependent_demand_qty | ProjectedBalance | rule | 764400 | 0 | PASS |
| range | min.dependent_demand_qty | ProjectedBalance | rule | 764400 | 0 | PASS |
| required | required.scheduled_receipts_qty | ProjectedBalance | rule | 764400 | 0 | PASS |
| range | min.scheduled_receipts_qty | ProjectedBalance | rule | 764400 | 0 | PASS |
| required | required.production_receipts_qty | ProjectedBalance | rule | 764400 | 0 | PASS |
| range | min.production_receipts_qty | ProjectedBalance | rule | 764400 | 0 | PASS |
| required | required.closing_qty | ProjectedBalance | rule | 764400 | 0 | PASS |
| required | required.safety_stock_qty | ProjectedBalance | rule | 764400 | 0 | PASS |
| range | min.safety_stock_qty | ProjectedBalance | rule | 764400 | 0 | PASS |
| required | required.shortfall_qty | ProjectedBalance | rule | 764400 | 0 | PASS |
| range | min.shortfall_qty | ProjectedBalance | rule | 764400 | 0 | PASS |
| schema | schema.columns_match | SupplierCapacityLedger | rule | 10 | 0 | PASS |
| primary_key | pk.unique | SupplierCapacityLedger | rule | 8266 | 0 | PASS |
| required | required.run_id | SupplierCapacityLedger | rule | 8266 | 0 | PASS |
| foreign_key | fk.run_id->PlanRun.run_id | SupplierCapacityLedger | rule | 8266 | 0 | PASS |
| required | required.supplier_id | SupplierCapacityLedger | rule | 8266 | 0 | PASS |
| foreign_key | fk.supplier_id->Supplier.supplier_id | SupplierCapacityLedger | rule | 8266 | 0 | PASS |
| required | required.product_family | SupplierCapacityLedger | rule | 8266 | 0 | PASS |
| format | pattern.product_family | SupplierCapacityLedger | rule | 8266 | 0 | PASS |
| required | required.week_start_date | SupplierCapacityLedger | rule | 8266 | 0 | PASS |
| format | pattern.week_start_date | SupplierCapacityLedger | rule | 8266 | 0 | PASS |
| required | required.iso_week | SupplierCapacityLedger | rule | 8266 | 0 | PASS |
| required | required.committed_qty | SupplierCapacityLedger | rule | 8266 | 0 | PASS |
| range | min.committed_qty | SupplierCapacityLedger | rule | 8266 | 0 | PASS |
| required | required.capacity_qty | SupplierCapacityLedger | rule | 8266 | 0 | PASS |
| range | min.capacity_qty | SupplierCapacityLedger | rule | 8266 | 0 | PASS |
| required | required.utilisation_pct | SupplierCapacityLedger | rule | 8266 | 0 | PASS |
| range | min.utilisation_pct | SupplierCapacityLedger | rule | 8266 | 0 | PASS |
| required | required.remaining_qty | SupplierCapacityLedger | rule | 8266 | 0 | PASS |
| range | min.remaining_qty | SupplierCapacityLedger | rule | 8266 | 0 | PASS |
| required | required.status | SupplierCapacityLedger | rule | 8266 | 0 | PASS |
| enum | enum.status | SupplierCapacityLedger | rule | 8266 | 0 | PASS |
| schema | schema.columns_match | Shortage | rule | 17 | 0 | PASS |
| primary_key | pk.unique | Shortage | rule | 1600 | 0 | PASS |
| required | required.shortage_id | Shortage | rule | 1600 | 0 | PASS |
| id_pattern | pattern.shortage_id | Shortage | rule | 1600 | 0 | PASS |
| required | required.run_id | Shortage | rule | 1600 | 0 | PASS |
| foreign_key | fk.run_id->PlanRun.run_id | Shortage | rule | 1600 | 0 | PASS |
| required | required.sku_id | Shortage | rule | 1600 | 0 | PASS |
| foreign_key | fk.sku_id->SKU.sku_id | Shortage | rule | 1600 | 0 | PASS |
| required | required.location_id | Shortage | rule | 1600 | 0 | PASS |
| foreign_key | fk.location_id->Location.location_id | Shortage | rule | 1600 | 0 | PASS |
| required | required.first_short_week | Shortage | rule | 1600 | 0 | PASS |
| format | pattern.first_short_week | Shortage | rule | 1600 | 0 | PASS |
| required | required.last_short_week | Shortage | rule | 1600 | 0 | PASS |
| format | pattern.last_short_week | Shortage | rule | 1600 | 0 | PASS |
| required | required.peak_short_week | Shortage | rule | 1600 | 0 | PASS |
| format | pattern.peak_short_week | Shortage | rule | 1600 | 0 | PASS |
| required | required.need_by_date | Shortage | rule | 1600 | 0 | PASS |
| format | pattern.need_by_date | Shortage | rule | 1600 | 0 | PASS |
| required | required.episode_weeks | Shortage | rule | 1600 | 0 | PASS |
| range | min.episode_weeks | Shortage | rule | 1600 | 0 | PASS |
| required | required.shortage_type | Shortage | rule | 1600 | 0 | PASS |
| enum | enum.shortage_type | Shortage | rule | 1600 | 0 | PASS |
| required | required.shortage_qty | Shortage | rule | 1600 | 0 | PASS |
| range | min.shortage_qty | Shortage | rule | 1600 | 0 | PASS |
| required | required.value_at_risk | Shortage | rule | 1600 | 0 | PASS |
| required | required.priority_score | Shortage | rule | 1600 | 0 | PASS |
| required | required.priority_rank | Shortage | rule | 1600 | 0 | PASS |
| range | min.priority_rank | Shortage | rule | 1600 | 0 | PASS |
| required | required.primary_cause_code | Shortage | rule | 1600 | 0 | PASS |
| enum | enum.primary_cause_code | Shortage | rule | 1600 | 0 | PASS |
| required | required.data_quality_flag | Shortage | rule | 1600 | 0 | PASS |
| enum | enum.data_quality_flag | Shortage | rule | 1600 | 0 | PASS |
| required | required.status | Shortage | rule | 1600 | 0 | PASS |
| enum | enum.status | Shortage | rule | 1600 | 0 | PASS |
| schema | schema.columns_match | ShortageCause | rule | 7 | 0 | PASS |
| primary_key | pk.unique | ShortageCause | rule | 1742 | 0 | PASS |
| required | required.shortage_id | ShortageCause | rule | 1742 | 0 | PASS |
| foreign_key | fk.shortage_id->Shortage.shortage_id | ShortageCause | rule | 1742 | 0 | PASS |
| required | required.cause_seq | ShortageCause | rule | 1742 | 0 | PASS |
| range | min.cause_seq | ShortageCause | rule | 1742 | 0 | PASS |
| required | required.cause_code | ShortageCause | rule | 1742 | 0 | PASS |
| enum | enum.cause_code | ShortageCause | rule | 1742 | 0 | PASS |
| required | required.contribution_qty | ShortageCause | rule | 1742 | 0 | PASS |
| range | min.contribution_qty | ShortageCause | rule | 1742 | 0 | PASS |
| required | required.source_table | ShortageCause | rule | 1742 | 0 | PASS |
| required | required.source_id | ShortageCause | rule | 1742 | 0 | PASS |
| required | required.explanation | ShortageCause | rule | 1742 | 0 | PASS |
| schema | schema.columns_match | MitigationOption | rule | 31 | 0 | PASS |
| primary_key | pk.unique | MitigationOption | rule | 7135 | 0 | PASS |
| required | required.mitigation_id | MitigationOption | rule | 7135 | 0 | PASS |
| id_pattern | pattern.mitigation_id | MitigationOption | rule | 7135 | 0 | PASS |
| required | required.shortage_id | MitigationOption | rule | 7135 | 0 | PASS |
| foreign_key | fk.shortage_id->Shortage.shortage_id | MitigationOption | rule | 7135 | 0 | PASS |
| required | required.option_type | MitigationOption | rule | 7135 | 0 | PASS |
| enum | enum.option_type | MitigationOption | rule | 7135 | 0 | PASS |
| foreign_key | fk.supplier_id->Supplier.supplier_id | MitigationOption | rule | 2204 | 0 | PASS |
| foreign_key | fk.alt_sku_id->SKU.sku_id | MitigationOption | rule | 197 | 0 | PASS |
| foreign_key | fk.source_location_id->Location.location_id | MitigationOption | rule | 2653 | 0 | PASS |
| foreign_key | fk.ref_po_id->PurchaseOrder.po_id | MitigationOption | rule | 166 | 0 | PASS |
| foreign_key | fk.production_plan_id->ProductionPlan.production_plan_id | MitigationOption | rule | 28 | 0 | PASS |
| required | required.qty | MitigationOption | rule | 7135 | 0 | PASS |
| range | min.qty | MitigationOption | rule | 7135 | 0 | PASS |
| required | required.covered_qty | MitigationOption | rule | 7135 | 0 | PASS |
| range | min.covered_qty | MitigationOption | rule | 7135 | 0 | PASS |
| required | required.unit_cost | MitigationOption | rule | 7135 | 0 | PASS |
| range | min.unit_cost | MitigationOption | rule | 7135 | 0 | PASS |
| required | required.expedite_premium | MitigationOption | rule | 7135 | 0 | PASS |
| range | min.expedite_premium | MitigationOption | rule | 7135 | 0 | PASS |
| required | required.freight_cost | MitigationOption | rule | 7135 | 0 | PASS |
| range | min.freight_cost | MitigationOption | rule | 7135 | 0 | PASS |
| required | required.excess_cost | MitigationOption | rule | 7135 | 0 | PASS |
| range | min.excess_cost | MitigationOption | rule | 7135 | 0 | PASS |
| required | required.penalty_cost | MitigationOption | rule | 7135 | 0 | PASS |
| range | min.penalty_cost | MitigationOption | rule | 7135 | 0 | PASS |
| required | required.total_cost | MitigationOption | rule | 7135 | 0 | PASS |
| required | required.cost_delta_vs_baseline | MitigationOption | rule | 7135 | 0 | PASS |
| range | min.lead_days | MitigationOption | rule | 5321 | 0 | PASS |
| format | pattern.earliest_arrival_date | MitigationOption | rule | 5321 | 0 | PASS |
| range | min.weeks_late | MitigationOption | rule | 7135 | 0 | PASS |
| required | required.fill_rate_pct | MitigationOption | rule | 7135 | 0 | PASS |
| range | min.fill_rate_pct | MitigationOption | rule | 7135 | 0 | PASS |
| range | max.fill_rate_pct | MitigationOption | rule | 7135 | 0 | PASS |
| range | min.capacity_available_qty | MitigationOption | rule | 5444 | 0 | PASS |
| required | required.capacity_check | MitigationOption | rule | 7135 | 0 | PASS |
| enum | enum.capacity_check | MitigationOption | rule | 7135 | 0 | PASS |
| required | required.policy_check | MitigationOption | rule | 7135 | 0 | PASS |
| enum | enum.policy_check | MitigationOption | rule | 7135 | 0 | PASS |
| required | required.lead_time_check | MitigationOption | rule | 7135 | 0 | PASS |
| enum | enum.lead_time_check | MitigationOption | rule | 7135 | 0 | PASS |
| required | required.approval_required_role | MitigationOption | rule | 7135 | 0 | PASS |
| enum | enum.approval_required_role | MitigationOption | rule | 7135 | 0 | PASS |
| required | required.is_recommendable | MitigationOption | rule | 7135 | 0 | PASS |
| enum | enum.is_recommendable | MitigationOption | rule | 7135 | 0 | PASS |
| required | required.rank | MitigationOption | rule | 7135 | 0 | PASS |
| range | min.rank | MitigationOption | rule | 7135 | 0 | PASS |
| required | required.is_recommended | MitigationOption | rule | 7135 | 0 | PASS |
| enum | enum.is_recommended | MitigationOption | rule | 7135 | 0 | PASS |
| required | required.status | MitigationOption | rule | 7135 | 0 | PASS |
| enum | enum.status | MitigationOption | rule | 7135 | 0 | PASS |
| schema | schema.columns_match | ShortageEvent | rule | 7 | 0 | PASS |
| primary_key | pk.unique | ShortageEvent | rule | 4800 | 0 | PASS |
| required | required.event_id | ShortageEvent | rule | 4800 | 0 | PASS |
| id_pattern | pattern.event_id | ShortageEvent | rule | 4800 | 0 | PASS |
| required | required.shortage_id | ShortageEvent | rule | 4800 | 0 | PASS |
| foreign_key | fk.shortage_id->Shortage.shortage_id | ShortageEvent | rule | 4800 | 0 | PASS |
| enum | enum.from_status | ShortageEvent | rule | 3200 | 0 | PASS |
| required | required.to_status | ShortageEvent | rule | 4800 | 0 | PASS |
| enum | enum.to_status | ShortageEvent | rule | 4800 | 0 | PASS |
| required | required.event_date | ShortageEvent | rule | 4800 | 0 | PASS |
| format | pattern.event_date | ShortageEvent | rule | 4800 | 0 | PASS |
| required | required.actor_role | ShortageEvent | rule | 4800 | 0 | PASS |
| enum | enum.actor_role | ShortageEvent | rule | 4800 | 0 | PASS |
| schema | schema.columns_match | MitigationEvent | rule | 7 | 0 | PASS |
| primary_key | pk.unique | MitigationEvent | rule | 7494 | 0 | PASS |
| required | required.event_id | MitigationEvent | rule | 7494 | 0 | PASS |
| id_pattern | pattern.event_id | MitigationEvent | rule | 7494 | 0 | PASS |
| required | required.mitigation_id | MitigationEvent | rule | 7494 | 0 | PASS |
| foreign_key | fk.mitigation_id->MitigationOption.mitigation_id | MitigationEvent | rule | 7494 | 0 | PASS |
| enum | enum.from_status | MitigationEvent | rule | 359 | 0 | PASS |
| required | required.to_status | MitigationEvent | rule | 7494 | 0 | PASS |
| enum | enum.to_status | MitigationEvent | rule | 7494 | 0 | PASS |
| required | required.event_date | MitigationEvent | rule | 7494 | 0 | PASS |
| format | pattern.event_date | MitigationEvent | rule | 7494 | 0 | PASS |
| required | required.actor_role | MitigationEvent | rule | 7494 | 0 | PASS |
| enum | enum.actor_role | MitigationEvent | rule | 7494 | 0 | PASS |
| schema | schema.columns_match | DataQualityFinding | rule | 8 | 0 | PASS |
| primary_key | pk.unique | DataQualityFinding | rule | 195 | 0 | PASS |
| required | required.finding_id | DataQualityFinding | rule | 195 | 0 | PASS |
| id_pattern | pattern.finding_id | DataQualityFinding | rule | 195 | 0 | PASS |
| required | required.run_id | DataQualityFinding | rule | 195 | 0 | PASS |
| foreign_key | fk.run_id->PlanRun.run_id | DataQualityFinding | rule | 195 | 0 | PASS |
| required | required.issue_type | DataQualityFinding | rule | 195 | 0 | PASS |
| enum | enum.issue_type | DataQualityFinding | rule | 195 | 0 | PASS |
| required | required.entity | DataQualityFinding | rule | 195 | 0 | PASS |
| required | required.record_id | DataQualityFinding | rule | 195 | 0 | PASS |
| required | required.detail | DataQualityFinding | rule | 195 | 0 | PASS |
| id_pattern | id.demand_id_from_fks | ForecastDemand | rule | 764400 | 0 | PASS |
| id_pattern | id.inventory_id_from_fks | Inventory | rule | 14700 | 0 | PASS |
| date_order | id.iso_week_matches_date | ForecastDemand | rule | 764400 | 0 | PASS |
| id_pattern | id.mitigation_id_from_shortage | MitigationOption | rule | 7135 | 0 | PASS |
| coverage | coverage.active_pair_has_52_weeks | ForecastDemand | rule | 14700 | 0 | PASS |
| coverage | coverage.demand_only_for_active_pairs | ForecastDemand | rule | 14700 | 0 | PASS |
| coverage | coverage.inventory_pairs_equal_active_pairs | Inventory | rule | 14700 | 0 | PASS |
| coverage | coverage.every_sku_in_master_has_active_location | SKU | rule | 3000 | 0 | PASS |
| coverage | coverage.every_location_has_active_sku | Location | rule | 50 | 0 | PASS |
| coverage | coverage.inactive_pairs_have_no_demand | SKULocation | rule | 300 | 0 | PASS |
| volume | volume.sku_count | SKU | rule | 1 | 0 | PASS |
| volume | volume.location_count | Location | rule | 1 | 0 | PASS |
| volume | volume.supplier_count | Supplier | rule | 1 | 0 | PASS |
| volume | volume.purchase_order_count | PurchaseOrder | rule | 1 | 0 | PASS |
| volume | volume.demand_weeks | ForecastDemand | rule | 1 | 0 | PASS |
| foreign_key | fk.demand_pair_in_SKULocation | ForecastDemand | rule | 14700 | 0 | PASS |
| foreign_key | fk.PO_supplier_sku_in_SKUSupplier | PurchaseOrder | rule | 10000 | 0 | PASS |
| foreign_key | fk.PO_ship_to_pair_in_SKULocation | PurchaseOrder | rule | 10000 | 0 | PASS |
| foreign_key | fk.ProductionPlan_at_plant_for_make_sku | ProductionPlan | rule | 35872 | 0 | PASS |
| date_order | dates.effective_from_before_to | Location | rule | 50 | 0 | PASS |
| date_order | dates.effective_from_before_to | Supplier | rule | 500 | 0 | PASS |
| date_order | dates.effective_from_before_to | SKU | rule | 3000 | 0 | PASS |
| date_order | dates.effective_from_before_to | SKULocation | rule | 15000 | 0 | PASS |
| date_order | dates.effective_from_before_to | SKUSupplier | rule | 4301 | 0 | PASS |
| date_order | dates.effective_from_before_to | SKUSubstitute | rule | 383 | 0 | PASS |
| date_order | dates.effective_from_before_to | BillOfMaterial | rule | 600 | 0 | PASS |
| date_order | dates.effective_from_before_to | SupplierCapacity | rule | 1066 | 0 | PASS |
| date_order | dates.effective_from_before_to | LeadTime | rule | 4453 | 0 | PASS |
| date_order | dates.PO.created_date<=order_date | PurchaseOrder | rule | 10000 | 0 | PASS |
| date_order | dates.PO.order_date<=requested_date | PurchaseOrder | rule | 10000 | 0 | PASS |
| date_order | dates.PO.requested_date<=promised_date | PurchaseOrder | rule | 10000 | 0 | PASS |
| date_order | dates.PO.promised_date<=eta_date | PurchaseOrder | rule | 10000 | 0 | PASS |
| date_order | dates.PO.created<=as_of | PurchaseOrder | rule | 10000 | 0 | PASS |
| date_order | dates.PO.receipt_only_when_received_and_equals_eta | PurchaseOrder | rule | 10000 | 0 | PASS |
| date_order | dates.PO.received_before_as_of_open_not | PurchaseOrder | rule | 10000 | 0 | PASS |
| date_order | dates.PurchaseOrderEvent.not_after_as_of | PurchaseOrderEvent | rule | 14344 | 0 | PASS |
| date_order | dates.TransportEvent.not_after_as_of | TransportEvent | rule | 1718 | 0 | PASS |
| date_order | dates.InventoryEvent.not_after_as_of | InventoryEvent | rule | 600 | 0 | PASS |
| date_order | dates.ProductionPlanEvent.not_after_as_of | ProductionPlanEvent | rule | 42121 | 0 | PASS |
| range | dates.LeadTime.p90>=total | LeadTime | rule | 4453 | 0 | PASS |
| date_order | dates.SKUSubstitute.approved_date<=as_of | SKUSubstitute | rule | 383 | 0 | PASS |
| required | rules.SKUSubstitute.approved_has_role_and_date | SKUSubstitute | rule | 383 | 0 | PASS |
| range | rules.SKUSubstitute.not_self | SKUSubstitute | rule | 383 | 0 | PASS |
| range | rules.SKU.price>=cost | SKU | rule | 3000 | 0 | PASS |
| arithmetic | arith.Inventory.available | Inventory | rule | 14700 | 0 | PASS |
| arithmetic | arith.LeadTime.total | LeadTime | rule | 4453 | 0 | PASS |
| arithmetic | arith.PO.total_cost | PurchaseOrder | rule | 10000 | 0 | PASS |
| arithmetic | arith.PO.eta=promised+delays | PurchaseOrder | rule | 10000 | 0 | PASS |
| arithmetic | arith.ProductionPlan.required_hours | ProductionPlan | rule | 35872 | 0 | PASS |
| arithmetic | arith.ProductionPlan.multiple_of_lot | ProductionPlan | rule | 35872 | 0 | PASS |
| arithmetic | arith.PO.factor_exists_for_order_uom | PurchaseOrder | rule | 10000 | 0 | PASS |
| arithmetic | arith.PO.moq_and_multiple | PurchaseOrder | rule | 10000 | 0 | PASS |
| lifecycle | PurchaseOrderEvent.transitions_allowed | PurchaseOrderEvent | rule | 14344 | 0 | PASS |
| lifecycle | PurchaseOrderEvent.from_status_matches_previous | PurchaseOrderEvent | rule | 14344 | 0 | PASS |
| date_order | PurchaseOrderEvent.dates_non_decreasing | PurchaseOrderEvent | rule | 14344 | 0 | PASS |
| lifecycle | PurchaseOrderEvent.header_status_equals_last_event | PurchaseOrderEvent | rule | 10000 | 0 | PASS |
| lifecycle | PurchaseOrderEvent.every_entity_has_events | PurchaseOrderEvent | rule | 10000 | 0 | PASS |
| lifecycle | ProductionPlanEvent.transitions_allowed | ProductionPlanEvent | rule | 42121 | 0 | PASS |
| lifecycle | ProductionPlanEvent.from_status_matches_previous | ProductionPlanEvent | rule | 42121 | 0 | PASS |
| date_order | ProductionPlanEvent.dates_non_decreasing | ProductionPlanEvent | rule | 42121 | 0 | PASS |
| lifecycle | ProductionPlanEvent.header_status_equals_last_event | ProductionPlanEvent | rule | 35872 | 0 | PASS |
| lifecycle | ProductionPlanEvent.every_entity_has_events | ProductionPlanEvent | rule | 35872 | 0 | PASS |
| lifecycle | ShortageEvent.transitions_allowed | ShortageEvent | rule | 4800 | 0 | PASS |
| lifecycle | ShortageEvent.from_status_matches_previous | ShortageEvent | rule | 4800 | 0 | PASS |
| date_order | ShortageEvent.dates_non_decreasing | ShortageEvent | rule | 4800 | 0 | PASS |
| lifecycle | ShortageEvent.header_status_equals_last_event | ShortageEvent | rule | 1600 | 0 | PASS |
| lifecycle | ShortageEvent.every_entity_has_events | ShortageEvent | rule | 1600 | 0 | PASS |
| lifecycle | MitigationEvent.transitions_allowed | MitigationEvent | rule | 7494 | 0 | PASS |
| lifecycle | MitigationEvent.from_status_matches_previous | MitigationEvent | rule | 7494 | 0 | PASS |
| date_order | MitigationEvent.dates_non_decreasing | MitigationEvent | rule | 7494 | 0 | PASS |
| lifecycle | MitigationEvent.header_status_equals_last_event | MitigationEvent | rule | 7135 | 0 | PASS |
| lifecycle | MitigationEvent.every_entity_has_events | MitigationEvent | rule | 7135 | 0 | PASS |
| lifecycle | lifecycle.TransportEvent.delay_matches_PO_event | TransportEvent | rule | 1718 | 0 | PASS |
| duplicate | dup.ForecastDemand.sku_loc_week | ForecastDemand | rule | 764400 | 0 | PASS |
| duplicate | dup.LeadTime.supplier_sku_loc_from | LeadTime | rule | 4453 | 0 | PASS |
| duplicate | dup.SupplierCapacity.supplier_family_from | SupplierCapacity | rule | 1066 | 0 | PASS |
| edge_case | dq.duplicate_po | PurchaseOrder | labelled | 10000 | 45 | LABELLED |
| edge_case | dq.uom_arithmetic | PurchaseOrder | labelled | 10000 | 30 | LABELLED |
| edge_case | dq.capacity_ledger | SupplierCapacityLedger | labelled | 8266 | 30 | LABELLED |
| edge_case | dq.lead_time_defined | LeadTime | labelled | 4301 | 60 | LABELLED |
| edge_case | dq.substitute_approved | SKUSubstitute | labelled | 383 | 30 | LABELLED |
| acceptance | accept.PAB_identity_each_week | ProjectedBalance | rule | 764400 | 0 | PASS |
| acceptance | accept.PAB_opening_equals_previous_closing | ProjectedBalance | rule | 764400 | 0 | PASS |
| acceptance | accept.PAB_week1_opening_equals_inventory_available | ProjectedBalance | rule | 14700 | 0 | PASS |
| acceptance | accept.PAB_gross_demand_equals_forecast | ProjectedBalance | rule | 14700 | 0 | PASS |
| acceptance | accept.PAB_receipts_equal_open_PO_quantities | ProjectedBalance | rule | 14700 | 0 | PASS |
| arithmetic | arith.Shortage.value_at_risk | Shortage | rule | 1600 | 0 | PASS |
| arithmetic | arith.Shortage.qty=safety-closing_at_peak | Shortage | rule | 1600 | 0 | PASS |
| acceptance | accept.every_shortage_has_a_cause | Shortage | rule | 1600 | 0 | PASS |
| acceptance | accept.causes_reconcile_to_shortage_qty | ShortageCause | rule | 1600 | 0 | PASS |
| acceptance | accept.cause_has_source_record | ShortageCause | rule | 1742 | 0 | PASS |
| foreign_key | accept.cause_source_ids_exist | ShortageCause | rule | 1742 | 0 | PASS |
| arithmetic | arith.Shortage.primary_cause=largest_contribution | Shortage | rule | 1600 | 0 | PASS |
| acceptance | accept.at_least_2_alternatives_per_shortage | MitigationOption | rule | 1600 | 0 | PASS |
| acceptance | accept.alternatives_show_cost_and_service | MitigationOption | rule | 7135 | 0 | PASS |
| acceptance | accept.recommendable_options_pass_policy_and_capacity | MitigationOption | rule | 6776 | 0 | PASS |
| acceptance | accept.recommendable_qty_within_capacity | MitigationOption | rule | 6776 | 0 | PASS |
| acceptance | accept.non_recommendable_options_explain_why | MitigationOption | rule | 7135 | 0 | PASS |
| acceptance | accept.exactly_one_recommended_per_shortage | Shortage | rule | 1600 | 0 | PASS |
| acceptance | accept.recommendable_substitutes_are_approved | MitigationOption | rule | 36 | 0 | PASS |
| acceptance | accept.recommended_PO_qty_sum_within_supplier_capacity | MitigationOption | rule | 366 | 0 | PASS |
| acceptance | accept.transfer_donors_stay_above_safety_stock | MitigationOption | rule | 425 | 0 | PASS |
| acceptance | accept.DQ_findings_reference_run | DataQualityFinding | rule | 195 | 0 | PASS |
