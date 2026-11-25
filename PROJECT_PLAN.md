# PROJECT_PLAN.md — ORYVA NEXUS: Demand, Inventory & Supply Planning

Source of truth: *ORYVA AI Private Limited — Student Technical Assignment: Demand, Inventory & Supply Planning* (4 pages, fully read).
**Deadline: 25 November 2026, end of day.** Deliverable: public GitHub repo + submission form.

> **Schedule warning.** This plan was written on 23 Nov 2026 — roughly **2 days** before the deadline. The plan is therefore split into a **P0 mandatory gate** (everything the PDF requires) and **P1–P3 enhancements** that are only started after the P0 gate is green. See §11–§12.

Legend: **[M]** = mandatory (stated in the PDF) · **[I]** = interpretation/decision we make where the PDF is silent (must not contradict the PDF) · **[O]** = optional enhancement.

---

## Implementation status (updated 24 Nov 2026)

**Mandatory scope (P0) is implemented and verified** — see [README.md](README.md) for run instructions and the
generated `data/*/docs/validation_summary.md` for evidence. Decisions confirmed by the user: sparse assortment with a
**configurable** density (default 0.10), all SKUs/locations in master data, every active pair has 52 weeks.

Deviations from this blueprint (all documented in README §10):

* Stack: pandas + SQLite + argparse only (DuckDB, Typer, FastAPI, Streamlit, hypothesis were dropped; not needed for P0).
* PO status `DRAFT` was dropped; lifecycle is `PLANNED → CONFIRMED → IN_TRANSIT → (DELAYED) → RECEIVED`, `CANCELLED`.
* Only the *duplicate-PO* variant of "inbound counted twice" is implemented (variant B dropped).
* Capacity-exceeded is injected as a superseding effective-dated capacity row (rule: latest `effective_from` wins), not by adding POs.
* Cause code `COMPONENT_SHORTAGE` was dropped (no production feedback loop); new codes `INBOUND_LATE_SUPPLIER`,
  `PRODUCTION_PLAN_CANCELLED`, `PRODUCTION_PLAN_SHORTFALL`, `INBOUND_QTY_SHORTFALL` were added.
* Optional enhancements (§9) are now built in `src/oryva/advanced/` and `src/oryva/app/` (Streamlit app, assistant, simulator, supplier
  intelligence, replenishment, risk, optimizer) — see FINAL_REPORT.md. Streamlit/altair were added; scipy was not (blocked on the target machine).

---

## 0. Document map

1. Mandatory requirements register (traceable to PDF sections)
2. Interpretations & open decisions
3. Modules and development phases
4. Data model (entities, keys, relationships, lifecycles)
5. Planning workflow: demand → inventory → capacity → lead time → shortage → mitigation
6. The five mandatory edge cases
7. Synthetic data: generation, validation, ground truth, reproducibility
8. Technology stack
9. Optional enhancements (AI assistant, what-if, supplier intelligence, replenishment, risk prediction)
10. Architecture (starter vs. full dataset)
11. Testing & evaluation strategy
12. Prioritised development checklist
13. First development tasks

---

## 1. Mandatory requirements register [M]

Every row must be green before the project is "complete". "Verified by" is the automated check or artifact that proves it.

### 1.1 Problem, scope, workflow (PDF §1–§3)

| ID | PDF § | Requirement | Verified by |
|---|---|---|---|
| R-001 | 1 | End-to-end solution matching **forecast demand** to **inventory, supplier capacity, lead times and production constraints** | Planning engine integration test on golden dataset |
| R-002 | 1 | Shortages are **identified, explained and prioritized** | Shortage table has cause rows + `priority_score/rank`; tests R-042 |
| R-003 | 2 | Solution **exposes key decisions and exceptions** | Exception report (DQ findings) + decision log (events) + UI/report |
| R-004 | 2, 10 | **Preserve traceability** — evidence behind every shortage and mitigation | `ShortageCause` + `MitigationOption` store source record IDs; trace test |
| R-005 | 2 | **Measurable outputs** | KPI/metrics report (§11.3) |
| R-006 | 2 | Medium complexity: multiple related entities, **conditional business rules, ≥1 exception path, meaningful evaluation metrics** | Entity count, rule tests, 5 edge-case paths, metrics report |
| R-007 | 2 | Primary actors represented: Supplier, Planner, Carrier/warehouse operator, Logistics analyst, Operations manager | `actor_role` on events; role-specific views/reports (§4.6, §9) |
| R-008 | 3 | **Master data first**: SKU, Location, ForecastDemand, Inventory, Supplier | Generator order; dependency test |
| R-009 | 3 | **Dependent records next** (transactions/events) using valid parent IDs | FK-integrity validator |
| R-010 | 3, 5 | Planning logic: SKU-location demand by week; seed on-hand + inbound inventory; supplier capacity, MOQ, lead times; production capacity + BOM where applicable; projected available balance; shortages + candidate mitigations | Pipeline stages §5 |
| R-011 | 3 | **Preserve history**: state changes persisted as explicit records/events; **never overwrite** | Event tables; append-only test; effective-dated rows |
| R-012 | 3 | Outcomes and ground-truth labels **derived from documented rules**, not independent random assignment | Rules documented in §5/§7; test that labels are recomputable from source rows |

### 1.2 Entities, relationships, IDs (PDF §4)

| ID | PDF § | Requirement | Verified by |
|---|---|---|---|
| R-013 | 4 | Core entities exist: **SKU, Location, ForecastDemand, Inventory, Supplier, SupplierCapacity, LeadTime, PurchaseOrder, ProductionPlan, Shortage, MitigationOption** | Schema test: all 11 tables exported |
| R-014 | 4 | **Primary key for every entity, foreign key for every relationship** | DDL + PK/FK validators |
| R-015 | 4 | Document **cardinality (1:1, 1:N, N:M), optional relationships, effective dates, lifecycle states** | §4 + data dictionary |
| R-016 | 4 | **Bridge tables** for many-to-many | `SKUSubstitute`, `SKUSupplier`, `SKULocation`, `BOMLine`, `ShortageCause` |
| R-017 | 4 | Retain **event history** for state changes; **validate all joins** | Event tables; join validator |
| R-018 | 4 | Anomalies stored with **issue_type / ground_truth label**, not by silently corrupting unrelated rows | `ground_truth` file; "blast radius" test (R-029) |
| R-019 | 4 | SKU ID = `SKU-000001` | Regex validator |
| R-020 | 4 | Forecast demand ID = `DEM-<sku>-<location>-2026W01` | Regex + recompute-from-FKs validator |
| R-021 | 4 | PO ID = `PO-2026-000001` | Regex validator |
| R-022 | 4 | Shortage ID = `SHORT-2026-000001` | Regex validator |
| R-023 | 4 | Mitigation ID = `MIT-<shortage-id>-01` | Regex + recompute validator |
| R-024 | 4 | Counters **zero-padded**, IDs **immutable**, referenced IDs **exactly consistent across files** | Cross-file FK test; ID-stability test across regenerations |

### 1.3 Synthetic data generation (PDF §5, Steps 1–10)

| ID | Step | Requirement | Verified by |
|---|---|---|---|
| R-025 | 1 | **Data dictionary** for all 11 core entities; per field: **type, required/optional, allowed values, units, uniqueness, validation rule** | Dictionary generated from schema registry; completeness test (no empty cell) |
| R-026 | 2 | Generate in **dependency order** (parents → children/events); demand by week; on-hand & inbound; capacity/MOQ/lead time; production capacity + BOM; PAB; shortages; mitigations | Generator DAG test |
| R-027 | 3 | **Deterministic IDs**, zero-padded, immutable, consistent in all exports | Regeneration test |
| R-028 | 4 | Baseline volume: **3,000 SKUs, 50 locations, 52 weeks demand, 500 suppliers, 10,000 inbound orders**; include **demand spikes, constrained suppliers, substitute SKUs, transport delays**; fixed seed (e.g. **20261022**); **scale parameterised, starter and full use the same generator** | `full` profile row counts; scenario-presence tests; single code path |
| R-029 | 5 | **Valid baseline first, then inject** labelled edge cases; **do not silently corrupt unrelated records** | Two-pass generator; test: baseline validates clean *before* injection; diff after injection touches only labelled rows |
| R-030 | 6 | **Derived values** (totals, balances, scores, statuses, dates) calculated from source records, not generated independently | Recompute/reconcile validators |
| R-031 | 7 | **Separate** `ground_truth.csv` or `.json` for anomalies/expected decisions/labels; **never leaked** into input features | Separate directory; firewall test (§7.5) |
| R-032 | 8 | Validation: **PK uniqueness, FK integrity, allowed enums, date ordering, arithmetic reconciliation, lifecycle transitions, duplicate checks** | `validate` command + `validation_summary` |
| R-033 | 9 | Export **CSV/JSON/SQL seed** + **README, schema/data dictionary, generator command, fixed seed, source manifest, validation summary** | Export manifest test |
| R-034 | 10 | **Regenerate twice with same seed; compare row counts and checksums** | `repro` command + stored report |

