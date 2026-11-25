CREATE TABLE "UnitOfMeasure" (
  "uom_code" TEXT NOT NULL,
  "uom_name" TEXT NOT NULL,
  "uom_class" TEXT NOT NULL,
  PRIMARY KEY ("uom_code")
);

CREATE TABLE "Location" (
  "location_id" TEXT NOT NULL,
  "location_name" TEXT NOT NULL,
  "location_type" TEXT NOT NULL,
  "region" TEXT NOT NULL,
  "country" TEXT NOT NULL,
  "status" TEXT NOT NULL,
  "effective_from" TEXT NOT NULL,
  "effective_to" TEXT,
  PRIMARY KEY ("location_id")
);

CREATE TABLE "Carrier" (
  "carrier_id" TEXT NOT NULL,
  "carrier_name" TEXT NOT NULL,
  "mode" TEXT NOT NULL,
  "sourcing_region" TEXT NOT NULL,
  PRIMARY KEY ("carrier_id")
);

CREATE TABLE "Supplier" (
  "supplier_id" TEXT NOT NULL,
  "supplier_name" TEXT NOT NULL,
  "country" TEXT NOT NULL,
  "region" TEXT NOT NULL,
  "tier" TEXT NOT NULL,
  "status" TEXT NOT NULL,
  "currency" TEXT NOT NULL,
  "payment_terms_days" INTEGER NOT NULL,
  "onboarded_date" TEXT NOT NULL,
  "effective_from" TEXT NOT NULL,
  "effective_to" TEXT,
  PRIMARY KEY ("supplier_id")
);

CREATE TABLE "SKU" (
  "sku_id" TEXT NOT NULL,
  "sku_name" TEXT NOT NULL,
  "product_family" TEXT NOT NULL,
  "sku_type" TEXT NOT NULL,
  "base_uom" TEXT NOT NULL,
  "unit_cost" REAL NOT NULL,
  "unit_price" REAL NOT NULL,
  "service_level_target" REAL NOT NULL,
  "criticality" TEXT NOT NULL,
  "lifecycle_status" TEXT NOT NULL,
  "effective_from" TEXT NOT NULL,
  "effective_to" TEXT,
  PRIMARY KEY ("sku_id"),
  FOREIGN KEY ("base_uom") REFERENCES "UnitOfMeasure"("uom_code")
);

CREATE TABLE "UoMConversion" (
  "conversion_id" TEXT NOT NULL,
  "sku_id" TEXT NOT NULL,
  "from_uom" TEXT NOT NULL,
  "to_uom" TEXT NOT NULL,
  "factor" REAL NOT NULL,
  PRIMARY KEY ("conversion_id"),
  FOREIGN KEY ("sku_id") REFERENCES "SKU"("sku_id"),
  FOREIGN KEY ("from_uom") REFERENCES "UnitOfMeasure"("uom_code"),
  FOREIGN KEY ("to_uom") REFERENCES "UnitOfMeasure"("uom_code")
);

CREATE TABLE "SKULocation" (
  "sku_id" TEXT NOT NULL,
  "location_id" TEXT NOT NULL,
  "stocking_status" TEXT NOT NULL,
  "effective_from" TEXT NOT NULL,
  "effective_to" TEXT,
  PRIMARY KEY ("sku_id", "location_id"),
  FOREIGN KEY ("sku_id") REFERENCES "SKU"("sku_id"),
  FOREIGN KEY ("location_id") REFERENCES "Location"("location_id")
);

CREATE TABLE "SKUSupplier" (
  "sku_id" TEXT NOT NULL,
  "supplier_id" TEXT NOT NULL,
  "is_preferred" INTEGER NOT NULL,
  "approval_status" TEXT NOT NULL,
  "unit_price" REAL NOT NULL,
  "effective_from" TEXT NOT NULL,
  "effective_to" TEXT,
  PRIMARY KEY ("sku_id", "supplier_id"),
  FOREIGN KEY ("sku_id") REFERENCES "SKU"("sku_id"),
  FOREIGN KEY ("supplier_id") REFERENCES "Supplier"("supplier_id")
);

CREATE TABLE "SKUSubstitute" (
  "sku_id" TEXT NOT NULL,
  "substitute_sku_id" TEXT NOT NULL,
  "substitution_ratio" REAL NOT NULL,
  "approval_status" TEXT NOT NULL,
  "approved_by_role" TEXT,
  "approved_date" TEXT,
  "cost_penalty_pct" REAL NOT NULL,
  "effective_from" TEXT NOT NULL,
  "effective_to" TEXT,
  PRIMARY KEY ("sku_id", "substitute_sku_id", "effective_from"),
  FOREIGN KEY ("sku_id") REFERENCES "SKU"("sku_id"),
  FOREIGN KEY ("substitute_sku_id") REFERENCES "SKU"("sku_id")
);

