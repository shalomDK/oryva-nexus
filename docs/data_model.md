# Data model: relationships, cardinality, effective dates, lifecycles

Authoritative field-level detail is in `data/<profile>/docs/data_dictionary.md` (generated from `src/oryva/schema.py`);
the SQL DDL (`data/<profile>/sql/schema.sql`) has all 32 primary keys and 57 foreign keys.

## Cardinality (FK = foreign key; "opt" = optional relationship)

| Relationship | Cardinality | Realised by |
|---|---|---|
| SKU <-> Location | N:M | bridge `SKULocation` (ACTIVE pairs carry 52 weeks of demand + 1 Inventory row; INACTIVE none) |
| SKU <-> Supplier | N:M | bridge `SKUSupplier` (1-3 suppliers per bought SKU; `is_preferred`, `approval_status`) |
| SKU <-> SKU (substitute) | N:M | bridge `SKUSubstitute` (approval workflow, effective-dated) |
| make-SKU <-> component SKU | N:M | `BillOfMaterial` (1:N from SKU) + bridge `BOMLine` |
| SKU 1:N ForecastDemand, Location 1:N ForecastDemand | 1:N | `ForecastDemand.sku_id/location_id` (+ pair must exist in `SKULocation`) |
| (SKU, Location) 1:1 Inventory (per as-of date) | 1:1 | `Inventory` |
| Supplier 1:N SupplierCapacity | 1:N | effective-dated, per product family |
| (Supplier, SKU[, ship-to Location opt]) 1:N LeadTime | 1:N | `ship_to_location_id` optional (empty = default) |
| Supplier 1:N PurchaseOrder; Carrier 1:N PurchaseOrder (opt) | 1:N | `carrier_id` assigned only once shipped |
| PurchaseOrder 1:N PurchaseOrderEvent / TransportEvent (opt) / InventoryEvent (opt) | 1:N | append-only history |
| Plant Location 1:N WorkCenter 1:N ProductionCapacity (weekly) | 1:N | |
| ProductionPlan N:1 (make-SKU, plant, work centre, BOM) | N:1 | `ProductionPlanEvent` 1:N |
| PlanRun 1:N Shortage; (SKU, Location) 1:N Shortage (episodes) | 1:N | |
| Shortage 1:N MitigationOption (>= 2) ; Shortage 1:N ShortageCause | 1:N | `ShortageCause` is the evidence bridge shortage <-> source record (N:M, any source table) |
| Shortage 1:N ShortageEvent; MitigationOption 1:N MitigationEvent | 1:N | append-only |

Optional FKs: `PurchaseOrder.carrier_id`, `PurchaseOrder.actual_receipt_date`, `LeadTime.ship_to_location_id`,
`MitigationOption.{supplier_id, alt_sku_id, source_location_id, ref_po_id, production_plan_id}`, `InventoryEvent.po_id`.

## Effective dating (never overwritten; new row supersedes)

`Location, Supplier, SKU, SKULocation, SKUSupplier, SKUSubstitute, BillOfMaterial, SupplierCapacity, LeadTime` carry
`effective_from` (inclusive) / `effective_to` (exclusive, empty = open). For `SupplierCapacity` overlapping windows are
allowed; the row with the latest `effective_from` wins (used for capacity expansions and the capacity-exceeded edge case).

## Lifecycles (enforced by the validator against the event tables; header status == last event)

| Entity | Allowed transitions |
|---|---|
| PurchaseOrder | (start)->PLANNED; PLANNED->CONFIRMED/CANCELLED; CONFIRMED->IN_TRANSIT/CANCELLED; IN_TRANSIT->DELAYED/RECEIVED; DELAYED->DELAYED/RECEIVED |
| ProductionPlan | (start)->PLANNED; PLANNED->FIRMED/CANCELLED; FIRMED->RELEASED/CANCELLED; RELEASED->COMPLETED |
| Shortage | (start)->DETECTED->ANALYZED->MITIGATION_PROPOSED or NEEDS_REVIEW; NEEDS_REVIEW->DETECTED; MITIGATION_PROPOSED->MITIGATION_APPROVED/ACCEPTED_BACKORDER; MITIGATION_APPROVED->RESOLVED |
| MitigationOption | (start)->PROPOSED->APPROVED/REJECTED; APPROVED->EXECUTED |

Terminal states (RECEIVED, CANCELLED, COMPLETED, RESOLVED, ACCEPTED_BACKORDER, REJECTED, EXECUTED) have no outgoing transition, so a
later event on them fails `*.transitions_allowed`.