### 1.4 Edge cases (PDF §6)

| ID | Requirement |
|---|---|
| R-035 | Inbound inventory counted twice |
| R-036 | Substitute SKU not approved |
| R-037 | Supplier capacity exceeded |
| R-038 | Shortage calculated without lead time |
| R-039 | Units-of-measure mismatch |
| R-040 | Each injected case identifiable via issue_type/ground_truth label **and** traceable to relevant source records (detail in §6) |

### 1.5 Validation rules & acceptance criteria (PDF §7)

| ID | Requirement | Verified by |
|---|---|---|
| R-041 | Projected available balance **reconciles week by week** | Residual = 0 test on every SKU-location chain |
| R-042 | **Every shortage has explainable causes** | Query: shortages without ≥1 `ShortageCause` = 0 |
| R-043 | **Every mitigation respects policy and available capacity** | Policy/capacity validator over all `recommendable` options |
| R-044 | **Alternatives show cost and service trade-offs** | ≥2 alternatives where feasible, each with cost + service fields populated |
| R-045 | PKs unique, all FK joins valid | Validators |
| R-046 | Derived values reconcile to source; lifecycle transitions and dates valid | Validators |

### 1.6 Evaluation focus (PDF §8) — reviewers grade these areas

| Area | What is evaluated | Our evidence |
|---|---|---|
| A | Realistic distributions, meaningful variation | Distribution report (ABC/Pareto, seasonality, intermittent demand, lead-time spread) |
| B | Consistent IDs, valid joins | R-019–R-024, R-045 |
| C | Dependency & lifecycle consistency across entities | Lifecycle/date validators, event-vs-header consistency |
| D | Correct derived values & reconciliation | R-030, R-041, R-046 |
| E | Normal, boundary, failure, exception coverage | Boundary data + 5 edge cases + validator negative tests |
| F | Separate ground-truth labels excluded from input features | R-031 firewall |
| G | Fixed-seed reproducibility, documentation, **lawful provenance** | R-033, R-034, source manifest |

### 1.7 Lawful data use (PDF §9)

| ID | Requirement |
|---|---|
| R-047 | External data is **optional**. If used: record source URL, dataset/version, retrieval date, license/terms, attribution, transformations, fields discarded |
| R-048 | Use only legally accessible/redistributable data; no access-control bypass; no confidential/personal information |
| R-049 | If licensing/suitability is unclear → **use synthetic data**, cite public data only for schema inspiration |

**Decision: use 100% synthetic data, no external datasets.** The source manifest still ships and states "no external data; schema inspired by generic MRP/APS concepts".

### 1.8 Submission (PDF §10 + "How to submit")

| ID | Requirement |
|---|---|
| R-050 | Code pushed to a **public GitHub repository** |
| R-051 | **README**: how to install, configure, run |
| R-052 | Include **the requested tests and validation output** |
| R-053 | Include generated data exports, schema/data dictionary, generator command, fixed seed, source manifest, validation summary |
| R-054 | Include the **separate ground-truth file** and **demonstrate reproducibility** with the same seed |
| R-055 | Build and test locally → push → **submit via the form** shared with the student |
| R-056 | Submission must be **reproducible, auditable, easy for another person to run**; decisions explainable; **evidence preserved behind every shortage and mitigation** |
| R-057 | Meet the **25 Nov 2026 EOD** deadline |

---

## 2. Interpretations & open decisions [I]

The PDF is silent or ambiguous on the points below. Each choice is consistent with the PDF; flag any you want changed **before** coding.

| # | Topic | Decision | Why / risk |
|---|---|---|---|
| D1 | **issue_type / label location** (PDF §4 says "store an issue_type/ground_truth label"; §5 Step 7 says a *separate* file never leaked to inputs) | Labels live **only** in `ground_truth.csv/json`, keyed by affected record IDs. Input tables carry **no** label columns. | Satisfies both statements; leaking labels into input tables would violate F. |
| D2 | **Sparse vs. dense demand.** 3,000 × 50 × 52 = 7.8 M rows if every SKU is in every location | Use an **assortment bridge `SKULocation`** with configurable `assortment_density` (default ≈ 0.10 → ~0.8 M demand rows). | Dense data is ~600 MB — over GitHub's 100 MB file limit and unrealistic (stores don't stock everything). Counts of 3,000 SKUs / 50 locations / 52 weeks are all still met. **Confirm density.** |
| D3 | **Large files in GitHub** | Commit starter exports + full-dataset exports split into ≤ 50 MB chunks (or `.csv.gz`), with checksum manifest; if still too large use Git LFS. Full data always regenerable by one command. | PDF requires data exports in the repo and reproducibility. |
| D4 | **Location ID format** (not specified) | `LOC-001` … `LOC-050` | Makes `DEM-SKU-000001-LOC-001-2026W01` readable. |
| D5 | **Other ID formats** | `SUP-0001`, `INV-<sku>-<loc>`, `PP-2026-000001`, `SCAP-000001`, `LT-000001`, `EVT-…` | Same zero-pad/immutable rules as §4. |
| D6 | **"10,000 inbound orders"** | = 10,000 `PurchaseOrder` rows (single-line PO: one SKU per PO). | Keeps PO ID pattern and counts exact. Header/line split would make "10,000" ambiguous. |
| D7 | **Time model** | ISO weeks; `2026W01` starts Monday 2025-12-29. `as_of_date` is a **fixed parameter** (default = start of 2026W01 + generation-time constant, never `now()`). PO statuses are derived from dates vs. `as_of_date`; future-dated orders are `PLANNED/CONFIRMED` (firm scheduled receipts), historic ones `RECEIVED`/`CANCELLED`. Events after `as_of_date` must not exist. | Required for determinism and date-ordering validation. |
| D8 | **Weekly grain** | All planning buckets = ISO week; quantities in **base UoM**. | PDF says "demand by week". |
| D9 | **Shortage grain** | One `Shortage` per SKU-location **episode** (contiguous weeks below target): first shortage week, peak deficit. | Keeps volume manageable; because PAB is cumulative, covering the peak fixes the episode. |
| D10 | **"Requested tests"** (PDF §10 says "requested tests" but only §5 Step 8, Step 10 and §7 define checks) | Treat as: the Step 8 validation suite, Step 10 reproducibility comparison, §7 acceptance criteria, **plus** our own unit/negative tests. | Superset is safe. |
| D11 | **Anomalies vs. scenarios** | Ground truth has `label_class = ANOMALY` (five edge cases) and `label_class = SCENARIO` (demand spikes, constrained suppliers, transport delays, substitute links — valid business variation the engine must *explain*). | PDF asks for both variation and labelled exceptions. |
| D12 | **Repo name / license** | Public repo `oryva-nexus`; MIT license. | Needed for "public". |
| D13 | **Which actor does what** | Supplier → confirms POs/capacity; Planner → approves mitigations; Carrier/warehouse operator → shipment/receipt events; Logistics analyst → transport-delay & lead-time analysis; Ops manager → KPI view & approvals above threshold. Implemented as `actor_role` on event rows and as report views (no full auth system). | PDF lists actors but no auth requirement. |

---

## 3. Modules and development phases

### 3.1 Modules

| # | Module | Responsibility | Mandatory? |
|---|---|---|---|
| M1 | **Schema registry** | Single source of truth: entities, fields, types, enums, units, uniqueness, validation rules, FKs, cardinality, lifecycles. Emits DDL, data dictionary, validators. | [M] |
| M2 | **ID service** | Deterministic zero-padded ID builders + regex parsers. | [M] |
| M3 | **Generator** | Seeded, dependency-ordered, scale-parameterised synthetic data; two-pass (baseline → injection). | [M] |
| M4 | **Edge-case injector** | Five labelled anomalies + scenario markers; writes `ground_truth`. | [M] |
| M5 | **Validator** | PK/FK/enum/date/arithmetic/lifecycle/duplicate checks; produces `validation_summary`. | [M] |
| M6 | **Exporter** | CSV/JSON/SQL seed, data dictionary, manifest, checksums. | [M] |
| M7 | **Reproducibility harness** | Run twice, compare row counts + SHA-256. | [M] |
| M8 | **Planning engine** | DQ gate, UoM normalisation, netting/PAB, shortage detection, cause attribution, prioritisation, mitigation generation, event persistence. | [M] |
| M9 | **Evaluation / metrics** | Edge-case detection precision/recall vs. ground truth, reconciliation stats, KPIs. | [M] (R-005/R-006) |
| M10 | **Storage layer** | SQLite (portable) with DuckDB analytics view; loads the SQL seed. | [M] (SQL seed) |
| M11 | **CLI** | `generate`, `validate`, `plan`, `repro`, `evaluate`, `export`. | [M] (generator command) |
| M12 | **API + UI** | FastAPI + Streamlit: shortage list, drill-down, mitigation comparison, exception report. | [O] (strongly recommended: "exposes decisions") |
| M13 | **AI planning assistant** | Grounded natural-language Q&A over the planning DB. | [O] |
| M14 | **What-if simulator** | Scenario overlays; baseline immutable. | [O] |
| M15 | **Supplier performance intelligence** | OTIF, lead-time variability, utilisation, scorecard. | [O] |
| M16 | **Automated replenishment** | Policy-respecting PO proposals. | [O] |
| M17 | **Risk prediction** | Shortage / delay risk model. | [O] |