CREATE TABLE "BillOfMaterial" (
  "bom_id" TEXT NOT NULL,
  "parent_sku_id" TEXT NOT NULL,
  "bom_version" INTEGER NOT NULL,
  "run_time_hours_per_unit" REAL NOT NULL,
  "lot_size" INTEGER NOT NULL,
  "effective_from" TEXT NOT NULL,
  "effective_to" TEXT,
  PRIMARY KEY ("bom_id"),
  FOREIGN KEY ("parent_sku_id") REFERENCES "SKU"("sku_id")
);

CREATE TABLE "BOMLine" (
  "bom_id" TEXT NOT NULL,
  "component_sku_id" TEXT NOT NULL,
  "qty_per" INTEGER NOT NULL,
  "scrap_pct" REAL NOT NULL,
  PRIMARY KEY ("bom_id", "component_sku_id"),
  FOREIGN KEY ("bom_id") REFERENCES "BillOfMaterial"("bom_id"),
  FOREIGN KEY ("component_sku_id") REFERENCES "SKU"("sku_id")
);

CREATE TABLE "WorkCenter" (
  "work_center_id" TEXT NOT NULL,
  "location_id" TEXT NOT NULL,
  "work_center_name" TEXT NOT NULL,
  "status" TEXT NOT NULL,
  PRIMARY KEY ("work_center_id"),
  FOREIGN KEY ("location_id") REFERENCES "Location"("location_id")
);

CREATE TABLE "ProductionCapacity" (
  "prod_capacity_id" TEXT NOT NULL,
  "work_center_id" TEXT NOT NULL,
  "iso_week" TEXT NOT NULL,
  "week_start_date" TEXT NOT NULL,
  "available_hours" REAL NOT NULL,
  PRIMARY KEY ("prod_capacity_id"),
  FOREIGN KEY ("work_center_id") REFERENCES "WorkCenter"("work_center_id")
);

CREATE TABLE "ForecastDemand" (
  "demand_id" TEXT NOT NULL,
  "sku_id" TEXT NOT NULL,
  "location_id" TEXT NOT NULL,
  "iso_week" TEXT NOT NULL,
  "week_start_date" TEXT NOT NULL,
  "forecast_qty" INTEGER NOT NULL,
  "demand_driver" TEXT NOT NULL,
  "forecast_stdev" REAL NOT NULL,
  PRIMARY KEY ("demand_id"),
  FOREIGN KEY ("sku_id") REFERENCES "SKU"("sku_id"),
  FOREIGN KEY ("location_id") REFERENCES "Location"("location_id")
);

CREATE TABLE "Inventory" (
  "inventory_id" TEXT NOT NULL,
  "sku_id" TEXT NOT NULL,
  "location_id" TEXT NOT NULL,
  "as_of_date" TEXT NOT NULL,
  "on_hand_qty" INTEGER NOT NULL,
  "allocated_qty" INTEGER NOT NULL,
  "quality_hold_qty" INTEGER NOT NULL,
  "safety_stock_qty" INTEGER NOT NULL,
  "available_qty" INTEGER NOT NULL,
  "inventory_status" TEXT NOT NULL,
  PRIMARY KEY ("inventory_id"),
  FOREIGN KEY ("sku_id") REFERENCES "SKU"("sku_id"),
  FOREIGN KEY ("location_id") REFERENCES "Location"("location_id")
);

CREATE TABLE "SupplierCapacity" (
  "capacity_id" TEXT NOT NULL,
  "supplier_id" TEXT NOT NULL,
  "product_family" TEXT NOT NULL,
  "weekly_capacity_qty" INTEGER NOT NULL,
  "min_order_qty" INTEGER NOT NULL,
  "order_multiple" INTEGER NOT NULL,
  "capacity_uom" TEXT NOT NULL,
  "status" TEXT NOT NULL,
  "effective_from" TEXT NOT NULL,
  "effective_to" TEXT,
  PRIMARY KEY ("capacity_id"),
  FOREIGN KEY ("supplier_id") REFERENCES "Supplier"("supplier_id")
);