### 3.2 Phases

| Phase | Name | Output | Gate |
|---|---|---|---|
| **P0** | Foundations | Repo skeleton, schema registry, ID service, CI, pytest | Schema emits DDL + dictionary |
| **P1** | Master + dependent data | Generator for 11 core + supporting tables, starter profile | Baseline validates clean |
| **P2** | Planning engine | PAB, shortage, causes, priority, mitigations | R-041…R-044 pass on starter |
| **P3** | Edge cases + ground truth | 5 injections, labels, detectors in engine | Detector precision = recall = 1.0 on starter |
| **P4** | Validation + export + repro | Validator, exports, manifest, `repro` | R-032…R-034 pass |
| **P5** | Full dataset | 3,000/50/52/500/10,000 run, performance tuned, size-split exports | Full validates, repro on full |
| **P6** | Docs & submission | README, dictionary, validation summary, push, form | Fresh-clone run works |
| **P7** | Enhancements (only after P0–P6 green) | M12–M17 | Mandatory tests still green |

---

## 4. Data model

### 4.1 Conventions

* All keys are strings with the ID patterns of PDF §4 (and D4/D5). All IDs immutable; never reused.
* Quantities are in **SKU base UoM** unless a field says otherwise (`order_qty` + `order_uom` + derived `qty_base`).
* Effective-dated tables use `effective_from` (inclusive) / `effective_to` (exclusive, nullable = open). **A change creates a new row; old rows are closed, never edited.**
* Timestamps in events are deterministic (derived from generated dates), never wall-clock.
* No label columns in input tables (D1).

### 4.2 Core entities (the 11 mandatory)

**SKU** — PK `sku_id` (`SKU-000001`)
`sku_name`, `product_family` (FK-like enum), `sku_type` {FINISHED_MAKE, FINISHED_BUY, COMPONENT}, `base_uom` (FK `UnitOfMeasure`), `unit_cost`, `unit_price`, `service_level_target`, `criticality` {A,B,C — derived from revenue contribution}, `lifecycle_status` {NEW, ACTIVE, PHASING_OUT, DISCONTINUED}, `effective_from`, `effective_to`.

**Location** — PK `location_id` (`LOC-001`)
`location_name`, `location_type` {PLANT, DC, STORE}, `region`, `country`, `status` {ACTIVE, INACTIVE}, `effective_from/to`. (≈ 6 PLANT, 9 DC, 35 STORE at 50 locations; plants own production lines.)

**ForecastDemand** — PK `demand_id` (`DEM-<sku>-<location>-2026W01`)
FK `sku_id`, `location_id` (must exist in `SKULocation`); `iso_week` (`2026W01`), `week_start_date`, `forecast_qty` (base UoM, ≥ 0), `demand_driver` {BASELINE, SEASONAL, PROMO, SPIKE}, `forecast_stdev`.
Unique (`sku_id`,`location_id`,`iso_week`) — also implied by the ID.

**Inventory** — PK `inventory_id` (`INV-<sku>-<location>`)
FK `sku_id`, `location_id`; `as_of_date`, `on_hand_qty`, `allocated_qty`, `quality_hold_qty`, `safety_stock_qty`, `available_qty` (**derived** = on_hand − allocated − quality_hold), `inventory_status`. Unique (`sku_id`,`location_id`,`as_of_date`). Inbound inventory is represented by open `PurchaseOrder` rows (+ `ProductionPlan` output); realised receipts by `InventoryEvent`.

**Supplier** — PK `supplier_id` (`SUP-0001`)
`supplier_name`, `country`, `region`, `tier` {STRATEGIC, PREFERRED, STANDARD}, `status` {ONBOARDING, ACTIVE, ON_HOLD, INACTIVE}, `currency`, `payment_terms_days`, `onboarded_date`, `effective_from/to`.

**SupplierCapacity** — PK `capacity_id` (`SCAP-000001`), effective-dated
FK `supplier_id`; `product_family`, `weekly_capacity_qty` (base UoM), `min_order_qty` (MOQ), `order_multiple`, `capacity_uom`, `effective_from/to`, `status`. Unique (`supplier_id`,`product_family`,`effective_from`). Constrained suppliers = high planned utilisation (≤ 100% in baseline).

**LeadTime** — PK `lead_time_id` (`LT-000001`), effective-dated
FK `supplier_id`, `sku_id`; optional FK `ship_to_location_id` (NULL = default for all locations); `production_days`, `transit_days`, `total_lead_days` (**derived** = production + transit), `p90_lead_days`, `transport_mode` {ROAD, RAIL, SEA, AIR}, `effective_from/to`.

**PurchaseOrder** — PK `po_id` (`PO-2026-000001`)
FK `supplier_id`, `sku_id`, `ship_to_location_id`; optional FK `carrier_id`; `order_date`, `requested_date`, `promised_date`, `eta_date` (current, derived from latest delay events), `actual_receipt_date` (nullable), `order_qty`, `order_uom`, `qty_base` (**derived** = order_qty × conversion factor), `unit_price`, `total_cost` (**derived**), `supplier_ref_no`, `status` (derived from latest `PurchaseOrderEvent`).
Lifecycle: `DRAFT → CONFIRMED → IN_TRANSIT → RECEIVED`; `PLANNED → CONFIRMED`; `CONFIRMED|IN_TRANSIT → DELAYED → IN_TRANSIT`; `DRAFT|PLANNED|CONFIRMED → CANCELLED`. `RECEIVED` and `CANCELLED` are terminal.
Date ordering: `order_date ≤ promised_date`, `order_date ≤ eta_date`, `actual_receipt_date ≥ order_date` and only when `RECEIVED`.

**ProductionPlan** — PK `production_plan_id` (`PP-2026-000001`)
FK `sku_id` (FINISHED_MAKE), `location_id` (PLANT), `work_center_id`, `bom_id`; `iso_week`, `planned_qty`, `required_hours` (**derived** = qty × run_time_hours_per_unit), `lot_size`, `status` {PLANNED, FIRMED, RELEASED, COMPLETED, CANCELLED}.

**Shortage** — PK `shortage_id` (`SHORT-2026-000001`)
FK `sku_id`, `location_id`, `run_id`; `first_short_week`, `need_by_date`, `shortage_type` {STOCKOUT, SAFETY_STOCK_BREACH}, `shortage_qty` (**derived** peak deficit), `value_at_risk` (**derived**), `priority_score`, `priority_rank`, `primary_cause_code` (derived from top `ShortageCause`), `status`.
Lifecycle: `DETECTED → ANALYZED → MITIGATION_PROPOSED → MITIGATION_APPROVED → RESOLVED`; `… → ACCEPTED_BACKORDER`; `NEEDS_REVIEW` (data-quality blocked) → `DETECTED`.

**MitigationOption** — PK `mitigation_id` (`MIT-<shortage-id>-01`)
FK `shortage_id`; optional FKs `supplier_id`, `alt_sku_id` (via `SKUSubstitute`), `source_location_id`, `production_plan_id`;
`option_type` {EXPEDITE_PO, NEW_PO, ALT_SUPPLIER_PO, SUBSTITUTE_SKU, LOCATION_TRANSFER, PRODUCTION_REPLAN, PARTIAL_FILL_BACKORDER};
`qty` (after MOQ/multiple rounding), `unit_cost`, `expedite_premium`, `freight_cost`, `excess_cost`, `total_cost`, `cost_delta_vs_baseline`, `lead_days`, `earliest_arrival_date`, `weeks_late`, `covered_qty`, `fill_rate_pct`, `service_impact`, `capacity_available_qty`, `capacity_check` {PASS, FAIL}, `policy_check` {PASS, FAIL}, `policy_reason`, `lead_time_check`, `is_recommendable`, `rank`, `status` {PROPOSED, APPROVED, REJECTED, EXECUTED, EXPIRED}.

### 4.3 Supporting entities (added; required for N:M, UoM, BOM, events)

| Table | PK | Purpose / key fields | Rel. |
|---|---|---|---|
| `UnitOfMeasure` | `uom_code` | EA, CASE, PALLET, KG, L… | 1:N SKU |
| `UoMConversion` | (`sku_id`,`from_uom`,`to_uom`) | `factor` (SKU-specific, e.g. 1 CASE = 12 EA) | N:1 SKU |
| `SKULocation` (bridge) | (`sku_id`,`location_id`) | assortment: `stocking_status`, `effective_from/to` | **N:M** SKU↔Location |
| `SKUSupplier` (bridge) | (`sku_id`,`supplier_id`) | `is_preferred`, `approval_status`, `unit_price`, `effective_from/to` | **N:M** SKU↔Supplier |
| `SKUSubstitute` (bridge) | (`sku_id`,`substitute_sku_id`,`effective_from`) | `substitution_ratio`, `approval_status` {APPROVED, PENDING, REJECTED, EXPIRED}, `approved_by_role`, `approved_date`, `cost_penalty_pct` | **N:M** SKU↔SKU |
| `BillOfMaterial` | `bom_id` | parent FINISHED_MAKE SKU, version, `effective_from/to` | 1:N SKU→BOM |
| `BOMLine` (bridge) | (`bom_id`,`component_sku_id`) | `qty_per`, `scrap_pct` | **N:M** parent↔component |
| `WorkCenter` | `work_center_id` | FK plant `location_id` | N:1 Location |
| `ProductionCapacity` | `prod_capacity_id` | FK `work_center_id`, weekly `available_hours`, `effective_from/to`; `run_time_hours_per_unit` per (work center, SKU) | 1:N |
| `Carrier` | `carrier_id` | name, mode, region | 1:N PO |
| `PlanRun` | `run_id` | `as_of_date`, `seed`, `profile`, `engine_version`, parameters hash | 1:N Shortage |
| `ProjectedBalance` (derived) | (`run_id`,`sku_id`,`location_id`,`iso_week`) | opening, gross, dependent, receipts, production, closing, safety stock | N:1 SKU, Location |
| `SupplierCapacityLedger` (derived) | (`run_id`,`supplier_id`,`product_family`,`iso_week`) | committed_qty, capacity_qty, utilisation_pct, remaining_qty | N:1 Supplier |
| `ShortageCause` (bridge, derived) | (`shortage_id`,`cause_seq`) | `cause_code`, `contribution_qty`, `source_table`, `source_id`, `explanation` | **N:M** Shortage↔source records |

### 4.4 Event (history) tables — append-only

| Table | Key fields |
|---|---|
| `PurchaseOrderEvent` | `event_id`, `po_id`, `event_type` {CREATED, CONFIRMED, SHIPPED, DELAYED, RECEIVED, CANCELLED, ETA_REVISED}, `from_status`, `to_status`, `event_date`, `actor_role`, `delay_days`, `reason_code` |
| `TransportEvent` | `event_id`, `po_id`, `carrier_id`, `event_type` {DEPARTED, IN_TRANSIT, DELAYED, ARRIVED}, `delay_days`, `reason_code` {WEATHER, PORT_CONGESTION, CUSTOMS, BREAKDOWN, …} |
| `InventoryEvent` | `event_id`, `sku_id`, `location_id`, `event_type` {RECEIPT, ISSUE, ADJUSTMENT}, `qty`, `po_id` (nullable) |
| `ProductionPlanEvent` | status changes for `ProductionPlan` |
| `ShortageEvent` | `DETECTED, ANALYZED, MITIGATION_PROPOSED, APPROVED, RESOLVED, ACCEPTED, REOPENED` + `actor_role` |
| `MitigationEvent` | `PROPOSED, APPROVED, REJECTED, EXECUTED` + `actor_role`, comment |

Rule: header "current status" is **derived from the latest event**; a validator asserts header status == last event `to_status` and that every transition is in the allowed-transition map.

### 4.5 Relationship summary (cardinality)

| Relationship | Card. | Optional? | Notes |
|---|---|---|---|
| SKU → ForecastDemand | 1:N | no | via SKULocation |
| Location → ForecastDemand | 1:N | no | |
| SKU ↔ Location | N:M (`SKULocation`) | — | assortment |
| SKU ↔ Supplier | N:M (`SKUSupplier`) | — | 1–3 suppliers/SKU |
| SKU ↔ SKU (substitute) | N:M (`SKUSubstitute`) | — | approval-gated |
| FINISHED_MAKE SKU ↔ COMPONENT SKU | N:M (`BOMLine`) | only for make-SKUs | |
| Supplier → SupplierCapacity | 1:N | no | effective-dated |
| (Supplier, SKU[, Location]) → LeadTime | 1:N | location optional | |
| Supplier → PurchaseOrder | 1:N | no | |
| Carrier → PurchaseOrder | 1:N | **optional** | |
| PurchaseOrder → PurchaseOrderEvent | 1:N | no | |
| PurchaseOrder → TransportEvent | 1:N | optional | |
| (SKU, Location) → Inventory | 1:1 per as_of_date | no | |
| Location(PLANT) → ProductionPlan | 1:N | only for make-SKUs | |
| (SKU, Location) → Shortage | 1:N | | episodes |
| Shortage → MitigationOption | 1:N | ≥ 1 | |
| Shortage ↔ source records | N:M (`ShortageCause`) | ≥ 1 | traceability |
| PlanRun → Shortage | 1:N | | |

### 4.6 Actor ↔ data mapping (R-007)

| Actor | Produces / consumes |
|---|---|
| Supplier | `SupplierCapacity`, PO confirmation + ETA events |
| Planner | Reviews `Shortage`, approves `MitigationOption` (`MitigationEvent.actor_role=PLANNER`) |
| Carrier / warehouse operator | `TransportEvent`, `InventoryEvent` (receipts) |
| Logistics analyst | Lead-time variability, transport-delay analysis views |
| Operations manager | KPI dashboard, high-value approvals |

### 4.7 Schema registry design

One declarative registry (Pydantic models + YAML/enum metadata) holds for **every field**: `type`, `required`, `allowed_values`, `unit`, `unique`, `validation_rule`, `fk`, `derived_from`. From it we generate: SQL DDL (with PK/FK/CHECK), the **data dictionary** (R-025, no empty cell enforced by a test), validator rules, and docs. This guarantees dictionary ⇄ DDL ⇄ validators never drift.

---

## 5. Planning workflow (demand → shortage → mitigation)

Weekly buckets `t = 1..52` (ISO `2026W01…W52`), grain = (SKU, Location). All quantities in base UoM.

### Stage 0 — Load & data-quality gate (the "exception path")
Before any netting, run detectors (these are also the engine side of the five edge cases):
* Inbound **duplicate** detection (§6.1) → exclude duplicates from supply, raise finding.
* **UoM** normalisation check: `qty_base == order_qty × factor`; missing factor → finding (§6.5).
* **Lead-time** presence check per (supplier, SKU[, location]) (§6.4).
* **Capacity ledger** check (§6.3).
* **Substitute approval** check (§6.2).
Findings are written to a `DataQualityFinding` output (run-scoped, no effect on source tables). The engine **never silently "fixes"** source data; it excludes/flags and records the decision.

### Stage 1 — Gross requirements
`gross_t = forecast_qty(sku, loc, t)` + `dependent_t` (components only), where
`dependent_t(component, plant) = Σ_parent planned_qty(parent, plant, t) × BOMLine.qty_per × (1 + scrap_pct)`.
Process finished goods first, then components (low-level-code order) so component demand depends on the capacity-limited production plan.

### Stage 2 — Opening position (seed on-hand)
`opening_1 = on_hand_qty − allocated_qty − quality_hold_qty` (= `available_qty`). For `t > 1`, `opening_t = closing_{t−1}`.

### Stage 3 — Scheduled receipts (inbound)
For every **open** PO (`PLANNED/CONFIRMED/IN_TRANSIT/DELAYED`, not duplicate-flagged):
`effective_eta = max(promised_date, eta_date)` where `eta_date = promised_date + Σ delay_days` from `PurchaseOrderEvent/TransportEvent` (so transport delays shift receipts right).
`receipt_week = isoweek(effective_eta)`; `receipts_t = Σ qty_base` of POs with `receipt_week = t`.
`RECEIVED` POs are **not** counted (already in on-hand → prevents double counting). `CANCELLED` ignored.

### Stage 4 — Production receipts
`production_t = ProductionPlan.planned_qty` (status ∈ PLANNED/FIRMED/RELEASED) for (finished SKU, plant, t), **capped** so that `Σ required_hours ≤ ProductionCapacity.available_hours(work_center, t)` and rounded to `lot_size`. Any cut-back quantity is remembered for cause attribution (`PRODUCTION_CAPACITY`).

### Stage 5 — Projected available balance (PAB)
```
closing_t = opening_t + receipts_t + production_t − gross_t
```
Reconciliation identity (R-041), stored in `ProjectedBalance` and asserted by test: `closing_t − (opening_t + receipts_t + production_t − gross_t) = 0` and `opening_t = closing_{t−1}` for all t, all chains, **exact** (integer quantities or fixed-precision decimals — no float drift).

### Stage 6 — Shortage detection
* `target_t = safety_stock_qty`.
* Week t is short if `closing_t < target_t`; type = `STOCKOUT` if `closing_t < 0`, else `SAFETY_STOCK_BREACH`.
* Group consecutive short weeks into an **episode** → one `Shortage`; `shortage_qty = max_t (target_t − closing_t)`; `need_by_date` = Monday of first short week; `value_at_risk = shortage_qty × unit_price`.
* If a data-quality blocker applies (e.g., missing lead time) → `status = NEEDS_REVIEW`.

### Stage 7 — Cause attribution (R-042)
For each shortage, evaluate rules in fixed order against **source records**, each producing a `ShortageCause` row (`cause_code`, `contribution_qty`, `source_table/source_id`, human-readable `explanation`):