CREATE TABLE "LeadTime" (
  "lead_time_id" TEXT NOT NULL,
  "supplier_id" TEXT NOT NULL,
  "sku_id" TEXT NOT NULL,
  "ship_to_location_id" TEXT,
  "production_days" INTEGER NOT NULL,
  "transit_days" INTEGER NOT NULL,
  "total_lead_days" INTEGER NOT NULL,
  "p90_lead_days" INTEGER NOT NULL,
  "transport_mode" TEXT NOT NULL,
  "effective_from" TEXT NOT NULL,
  "effective_to" TEXT,
  PRIMARY KEY ("lead_time_id"),
  FOREIGN KEY ("supplier_id") REFERENCES "Supplier"("supplier_id"),
  FOREIGN KEY ("sku_id") REFERENCES "SKU"("sku_id"),
  FOREIGN KEY ("ship_to_location_id") REFERENCES "Location"("location_id")
);

CREATE TABLE "PurchaseOrder" (
  "po_id" TEXT NOT NULL,
  "supplier_id" TEXT NOT NULL,
  "sku_id" TEXT NOT NULL,
  "ship_to_location_id" TEXT NOT NULL,
  "carrier_id" TEXT,
  "created_date" TEXT NOT NULL,
  "order_date" TEXT NOT NULL,
  "requested_date" TEXT NOT NULL,
  "promised_date" TEXT NOT NULL,
  "eta_date" TEXT NOT NULL,
  "actual_receipt_date" TEXT,
  "order_qty" INTEGER NOT NULL,
  "order_uom" TEXT NOT NULL,
  "qty_base" INTEGER NOT NULL,
  "unit_price" REAL NOT NULL,
  "total_cost" REAL NOT NULL,
  "supplier_ref_no" TEXT NOT NULL,
  "status" TEXT NOT NULL,
  PRIMARY KEY ("po_id"),
  FOREIGN KEY ("supplier_id") REFERENCES "Supplier"("supplier_id"),
  FOREIGN KEY ("sku_id") REFERENCES "SKU"("sku_id"),
  FOREIGN KEY ("ship_to_location_id") REFERENCES "Location"("location_id"),
  FOREIGN KEY ("carrier_id") REFERENCES "Carrier"("carrier_id"),
  FOREIGN KEY ("order_uom") REFERENCES "UnitOfMeasure"("uom_code")
);

CREATE TABLE "ProductionPlan" (
  "production_plan_id" TEXT NOT NULL,
  "sku_id" TEXT NOT NULL,
  "location_id" TEXT NOT NULL,
  "work_center_id" TEXT NOT NULL,
  "bom_id" TEXT NOT NULL,
  "iso_week" TEXT NOT NULL,
  "week_start_date" TEXT NOT NULL,
  "planned_qty" INTEGER NOT NULL,
  "required_hours" REAL NOT NULL,
  "status" TEXT NOT NULL,
  PRIMARY KEY ("production_plan_id"),
  FOREIGN KEY ("sku_id") REFERENCES "SKU"("sku_id"),
  FOREIGN KEY ("location_id") REFERENCES "Location"("location_id"),
  FOREIGN KEY ("work_center_id") REFERENCES "WorkCenter"("work_center_id"),
  FOREIGN KEY ("bom_id") REFERENCES "BillOfMaterial"("bom_id")
);

CREATE TABLE "PurchaseOrderEvent" (
  "event_id" TEXT NOT NULL,
  "po_id" TEXT NOT NULL,
  "event_type" TEXT NOT NULL,
  "from_status" TEXT,
  "to_status" TEXT NOT NULL,
  "event_date" TEXT NOT NULL,
  "actor_role" TEXT NOT NULL,
  "delay_days" INTEGER,
  "reason_code" TEXT,
  PRIMARY KEY ("event_id"),
  FOREIGN KEY ("po_id") REFERENCES "PurchaseOrder"("po_id")
);

CREATE TABLE "TransportEvent" (
  "event_id" TEXT NOT NULL,
  "po_id" TEXT NOT NULL,
  "carrier_id" TEXT NOT NULL,
  "event_type" TEXT NOT NULL,
  "event_date" TEXT NOT NULL,
  "delay_days" INTEGER,
  "reason_code" TEXT,
  "actor_role" TEXT NOT NULL,
  PRIMARY KEY ("event_id"),
  FOREIGN KEY ("po_id") REFERENCES "PurchaseOrder"("po_id"),
  FOREIGN KEY ("carrier_id") REFERENCES "Carrier"("carrier_id")
);