| Code | Rule (documented, deterministic) | Evidence |
|---|---|---|
| `DEMAND_SPIKE` | Σ over weeks ≤ short week of `max(0, forecast − baseline_run_rate)` where baseline = median of the SKU-location's forecast | `ForecastDemand` ids |
| `INBOUND_LATE_TRANSPORT` | Σ qty of POs whose `promised_week ≤ short week < effective_receipt_week` due to transport delay events | `PurchaseOrder`, `TransportEvent` ids |
| `INBOUND_LATE_SUPPLIER` | Same but delay from supplier ETA revisions | `PurchaseOrderEvent` ids |
| `SUPPLIER_CAPACITY` | Required order not placeable because supplier-family `utilisation ≥ 95%` in order week | `SupplierCapacity`, ledger rows |
| `INSUFFICIENT_LEAD_TIME` | `need_by_date − as_of_date < total_lead_days` for every sourcing option | `LeadTime` id |
| `NO_INBOUND_PLANNED` | Deficit with no open PO or plan covering the week | `Inventory`, `SKUSupplier` ids |
| `PRODUCTION_CAPACITY` | Cut-back qty from Stage 4 | `ProductionCapacity`, `ProductionPlan` ids |
| `COMPONENT_SHORTAGE` | Parent plan reduced because component short | child `Shortage` id |
| `DATA_ISSUE_*` | Findings from Stage 0 (double count, UoM, missing lead time) | PO/LeadTime ids |

Contributions are allocated **waterfall-style** in the order above, capped so `Σ contribution ≤ shortage_qty`; any remainder is labelled `RESIDUAL_FORECAST_ERROR_OR_UNKNOWN` and counted as a **quality metric** (target: residual share < 5 %). A shortage with **zero** cause rows is a hard test failure.

### Stage 8 — Prioritisation
```
priority_score = 100 × ( 0.35·urgency + 0.30·value_at_risk_norm + 0.20·criticality_weight + 0.15·service_gap )
urgency = 1 − min(weeks_to_shortage, 12)/12
criticality_weight: A=1.0, B=0.6, C=0.3
```
Rank by score (ties → earlier need-by date → `shortage_id`). Weights live in config and are recorded on `PlanRun`.

### Stage 9 — Candidate mitigations (R-043, R-044)
For each shortage, generate candidates; each is checked **in this order** and the outcome is stored (not discarded):

1. **Policy check** — supplier `ACTIVE` and in `SKUSupplier` (approved); substitute `approval_status = APPROVED` and within effective dates; expedite premium ≤ policy cap (e.g. 25 %); transfer must not push donor below *its* safety stock; production within capacity hours; spend ≤ approval threshold (above → "needs ops-manager approval" flag).
2. **Lead-time check** — `earliest_arrival = as_of + lead_days (+ expedite reduction) ≤ need_by` → on time; otherwise `weeks_late` computed. **Missing lead time → option blocked (`lead_time_check = MISSING`)**; no silent default.
3. **Capacity check** — `qty ≤ remaining_supplier_capacity(week)` from `SupplierCapacityLedger`, after MOQ/multiple rounding: `qty = max(MOQ, ceil(need / multiple) × multiple)`; qty reduced to remaining capacity → option becomes partial (`covered_qty < need`).
4. **Cost** = `qty × unit_cost × (1 + penalty/premium) + freight + excess_cost` (excess = rounded-up units beyond need × unit_cost × holding factor); `cost_delta_vs_baseline` relative to the cheapest feasible option.
5. **Service impact** = `fill_rate_pct = covered_qty / shortage_qty`, `weeks_late`, `service_level_after`.
6. **Ranking** = lexicographic: on-time & policy-pass first → highest fill rate → lowest cost; `is_recommendable = policy_check = PASS ∧ capacity_check = PASS ∧ lead_time_check ≠ MISSING`.
7. Always include a **`PARTIAL_FILL_BACKORDER`** option so at least one alternative with a cost/service trade-off exists (R-044). Option IDs `MIT-<shortage-id>-01…NN` in deterministic rank order of generation (IDs immutable once assigned; re-ranking changes `rank`, not the ID).

### Stage 10 — Persist (history)
Insert `ShortageEvent(DETECTED→ANALYZED→MITIGATION_PROPOSED)` and `MitigationEvent(PROPOSED)` rows; never update earlier rows. Record `PlanRun` (as_of, parameters hash, engine version, seed).

### Calculation worked-example (goes in README; used as golden unit test)
SKU-000001 @ LOC-001: on_hand 120, allocated 20, hold 0 → opening 100; forecast W01..W04 = 40, 60, 90, 50; PO 80 EA ETA W02 (promised W02, transport delay +9 d → effective W03). Closing: W01 = 60; W02 = 0; W03 = 0 + 80 − 90 = −10; W04 = −60. Safety stock 20 → shortage episode starts W02 (SS breach: 0 < 20), STOCKOUT from W03; `shortage_qty = 20 − (−60) = 80`; causes: `INBOUND_LATE_TRANSPORT` 80 (PO + TransportEvent). Hand-computed values are asserted in tests.

---

## 6. The five mandatory edge cases

**Common injection protocol (R-029, R-040):** (1) generate and validate the **clean baseline**; (2) pick targets by a seeded, documented selection rule (e.g., "k-th eligible PO by sorted ID"); (3) mutate **only** the target rows (or add rows referencing them); (4) write one `ground_truth` row per injection; (5) re-run the validator → it must flag **exactly** the labelled set (no more, no fewer); (6) test "blast radius": hash of all non-target rows before vs. after injection is identical.

`ground_truth` schema: `label_id`, `label_class` {ANOMALY, SCENARIO}, `issue_type`, `entity`, `record_id`, `related_record_ids`, `injected_field`, `original_value`, `injected_value`, `expected_detection`, `expected_decision`, `impact_qty`, `rule_ref`, `seed`. Volume: ≥ N per issue type (scales with profile; **min 3 per type** in starter, ~25–50 in full) so detection metrics are meaningful, including one boundary case per type.

### 6.1 Inbound inventory counted twice — `issue_type = INBOUND_DOUBLE_COUNT`
* **Injection (variant A, primary):** copy an open PO into a *new* PO ID (new counter value) with same `supplier_id, sku_id, ship_to_location_id, order_qty, promised_date, supplier_ref_no`. **Variant B:** a PO that has a `RECEIVED` event and an `InventoryEvent(RECEIPT)` already reflected in `on_hand_qty` but whose header is left `IN_TRANSIT` in the open-inbound extract.
* **Effect if undetected:** PAB overstated by `qty_base` from the receipt week onward → shortage hidden.
* **Engine:** Stage-0 dedupe key `(supplier, sku, ship_to, qty_base, promised_date, supplier_ref_no)`; variant B via PO↔InventoryEvent match. Duplicate excluded from supply; PAB with/without shown; finding `INBOUND_DOUBLE_COUNT` with both PO IDs.
* **Ground truth:** both PO IDs, `impact_qty`, `expected_decision = EXCLUDE_DUPLICATE`.
* **Tests:** (a) detector finds exactly the labelled pairs; (b) PAB of affected chain equals hand-computed value *without* duplicate; (c) shortage that appears after exclusion carries `DATA_ISSUE_DOUBLE_COUNT` cause; (d) near-duplicate (same SKU/qty but different supplier_ref) is **not** flagged (boundary/false-positive guard).

### 6.2 Substitute SKU not approved — `issue_type = SUBSTITUTE_NOT_APPROVED`
* **Injection:** a `SKUSubstitute` row with `approval_status ∈ {PENDING, REJECTED, EXPIRED}` (or date outside effective window) paired with a candidate mitigation of type `SUBSTITUTE_SKU` that references it (stored with `policy_check = FAIL`, `is_recommendable = false`, `policy_reason = SUBSTITUTE_NOT_APPROVED`). Valid approved substitutes exist in baseline (satisfying "substitute SKUs" variation).
* **Engine:** policy check rejects non-approved/expired substitutes; the option is retained for audit, never recommended or executed.
* **Ground truth:** `record_id = MIT-…`, `related = [SKUSubstitute key]`, `expected_decision = REJECT_OPTION`.
* **Tests:** no `is_recommendable` option references a non-approved substitute (global invariant); the labelled options are exactly those with policy FAIL for this reason; changing the substitute to APPROVED in a copy flips the decision (what-if/boundary); expired-yesterday vs. valid-today boundary.

### 6.3 Supplier capacity exceeded — `issue_type = SUPPLIER_CAPACITY_EXCEEDED`
* **Injection:** for a chosen (supplier, product_family, week) add/inflate PO quantities so `Σ qty_base > weekly_capacity_qty`; baseline supplier-weeks all stay ≤ capacity (generator uses a capacity ledger when assigning POs, constrained suppliers at 90–100 %). Include boundary: exactly = capacity (**not** an anomaly) and capacity + 1 unit (anomaly).
* **Engine:** `SupplierCapacityLedger.utilisation_pct > 100` → finding; excess qty treated as **at-risk** (not counted as reliable supply in strict mode, flagged in default mode) and `SUPPLIER_CAPACITY` cause; no mitigation may use more than `remaining_qty`.
* **Ground truth:** supplier-week key, PO IDs, `impact_qty = committed − capacity`.
* **Tests:** ledger flags exactly labelled weeks; `=capacity` not flagged; mitigation capacity validator (R-043) passes for all recommendable options; capacity change creates a **new effective-dated row** (history preserved).