CREATE TABLE "InventoryEvent" (
  "event_id" TEXT NOT NULL,
  "sku_id" TEXT NOT NULL,
  "location_id" TEXT NOT NULL,
  "event_type" TEXT NOT NULL,
  "qty" INTEGER NOT NULL,
  "event_date" TEXT NOT NULL,
  "po_id" TEXT,
  "actor_role" TEXT NOT NULL,
  PRIMARY KEY ("event_id"),
  FOREIGN KEY ("sku_id") REFERENCES "SKU"("sku_id"),
  FOREIGN KEY ("location_id") REFERENCES "Location"("location_id"),
  FOREIGN KEY ("po_id") REFERENCES "PurchaseOrder"("po_id")
);

CREATE TABLE "ProductionPlanEvent" (
  "event_id" TEXT NOT NULL,
  "production_plan_id" TEXT NOT NULL,
  "from_status" TEXT,
  "to_status" TEXT NOT NULL,
  "event_date" TEXT NOT NULL,
  "actor_role" TEXT NOT NULL,
  PRIMARY KEY ("event_id"),
  FOREIGN KEY ("production_plan_id") REFERENCES "ProductionPlan"("production_plan_id")
);

CREATE TABLE "PlanRun" (
  "run_id" TEXT NOT NULL,
  "as_of_date" TEXT NOT NULL,
  "seed" INTEGER NOT NULL,
  "profile" TEXT NOT NULL,
  "engine_version" TEXT NOT NULL,
  "policy_hash" TEXT NOT NULL,
  "n_pairs" INTEGER NOT NULL,
  "n_shortages" INTEGER NOT NULL,
  PRIMARY KEY ("run_id")
);

CREATE TABLE "ProjectedBalance" (
  "run_id" TEXT NOT NULL,
  "sku_id" TEXT NOT NULL,
  "location_id" TEXT NOT NULL,
  "iso_week" TEXT NOT NULL,
  "week_start_date" TEXT NOT NULL,
  "opening_qty" INTEGER NOT NULL,
  "gross_demand_qty" INTEGER NOT NULL,
  "dependent_demand_qty" INTEGER NOT NULL,
  "scheduled_receipts_qty" INTEGER NOT NULL,
  "production_receipts_qty" INTEGER NOT NULL,
  "closing_qty" INTEGER NOT NULL,
  "safety_stock_qty" INTEGER NOT NULL,
  "shortfall_qty" INTEGER NOT NULL,
  PRIMARY KEY ("run_id", "sku_id", "location_id", "iso_week"),
  FOREIGN KEY ("run_id") REFERENCES "PlanRun"("run_id"),
  FOREIGN KEY ("sku_id") REFERENCES "SKU"("sku_id"),
  FOREIGN KEY ("location_id") REFERENCES "Location"("location_id")
);

CREATE TABLE "SupplierCapacityLedger" (
  "run_id" TEXT NOT NULL,
  "supplier_id" TEXT NOT NULL,
  "product_family" TEXT NOT NULL,
  "week_start_date" TEXT NOT NULL,
  "iso_week" TEXT NOT NULL,
  "committed_qty" INTEGER NOT NULL,
  "capacity_qty" INTEGER NOT NULL,
  "utilisation_pct" REAL NOT NULL,
  "remaining_qty" INTEGER NOT NULL,
  "status" TEXT NOT NULL,
  PRIMARY KEY ("run_id", "supplier_id", "product_family", "week_start_date"),
  FOREIGN KEY ("run_id") REFERENCES "PlanRun"("run_id"),
  FOREIGN KEY ("supplier_id") REFERENCES "Supplier"("supplier_id")
);

CREATE TABLE "Shortage" (
  "shortage_id" TEXT NOT NULL,
  "run_id" TEXT NOT NULL,
  "sku_id" TEXT NOT NULL,
  "location_id" TEXT NOT NULL,
  "first_short_week" TEXT NOT NULL,
  "last_short_week" TEXT NOT NULL,
  "peak_short_week" TEXT NOT NULL,
  "need_by_date" TEXT NOT NULL,
  "episode_weeks" INTEGER NOT NULL,
  "shortage_type" TEXT NOT NULL,
  "shortage_qty" INTEGER NOT NULL,
  "value_at_risk" REAL NOT NULL,
  "priority_score" REAL NOT NULL,
  "priority_rank" INTEGER NOT NULL,
  "primary_cause_code" TEXT NOT NULL,
  "data_quality_flag" TEXT NOT NULL,
  "status" TEXT NOT NULL,
  PRIMARY KEY ("shortage_id"),
  FOREIGN KEY ("run_id") REFERENCES "PlanRun"("run_id"),
  FOREIGN KEY ("sku_id") REFERENCES "SKU"("sku_id"),
  FOREIGN KEY ("location_id") REFERENCES "Location"("location_id")
);