### 6.4 Shortage calculated without lead time — `issue_type = SHORTAGE_MISSING_LEAD_TIME`
* **Injection:** remove (or never create / set effective window to not cover `as_of`) the `LeadTime` row for selected (supplier, sku[, location]) pairs that sit on a chain with a genuine shortage. Implemented by *not generating* a row (not by corrupting one) and logging the omitted key to ground truth.
* **Engine:** lead-time lookup falls back (location-specific → default → none). If none: shortage still **detected** (demand/inventory math doesn't need it) but `status = NEEDS_REVIEW`, cause `DATA_ISSUE_MISSING_LEAD_TIME`, all supplier-based mitigations get `lead_time_check = MISSING`, `is_recommendable = false`; **no assumed default lead time** is used silently (an optional documented fallback is only available behind a flag and is labelled in the output).
* **Ground truth:** shortage key + the missing LeadTime key, `expected_decision = FLAG_AND_BLOCK_MITIGATION`.
* **Tests:** engine flags exactly the labelled shortages; none of them has a recommendable supplier mitigation; adding the missing row (copy) clears the flag; boundary: lead time = 0 days is valid (not "missing").

### 6.5 Units-of-measure mismatch — `issue_type = UOM_MISMATCH`
* **Injection:** a PO (or `SupplierCapacity`) where `order_uom ≠ sku.base_uom` (e.g., ordered in CASE) and the stored `qty_base` was **not** converted (equals `order_qty`), or the conversion factor row is missing. Baseline POs in non-base UoM are correctly converted (so CASE/PALLET usage is normal).
* **Effect if undetected:** supply off by the factor (e.g., 12×) → PAB wrong.
* **Engine:** Stage-0 recompute `qty_base = order_qty × factor(sku, order_uom → base)`; mismatch → use recomputed value, raise finding; missing factor → exclude from supply, flag `NEEDS_REVIEW`.
* **Ground truth:** PO ID, `original_value` (recorded qty_base), `injected_value`, correct value, factor.
* **Tests:** recomputed supply equals ground-truth correct value; arithmetic validator flags exactly labelled POs; factor = 1 (EA→EA) boundary not flagged; PAB reconciles with the corrected value.

### 6.6 Detection scoring (evaluation metric, R-005/R-006)
`evaluate` compares engine findings with ground truth **after** the engine run (ground truth is read only here): per `issue_type` precision, recall, F1 → must be 1.0 on seeded data. Printed in the validation summary.

---

## 7. Synthetic data: generation, validation, ground truth, reproducibility

### 7.1 Scale profiles (one generator, R-028)

| Parameter | `tiny` (unit tests) | `starter` (demo/CI) | `full` (PDF baseline) |
|---|---|---|---|
| SKUs | 40 | 300 | **3,000** |
| Locations | 5 | 10 | **50** |
| Weeks | 52 | 52 | **52** |
| Suppliers | 8 | 50 | **500** |
| Inbound POs | 150 | 1,000 | **10,000** |
| Assortment density | 0.6 | 0.3 | ~0.10 (D2) |
| Seed | 20261022 | 20261022 | **20261022** |
| Edge cases per type | 2 | ≥ 3 | ~25–50 |

Same code path; only a YAML profile changes counts. Counts are *parameters*, never hard-coded; scenario shares (spike %, constrained-supplier %, delay %) are also profile parameters.

### 7.2 Generation DAG (dependency order, R-026)
```
UnitOfMeasure, Location, Carrier, Supplier
   → SKU → UoMConversion → SKULocation → SKUSupplier → SKUSubstitute (approved + pending/rejected seeds)
   → BillOfMaterial/BOMLine → WorkCenter → ProductionCapacity
   → SupplierCapacity → LeadTime
   → ForecastDemand (base + seasonality + spikes)
   → Inventory (opening on-hand, safety stock from demand variability)
   → PurchaseOrder (+ capacity ledger) → PurchaseOrderEvent / TransportEvent / InventoryEvent
   → ProductionPlan (+ events)
   → [validate clean baseline]
   → inject edge cases → ground_truth
   → planning engine → ProjectedBalance, Shortage, ShortageCause, MitigationOption, events
   → validate → export → checksum
```
Master data first, dependents only reference existing parent IDs (R-008/R-009).

### 7.3 Realism requirements (Area A)
* **Demand:** SKU volume ~ Pareto/lognormal (A/B/C classes derived *from* the volume); weekly seasonality (sinusoid + trend); intermittent (Poisson/zero-inflated) demand for slow movers, negative-binomial for fast; promo and **spike** weeks (spike ≈ 2–4× baseline for ~3–5 % of SKU-weeks, labelled `SCENARIO`); location scale factors by type.
* **Suppliers:** tiered; capacity lognormal by size; **constrained suppliers** (~10–15 %) run at 90–100 % utilisation; reliability varies (drives delay probability).
* **Lead times:** lognormal by region/mode (e.g., ROAD 3–10 d, SEA 25–50 d), p90 > mean; production_days per supplier.
* **Transport delays:** ~8–15 % of POs have `TransportEvent(DELAYED)` with reason mix; delay days geometric/lognormal; labelled `SCENARIO`.
* **MOQ/multiples** by family; case pack conversions (EA/CASE/PALLET); price lognormal with supplier markup.
* **Substitutes:** ~10–15 % of SKUs have 1–2 substitutes within the same family (ratio 1.0–1.2), mostly APPROVED.
* **Inventory:** on-hand ≈ lognormal around k× weekly demand; safety stock = z × σ × √(lead-time weeks); a share of chains deliberately tight so shortages arise **from the rules**, not random flags (R-012).
* **POs:** quantity sized to cover forecast over lead time ± MOQ rounding; order dates = need-by − lead time; statuses from dates vs. `as_of_date` (D7).
* **Production:** make-SKUs at plants with BOM depth 1–2, weekly capacity ~85–110 % of average demand (some overloaded weeks).

### 7.4 Derived-value policy (Step 6, R-030)
Never independently randomised: `qty_base, total_cost, total_lead_days, available_qty, required_hours, eta_date, PO status, Shortage status, shortage_qty, priority_score, ProjectedBalance.*, utilisation_pct, criticality (ABC), fill_rate_pct, total_cost (mitigation)`. Each has a `derived_from` entry in the registry and a recompute test.

### 7.5 Ground truth firewall (Step 7, Area F)
* Written to `data/<profile>/ground_truth/ground_truth.csv` (+ `.json`) — a **separate folder**.
* Pipeline code: generator/injector may write it; planning engine, risk model, assistant and UI **cannot read it** (engine modules never import the path; reading it only occurs in `evaluate`).
* Tests: (1) no input table has a column named like `issue_type|ground_truth|label|is_anomaly`; (2) static check: engine/ML packages don't reference ground-truth paths; (3) ML features list is an explicit allow-list from input tables; (4) engine output is byte-identical if `ground_truth/` is deleted.

### 7.6 Validation suite (Step 8, R-032/R-045/R-046)

| Check | Rule |
|---|---|
| PK uniqueness | Every table; composite keys for bridges |
| FK integrity | Every FK exists in parent (incl. optional FK: NULL allowed only where documented) |
| ID pattern & recompute | Regexes (R-019–R-023); `demand_id`, `mitigation_id` recomputed from FKs |
| Enums | Allowed values from registry |
| Date ordering | order ≤ promised/eta ≤ receipt; effective_from < effective_to; no events after `as_of_date`; event dates monotonic per PO |
| Arithmetic | `qty_base`, `total_cost`, `total_lead_days`, `available_qty`, PAB identity, ledger utilisation, shortage_qty, mitigation cost/fill rate |
| Lifecycle | Header status == last event; each transition ∈ allowed map; terminal states have no later events |
| Duplicates | Natural-key duplicates (PO dedupe key, demand sku-loc-week, capacity overlap windows) |
| Acceptance | R-042 (causes ≥ 1), R-043 (policy+capacity), R-044 (≥ 2 alternatives w/ cost & service) |
| Labelled-issue reconciliation | Validator failures == ground-truth set exactly (clean baseline: zero failures) |
| **Negative tests** | Mutate a clean dataset (break a FK, swap a date, corrupt a status) → validator must catch it |

Outputs `validation_summary.md/json`: per-check pass/fail counts, row counts, examples of labelled failures.

### 7.7 Export & documentation (Step 9, R-033)
```
data/<profile>/
  csv/<table>.csv(.gz, chunked if >50MB)    json/<table>.json (starter only if size permits)
  sql/seed.sql + schema.sql (SQLite-compatible)  ground_truth/ground_truth.csv|json
  docs/data_dictionary.md|csv  docs/validation_summary.md|json
  manifest.json   # row counts, SHA-256, generator command, seed, versions, profile, as_of_date, source manifest
  SOURCE_MANIFEST.md  # "synthetic; no external data" (+ schema-inspiration note)
```
`manifest.json` stores the exact generator command and fixed seed. README repeats it.

### 7.8 Reproducibility (Step 10, R-034)
* **RNG:** `numpy.random.SeedSequence(20261022)` spawned **per table/stage by stable name** (not call order) → adding a table can't shift other tables' streams.
* No `datetime.now()`, `uuid4`, `hash()` of strings, unordered set/dict iteration; all outputs sorted by PK; fixed CSV dialect (UTF-8, `\n`, quoting, fixed decimal/float format); decimals rounded with fixed rules; pinned dependency versions (`requirements.lock`); `PYTHONHASHSEED` irrelevant by design.
* `repro` command: generate twice into separate dirs → compare **row counts and SHA-256 of every file** → write `reproducibility_report.md` (PASS/FAIL table). Also runs in CI on `starter`, and once on `full` before submission. Also tested: different seed → different checksums but identical validation pass (proves seed matters, validators don't depend on it).
* ID stability: IDs are counters assigned in sorted deterministic order, so regenerated IDs are identical.

---

## 8. Technology stack

| Layer | Choice | Reason |
|---|---|---|
| Language | **Python 3.12/3.13** (3.13 is installed) | Data + planning logic, fastest to build in 2 days |
| Data | **pandas + numpy** (vectorised generation), **pyarrow** optional | Speed on ~1–2 M rows |
| Validation/analytics | **DuckDB** | Fast SQL joins/reconciliation over millions of rows |
| Schema | **Pydantic v2** + YAML registry | Dictionary/DDL/validators from one source |
| Storage / SQL seed | **SQLite** (portable, zero setup) | "SQL seed data" requirement; any reviewer can run it |
| CLI | **Typer** | `generate/validate/plan/repro/evaluate/export` |
| API [O] | **FastAPI** | Thin read API for UI/assistant |
| UI [O] | **Streamlit** (+ Plotly) | Quickest path to an actionable planner dashboard (vs. React: too slow for the deadline) |
| ML [O] | **scikit-learn** (logistic regression / gradient boosting) | Explainable, small |
| AI assistant [O] | **Anthropic Claude API** (tool-use over the read-only API; model `claude-sonnet-5-5`) with deterministic template fallback when no key | Grounded Q&A; works offline |
| Testing | **pytest**, **hypothesis** (property tests), pytest-cov | |
| Quality | **ruff**, **mypy** (lenient), pre-commit | |
| CI | **GitHub Actions** (tiny + starter tests, repro on starter) | Auditability |
| Packaging | `pyproject.toml`, `make`/`tasks.ps1`, `.env.example` | Easy for another person to run |

Windows-friendly: all commands also provided as PowerShell snippets.

---

## 9. Optional enhancements [O]

**Hard rule:** enhancements are implemented as *separate packages* that **read** planning outputs; they never alter generator code, IDs, baseline exports, validators or the planning rules. A CI job runs the full mandatory suite with enhancement packages removed to prove independence.

### 9.1 AI planning assistant (M13)
* Read-only tool-use over the API/SQLite: `get_shortage(id)`, `explain_shortage`, `list_top_shortages`, `compare_mitigations`, `supplier_scorecard`, `run_whatif`.
* Every answer must cite IDs (shortage/PO/mitigation) from tool results — **no free-form numbers**; refuse if no evidence. Answers include a "sources" footer.
* No write actions without explicit user confirmation; cannot read `ground_truth`.
* Offline fallback: templated explanations from `ShortageCause` rows. Tests: mocked LLM; assert cited IDs exist; assert refusal on unknown IDs.

### 9.2 What-if scenario simulator (M14)
* Scenario = parameter overlay (`demand_multiplier` per family/week range, `supplier_capacity_factor`, `lead_time_delta_days`, `supplier_disabled`, `approve_substitute`, `expedite_allowed`, `add_inventory`).
* Runs the **same engine** on an in-memory overlay → new `PlanRun` (`scenario_id`), baseline tables untouched; outputs delta table (shortages added/removed, qty, cost, service).
* Tests: zero-change scenario ⇒ identical results; monotonicity (demand ↑ never reduces shortages); baseline checksum unchanged afterwards.

### 9.3 Supplier performance intelligence (M15)
* Derived only from PO/transport events: OTIF %, avg & p90 delay, lead-time variability (CV), fill rate, capacity utilisation, cancel rate, **reliability score** (documented weighted formula), tier/risk band, trend by quarter; link to shortages caused (`INBOUND_LATE_*`). Used to inform mitigation ranking only through a documented, optional weight.

### 9.4 Automated replenishment (M16)
* Policy engine (min/max or (s,S) with safety stock) → **proposals** (`ReplenishmentProposal`, own ID `RPL-…`) honouring MOQ/multiple, capacity ledger, lead time, approved suppliers, budget caps; approval workflow with events. Proposals are **not** written into the exported baseline PO table (PO counter `PO-2026-000001…010000` stays intact); approval would mint the next counter in the runtime DB only.

### 9.5 Risk prediction (M17)
* Targets: (a) P(shortage within next 4 weeks) per SKU-location, (b) P(PO delayed > 3 days).
* Features strictly from input tables (demand variability, cover weeks, supplier reliability, lead-time CV, utilisation, open-PO lateness). **Labels from the engine's derived shortages, never from `ground_truth.csv`.** Time-based split (train W01–W30, test W31–W52) to avoid leakage; report AUC/PR-AUC, calibration; feature importance for explainability. Allow-list test of feature columns.

---

## 10. Architecture (starter vs. full)

```
                ┌─────────────────────────────────────────────────────────┐
 profiles/*.yaml│  config (scale, seed, as_of, scenario shares, policies) │
                └──────────────┬──────────────────────────────────────────┘
                               ▼
   ┌──────────────┐   ┌────────────────┐   ┌────────────┐   ┌───────────┐
   │ schema       │──▶│ generator      │──▶│ validator  │──▶│ exporter  │
   │ registry     │   │ (baseline →    │   │ (DuckDB)   │   │ CSV/JSON/ │
   │ (M1,M2)      │   │  inject → GT)  │   └────────────┘   │ SQL/docs  │
   └──────┬───────┘   └──────┬─────────┘                    └─────┬─────┘
          │                  │ ground_truth/ (isolated)           ▼
          │                  ▼                              data/<profile>/
          │           input tables ─────────▶ planning engine ──▶ outputs
          │                                   (pure functions, deterministic)
          │                                          │
          ▼                                          ▼
     DDL/dictionary                  SQLite/DuckDB  ──▶ FastAPI ──▶ Streamlit
                                              ▲            ▲
                         what-if overlay ─────┘   assistant / ML / supplier intel
                                     evaluate (only module that reads ground_truth)
```

**Scalability decisions**
* Vectorised pandas/numpy generation; chunked writes; DuckDB for validation so 1 M+ rows validate in seconds.
* Engine is a pure function `(tables, config) → outputs`; per-(SKU,location) chains are independent except BOM/transfer links → can run grouped/vectorised (groupby cumulative sums) and parallelised by location if needed.
* Profile-driven: `tiny` for unit tests, `starter` for CI/demo, `full` for submission; identical code paths, so a bug found on starter is the same bug in full.
* Storage portable (SQLite) with DuckDB attach; Postgres swap possible later (DDL generated from registry).
* Repo-size strategy (D3): chunked/gz exports + checksums; full dataset regenerable by one command.
* Layering: `core` (schema/ID/config) ← `datagen` ← `validate` ← `planning` ← `services` (api/ui/assistant/ml/whatif). Dependencies point one way; enhancements depend on core+planning, not the reverse.

**Proposed repo layout**
```
oryva-nexus/
  PROJECT_PLAN.md  README.md  LICENSE  pyproject.toml  requirements.lock  .env.example
  profiles/ tiny.yaml starter.yaml full.yaml  policies.yaml
  src/oryva/
    core/ (schema_registry, ids, config, calendar, uom)
    datagen/ (master, demand, inventory, suppliers, orders, production, injectors)
    validate/ (rules, runner, report)
    export/ (csv, json, sql, dictionary, manifest)
    planning/ (dq_gate, netting, shortage, causes, priority, mitigation, events, engine)
    evaluate/ (metrics, ground_truth_scoring)
    services/ (api, ui, assistant, whatif, supplier_intel, replenishment, risk)   # [O]
    cli.py
  tests/ (unit, integration, negative, property, repro)
  data/starter/…  data/full/…
  docs/ (architecture.md, data_dictionary.md, decisions.md)
```

---

## 11. Testing & evaluation strategy

### 11.1 Test layers
1. **Unit** — ID builders/regex; calendar (ISO week, 2026W01 = 2025-12-29, W52/53 boundary); UoM conversion; each planning stage; cause rules; priority formula; MOQ/multiple rounding.
2. **Golden** — hand-computed `tiny` fixture (the worked example in §5) asserting exact PAB, shortage, causes, mitigation costs.
3. **Property-based (hypothesis)** — PAB identity holds for arbitrary demand/receipt vectors; shortage_qty ≥ 0; `Σ cause ≤ shortage_qty`; mitigation qty respects MOQ/multiple/capacity; rank order deterministic.
4. **Validator negative tests** — each rule has a mutation test proving it fails when it should.
5. **Edge-case tests** — §6 per type: injection → label → detection → decision, plus boundary and false-positive guards, plus blast-radius hash test.
6. **Reproducibility** — twice-run row counts + SHA-256 on `tiny` (unit) / `starter` (CI) / `full` (pre-submission); different-seed sanity check.
7. **Firewall tests** — §7.5.
8. **Integration** — `generate → validate → plan → evaluate` end-to-end on `starter`; fresh-clone smoke test from README commands.
9. **Enhancement tests** — separate, plus "mandatory suite passes without enhancements".

### 11.2 Coverage areas mapped to PDF §8 (E: normal/boundary/failure/exception)
Normal (clean chain), boundary (PAB = 0 / = safety stock, capacity = limit, lead time = 0, MOQ = need, week 52 → W01 year edge), failure (missing parent, invalid enum, bad date), exception (5 edge cases + NEEDS_REVIEW path).

### 11.3 Metrics reported (R-005/R-006)
Validation pass rate per check; edge-case precision/recall/F1 per type; % shortages with ≥1 cause and residual-unknown share; % shortages with ≥2 alternatives; fill rate & cost of recommended plan vs. do-nothing; PAB residual (must be 0); reproducibility match %; distribution summaries (A); [O] risk model AUC, supplier OTIF distribution.

---

## 12. Prioritised development checklist

**Priority key:** **P0** = mandatory, blocks submission · P1 = mandatory-adjacent quality/documentation · P2 = valuable enhancement · P3 = nice-to-have.

### P0 — Mandatory (must be done and verified)

- [ ] **Repo & tooling:** git init, `pyproject.toml`, pytest, ruff, CI skeleton, MIT license, `.gitignore`. (R-050)
- [ ] **Schema registry** for all 11 core + supporting tables with every field's type/required/allowed values/units/uniqueness/validation rule/FK. (R-013–R-016, R-025)
- [ ] **ID service** with regexes and builders: SKU, DEM, PO, SHORT, MIT (+ LOC/SUP/etc.). (R-019–R-024)
- [ ] **Calendar utility** (ISO weeks, `2026W01` mapping, as_of). (D7)
- [ ] **Config/profiles** `tiny/starter/full`, seed 20261022, all counts parameterised. (R-028)
- [ ] **Generator – master data:** UoM, Location, Supplier, Carrier, SKU, conversions, SKULocation, SKUSupplier, SKUSubstitute, BOM, WorkCenter. (R-008, R-026)
- [ ] **Generator – parameters:** SupplierCapacity, LeadTime, ProductionCapacity. 
- [ ] **Generator – demand:** weekly SKU-location forecast incl. spikes, seasonality, intermittent. (R-010, R-028)
- [ ] **Generator – inventory:** on-hand, allocated, safety stock.
- [ ] **Generator – POs + events + transport delays** with capacity ledger; 10,000 POs at full scale. (R-009, R-011, R-028)
- [ ] **Generator – ProductionPlan + events.**
- [ ] **Validator** (PK/FK/enum/date/arithmetic/lifecycle/duplicate) + negative tests; clean baseline = zero failures. (R-032, R-045, R-046)
- [ ] **Planning engine:** DQ gate, UoM normalisation, scheduled receipts, production, PAB, `ProjectedBalance`. (R-010, R-041)
- [ ] **Shortage detection + cause attribution + priority scoring.** (R-002, R-042)
- [ ] **Mitigation generator** with policy/lead-time/capacity checks, cost & service trade-offs, ≥2 alternatives, deterministic IDs. (R-043, R-044, R-023)
- [ ] **Event persistence** for PO/Shortage/Mitigation (append-only, no overwrite). (R-011, R-017)
- [ ] **Edge-case injectors ×5** (two-pass, labelled, traceable) + `ground_truth.csv/json` in isolated folder. (R-029, R-031, R-035–R-040)
- [ ] **Engine detectors for the five edge cases** + `evaluate` precision/recall vs. ground truth. (R-006)
- [ ] **Ground-truth firewall tests.** (R-031, Area F)
- [ ] **Exporter:** CSV/JSON/SQL seed, data dictionary, manifest with checksums, generator command, seed, source manifest, validation summary. (R-033, R-053)
- [ ] **Reproducibility harness** + report on starter **and** full. (R-034, R-054)
- [ ] **Full dataset run** (3,000/50/52/500/10,000), validated, size-split if needed. (R-028, D2, D3)
- [ ] **README** (install/configure/run, generator command, seed, test commands, outputs, design decisions, worked example). (R-051)
- [ ] **Validation output committed** (summary + test results). (R-052)
- [ ] **Fresh-clone dry run** on a clean folder following README only. (R-056)
- [ ] **Push to public GitHub + submit form before 25 Nov 2026 EOD.** (R-050, R-055, R-057)

### P1 — Quality & documentation
- [ ] Distribution report (histograms/summary of demand, lead times, utilisation) for Area A.
- [ ] `docs/decisions.md` recording D1–D13.
- [ ] Minimal CLI-printed exception report (decisions & exceptions exposed). (R-003)
- [ ] Actor-role views as report sections (planner / analyst / ops manager). (R-007)
- [ ] Hypothesis property tests; coverage ≥ 80 % on `planning/` and `validate/`.
- [ ] Architecture diagram in docs.

### P2 — Enhancements (only after all P0 green; separate packages, mandatory suite must remain green)
- [ ] Streamlit dashboard: ranked shortages, drill-down to causes/evidence, mitigation trade-off comparison. (M12)
- [ ] What-if simulator. (M14)
- [ ] Supplier performance intelligence. (M15)
- [ ] Automated replenishment proposals. (M16)

### P3 — Stretch
- [ ] Risk prediction model with time-split validation. (M17)
- [ ] AI planning assistant (grounded tool-use, offline fallback). (M13)
- [ ] FastAPI read API, Postgres DDL variant, Docker.

### Definition of Done (project complete)
All R-001…R-057 green; `pytest` passes; `validate` shows zero unexpected failures and flags exactly the labelled set; engine detectors score 1.0 on all five issue types; `repro` PASS on starter and full; README verified from a fresh clone; ground truth separate and firewall tests pass; repo public; form submitted.

### Suggested 2-day timeline (deadline 25 Nov EOD)
* **Day 1 (23 Nov):** tooling, registry, IDs, calendar, profiles, generator for all tables on `tiny`→`starter`, validator, first repro check.
* **Day 2 (24 Nov):** planning engine, shortages/causes/mitigations, five injections + detectors + evaluate, exporter, full-scale run + repro, README/docs.
* **25 Nov (buffer):** fresh-clone test, fix gaps, push, submit (aim to submit by midday, not EOD). Enhancements only if everything above is done.

---

## 13. First development tasks (in order)

1. **Initialise the repository & tooling** — `git init`, `pyproject.toml`, `src/oryva` layout, pytest + ruff, `.gitignore`, MIT license, GitHub Actions skeleton.
2. **Build the ID service** — builders + regex validators for `SKU-`, `DEM-…-2026Wnn`, `PO-2026-`, `SHORT-2026-`, `MIT-<shortage-id>-nn` (+ `LOC-`, `SUP-`), with unit tests (zero-padding, immutability, round-trip parse).
3. **Build the calendar utility** — ISO week ↔ `2026Wnn` ↔ Monday date, with W01 = 2025-12-29 and year-boundary tests.
4. **Create the schema registry** — define all 11 core + supporting entities with per-field type/required/allowed values/units/uniqueness/validation rule/FK/derived_from; emit DDL and `data_dictionary.md`; add the "no empty cell" completeness test.
5. **Create profiles & config loader** — `tiny/starter/full` YAML with seed 20261022, all counts and scenario shares as parameters; per-table `SeedSequence` spawning by stable name.
6. **Generate master data** (UoM, Location, Supplier, Carrier, SKU, conversions, SKULocation, SKUSupplier, SKUSubstitute, BOM, WorkCenter) on `tiny`, with PK/FK validator running from day one.
7. **Generate SupplierCapacity, LeadTime, ForecastDemand, Inventory, PurchaseOrder (+events, capacity ledger), ProductionPlan** in dependency order; get a clean baseline passing the full validator.
8. **Implement the planning engine core** (Stage 0–6: DQ gate, UoM, receipts, PAB, shortage episodes) with the hand-computed golden test.
9. **Add cause attribution, priority scoring and mitigation generation**, then the acceptance checks R-042/R-043/R-044.
10. **Implement the five edge-case injectors + ground_truth**, matching engine detectors, `evaluate`, blast-radius and firewall tests.
11. **Exporter + reproducibility harness**, then scale to `starter` and `full`; commit data, validation summary and reproducibility report.
12. **Write README and docs, fresh-clone test, push, submit.**