CREATE TABLE "ShortageCause" (
  "shortage_id" TEXT NOT NULL,
  "cause_seq" INTEGER NOT NULL,
  "cause_code" TEXT NOT NULL,
  "contribution_qty" INTEGER NOT NULL,
  "source_table" TEXT NOT NULL,
  "source_id" TEXT NOT NULL,
  "explanation" TEXT NOT NULL,
  PRIMARY KEY ("shortage_id", "cause_seq"),
  FOREIGN KEY ("shortage_id") REFERENCES "Shortage"("shortage_id")
);

CREATE TABLE "MitigationOption" (
  "mitigation_id" TEXT NOT NULL,
  "shortage_id" TEXT NOT NULL,
  "option_type" TEXT NOT NULL,
  "supplier_id" TEXT,
  "alt_sku_id" TEXT,
  "source_location_id" TEXT,
  "ref_po_id" TEXT,
  "production_plan_id" TEXT,
  "qty" INTEGER NOT NULL,
  "covered_qty" INTEGER NOT NULL,
  "unit_cost" REAL NOT NULL,
  "expedite_premium" REAL NOT NULL,
  "freight_cost" REAL NOT NULL,
  "excess_cost" REAL NOT NULL,
  "penalty_cost" REAL NOT NULL,
  "total_cost" REAL NOT NULL,
  "cost_delta_vs_baseline" REAL NOT NULL,
  "lead_days" INTEGER,
  "earliest_arrival_date" TEXT,
  "weeks_late" INTEGER,
  "fill_rate_pct" REAL NOT NULL,
  "capacity_available_qty" INTEGER,
  "capacity_check" TEXT NOT NULL,
  "policy_check" TEXT NOT NULL,
  "policy_reason" TEXT,
  "lead_time_check" TEXT NOT NULL,
  "approval_required_role" TEXT NOT NULL,
  "is_recommendable" INTEGER NOT NULL,
  "rank" INTEGER NOT NULL,
  "is_recommended" INTEGER NOT NULL,
  "status" TEXT NOT NULL,
  PRIMARY KEY ("mitigation_id"),
  FOREIGN KEY ("shortage_id") REFERENCES "Shortage"("shortage_id"),
  FOREIGN KEY ("supplier_id") REFERENCES "Supplier"("supplier_id"),
  FOREIGN KEY ("alt_sku_id") REFERENCES "SKU"("sku_id"),
  FOREIGN KEY ("source_location_id") REFERENCES "Location"("location_id"),
  FOREIGN KEY ("ref_po_id") REFERENCES "PurchaseOrder"("po_id"),
  FOREIGN KEY ("production_plan_id") REFERENCES "ProductionPlan"("production_plan_id")
);

CREATE TABLE "ShortageEvent" (
  "event_id" TEXT NOT NULL,
  "shortage_id" TEXT NOT NULL,
  "from_status" TEXT,
  "to_status" TEXT NOT NULL,
  "event_date" TEXT NOT NULL,
  "actor_role" TEXT NOT NULL,
  "comment" TEXT,
  PRIMARY KEY ("event_id"),
  FOREIGN KEY ("shortage_id") REFERENCES "Shortage"("shortage_id")
);

CREATE TABLE "MitigationEvent" (
  "event_id" TEXT NOT NULL,
  "mitigation_id" TEXT NOT NULL,
  "from_status" TEXT,
  "to_status" TEXT NOT NULL,
  "event_date" TEXT NOT NULL,
  "actor_role" TEXT NOT NULL,
  "comment" TEXT,
  PRIMARY KEY ("event_id"),
  FOREIGN KEY ("mitigation_id") REFERENCES "MitigationOption"("mitigation_id")
);

CREATE TABLE "DataQualityFinding" (
  "finding_id" TEXT NOT NULL,
  "run_id" TEXT NOT NULL,
  "issue_type" TEXT NOT NULL,
  "entity" TEXT NOT NULL,
  "record_id" TEXT NOT NULL,
  "related_record_ids" TEXT,
  "impact_qty" INTEGER,
  "detail" TEXT NOT NULL,
  PRIMARY KEY ("finding_id"),
  FOREIGN KEY ("run_id") REFERENCES "PlanRun"("run_id")
);
