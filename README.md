# ORYVA NEXUS — AI-powered Demand, Inventory & Supply Planning

End-to-end planning solution for the *ORYVA AI Student Technical Assignment* ("Demand, Inventory & Supply Planning"):

1. **Mandatory core** — reproducible synthetic data generator (3,000 SKUs / 50 locations / 52 weeks / 500 suppliers /
   10,000 inbound POs), a planning engine (projected available balance, shortages, evidence-linked causes, prioritisation,
   mitigations with cost/service trade-offs), the five labelled edge cases, ground truth, validation and reproducibility proof.
2. **Application** — a Streamlit planning cockpit (17 pages, roles, audit trail) on top of the planning outputs.
3. **Advanced modules** — grounded AI assistant, what-if simulator, supplier intelligence, automated replenishment,
   risk prediction and an optimisation engine. They only *read* planning outputs and never alter the mandatory pipeline.

Documents: [PROJECT_PLAN.md](PROJECT_PLAN.md) (blueprint) · [REQUIREMENTS_AUDIT.md](REQUIREMENTS_AUDIT.md) (strict audit against the PDF) ·
[FINAL_REPORT.md](FINAL_REPORT.md) · [docs/data_model.md](docs/data_model.md) · [docs/test_results.txt](docs/test_results.txt) ·
reproducibility: [full](docs/reproducibility_full.md), [starter](docs/reproducibility_starter.md) ·
independent audit evidence: [full](docs/audit_evidence_full.json), [starter](docs/audit_evidence_starter.json)

## 1. Install

Python ≥ 3.11 (developed on 3.13). The mandatory pipeline needs only `numpy`, `pandas`, `pyyaml`; the application and advanced
modules additionally need `streamlit`, `altair`, `tabulate` (extra `app`).

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
```

## 2. Configure

Everything is driven by a profile in [`profiles/`](profiles) — the **same generator** serves every scale:

| Profile | SKUs | Locations | Weeks | Suppliers | Inbound POs | Assortment density | Use |
|---|---|---|---|---|---|---|---|
| `tiny` | 60 | 6 | 52 | 12 | 250 | 0.50 | unit tests |
| `starter` | 300 | 10 | 52 | 50 | 1,000 | 0.30 | demo / CI |
| `full` | **3,000** | **50** | **52** | **500** | **10,000** | **0.10** | PDF baseline |

Fixed seed **`20261022`**. Any value can be overridden without editing files, e.g.
`python -m oryva generate --profile full --set assortment_density=0.15 --set seed=7`.
Planning policies (expedite premium cap, freight %, approval threshold, priority weights…) live in
[`profiles/policies.yaml`](profiles/policies.yaml) and are hashed onto every `PlanRun`.

## 3. Run

```powershell
# --- mandatory core -------------------------------------------------------------------------
python -m oryva generate --profile starter --out data/starter
python -m oryva generate --profile full    --out data/full          # exact generator command is recorded in manifest.json
python -m oryva validate  --data-dir data/starter                   # re-validate an export from disk + checksum check
python -m oryva repro     --profile starter --report docs/reproducibility_starter.md
python -m oryva repro     --profile full    --report docs/reproducibility_full.md
python -m oryva load-sql  --data-dir data/starter --db oryva.sqlite  # load the SQL seed (foreign-key check included)
python -m oryva report    --data-dir data/starter                    # role-based decision & exception report
python scripts/audit.py data/full docs/audit_evidence_full.json      # independent audit of an export
python -m pytest                                                     # whole test suite, run from the repository root
powershell -File scripts/fresh_clone_test.ps1                        # fresh-clone dry run (new venv, README steps, checksum compare)

# --- application ----------------------------------------------------------------------------
streamlit run app.py                                                 # http://localhost:8501
python scripts/ui_smoke.py full                                      # render every page headlessly against a dataset
```

The dashboard reads exported datasets from `data/<name>/` (`starter` by default; choose `full` in the sidebar).
Application state (users, audit log, approvals, draft orders, saved scenarios) lives in `data/app_state.sqlite` and
logs in `logs/oryva_app.log`; **the baseline CSV/SQL data is never written by the application.**

**Demo accounts** (local use only): `admin`, `ops`, `planner`, `analyst`, `warehouse`, `supplier` — password `oryva-demo`
unless the environment variable `ORYVA_DEMO_PASSWORD` is set before the first start. Passwords are stored as salted
PBKDF2-SHA256 hashes. Change them for any shared deployment.

| Role | Pages | May approve/modify |
|---|---|---|
| ADMIN, OPS_MANAGER | all | proposals (incl. above the spend threshold), mitigations, users (admin) |
| PLANNER | all | proposals ≤ threshold, mitigations, scenarios |
| LOGISTICS_ANALYST | analysis pages, reports, audit | save scenarios, export |
| CARRIER_WAREHOUSE | overview, inventory, purchase orders, reports | export |
| SUPPLIER | overview, suppliers, purchase orders (own records only) | – |

## 4. Mandatory core — what is produced (`data/<profile>/`)

| Path | Content |
|---|---|
| `csv/` | all 32 tables (tables above 100 k rows as deterministic `.csv.gz`) |
| `json/` | JSON export of every table (`.json.gz` above 200 k rows) |
| `sql/` | `schema.sql` (PK/FK DDL) + one `seed_<Table>.sql[.gz]` per table (SQLite-compatible) |
| `ground_truth/` | **`ground_truth.csv` / `.json` — separate from every input; never read by the engine or the application** |
| `docs/` | data dictionary (md + csv), validation summary, per-check CSV, evaluation JSON, role report |
| `manifest.json` | generator command, seed, parameters, row counts, SHA-256 of every file |
| `SOURCE_MANIFEST.md` | provenance: **no external data**, 100 % synthetic |

IDs follow the PDF exactly: `SKU-000001`, `DEM-<sku>-<location>-2026W01`, `PO-2026-000001`, `SHORT-2026-000001`,
`MIT-<shortage-id>-01` (zero-padded, immutable, identical across every file).

## 5. Sparse assortment (10 % density) — reasoning and compliance

A dense cross-product (every SKU in every location) is 3,000 × 50 × 52 = **7.8 M** demand rows (~600 MB of CSV): unrealistic
(stores do not stock every SKU) and incompatible with a public GitHub repository (100 MB per-file limit). We stock a
configurable share of the SKU × Location cross-product via the **`SKULocation` bridge table**
(`assortment_density`, default **0.10** for `full`): 15,000 stocked pairs → 14,700 active pairs × 52 weeks = **764,400** demand rows.

1. **All 3,000 SKUs and all 50 locations exist** in master data and each has ≥ 1 *active* pair (validator + independent audit).
2. **Every ACTIVE SKU-location pair has demand for all 52 weeks**; INACTIVE pairs (≈2 %) carry no demand or inventory.
3. **The density is a parameter** (`--set assortment_density=…`), tested; the achieved density is written to `manifest.json`.
   Make-SKUs and components are stocked at plants only, which caps very high densities (≈0.67 for `tiny`).
4. The PDF never states that the cross-product must be dense; all required counts (3,000 / 50 / 52 / 500 / 10,000) are met exactly.

## 6. Planning engine (traceability)

`src/oryva/planning.py` is a deterministic function of the input tables only:

0. **Data-quality gate** (the exception path): UoM normalisation, duplicate-inbound detection (duplicate PO and
   received-order-re-listed), supplier capacity ledger, missing lead times, unapproved substitutes → `DataQualityFinding`.
1. Gross requirements = forecast + BOM dependent demand from capacity-limited production.
2. Opening = `on_hand − allocated − quality_hold`.
3. Scheduled receipts = open, non-duplicate POs by ETA week (`ETA = promised + Σ delay events`).
4. Production = planned quantity reduced by the minimum number of whole lots until each work-centre-week fits its hours.
5. **Projected available balance** `closing = opening + receipts + production − demand − dependent` — reconciled exactly every week.
6. Shortage episodes where `closing < safety stock`; cause attribution (waterfall over source records; contributions sum
   exactly to `shortage_qty`); priority score; mitigations (expedite, new PO, alternative supplier, substitute SKU,
   location transfer, production re-plan, backorder) each checked for **policy → lead time → capacity (MOQ, multiples, remaining
   supplier capacity, donor surplus, spare hours)**, costed and scored for service; history as append-only events.

**Worked example** (golden test `tests/test_engine_golden.py`): on-hand 100, safety stock 20, demand W01–W03 = 40/90/30, one PO of 80
promised W02 but delayed to W03 → closing 60, −30, 20 → shortage W02, quantity 50, single cause `INBOUND_LATE_TRANSPORT`.

## 7. The five mandatory edge cases

Injected after a validated clean baseline, by deterministic rules, touching only labelled rows; labels live only in `ground_truth/`
(`label_class = BOUNDARY` rows are valid look-alikes that must **not** be flagged).

| `issue_type` | Injection | Engine / validator behaviour |
|---|---|---|
| `INBOUND_DOUBLE_COUNT` | (A) a PO duplicated under a new ID with identical supplier/SKU/ship-to/promised date/`supplier_ref_no`; (B) an already **RECEIVED** order re-listed as an open PLANNED order | Duplicate excluded from supply and capacity; PAB identical to the clean run |
| `SUBSTITUTE_NOT_APPROVED` | PENDING / REJECTED / EXPIRED substitute for a SKU with a shortage | Option kept for audit with `policy_check=FAIL`, never recommendable |
| `SUPPLIER_CAPACITY_EXCEEDED` | superseding effective-dated capacity row below committed load (boundary: capacity == committed) | Ledger `EXCEEDED`, finding raised, mitigation capacity limited |
| `SHORTAGE_MISSING_LEAD_TIME` | lead-time rows removed for every supplier of a shortage SKU | Shortage → `NEEDS_REVIEW`; supplier options blocked; no default lead time is assumed |
| `UOM_MISMATCH` | PO ordered in CASE/BAG with `qty_base` not converted | Recomputed `order_qty × factor` used; finding raised |

`evaluate.py` (the only module that reads ground truth) scores precision/recall per type; see `docs/validation_summary.md`.

## 8. Application and advanced modules (optional, separate from the mandatory core)

| Page | What it does |
|---|---|
| Overview | KPI tiles (service level, shortages, value at risk, plan cost vs do-nothing), charts, "needs attention" list |
| Inventory | filters, weeks of cover, position vs safety stock, projected balance chart per SKU-location |
| Demand | 52-week forecast by family / driver, spikes and promotions |
| Suppliers | scorecard (on-time, fulfilment, delays, capacity utilisation, shortage exposure), score breakdown, disruption risk |
| Shortages / Mitigation | prioritised shortages with evidence, option comparison (cost vs service), independent validation, approve/reject |
| **Stress test** | fails each high-exposure supplier in turn (outage of N weeks or permanent) on a copy of the data and **re-runs the planning engine** -> ranks suppliers by verified impact (new/worse shortages, value at risk, first impact week), shows how many shortages the engine could recover, single-sourced SKUs and second-source candidates, and how poorly the heuristic risk score predicts the real impact |
| **Recovery planner** | select several shortages -> one action per shortage chosen so that, **together**, they respect shared supplier capacity, donor/substitute stock, production hours and expedited-order quantity -> the combined plan is **verified by one engine re-run** -> compared with doing nothing, independent best picks and the engine's one-by-one picks (cost, gaps, side effects, capacity exceedances) -> reasons for every selected/rejected option -> approve (audited) -> Markdown export |
| **Decision room** | shortage -> evidence -> every candidate option applied to a copy of the data and **the planning engine re-run** -> verified before/after gap, side effects elsewhere, service/capacity deltas -> checks -> approve (audited) -> downloadable case file |
| Purchase orders | PO explorer + event timeline, **replenishment proposals** (approve/reject, draft orders), approved orders |
| Data quality | engine findings, capacity exceedances, validation-suite results |
| Scenarios | what-if: demand, lead time, supplier capacity, transport delay, disabled suppliers; baseline vs scenario; save |
| Risk | explainable early-warning scores (factor contributions) + supplier disruption risk + stress backtest |
| Optimizer | four strategies compared (engine ranking, minimum cost, cost-optimal with service floor, maximum service) |
| AI assistant | grounded Q&A (see below) |
| Reports | downloadable CSV / Markdown exports, role-based report (all downloads audited) |
| Audit history | hash-chained application audit log, approval decisions, dataset event history |

* **AI assistant**: answers are assembled from tool results over the loaded tables; every identifier must exist and every number must
  come from a data lookup (`verify_grounded`), unknown IDs are refused, recommendations are re-validated (MOQ, multiples, capacity,
  lead time, policy) before being shown. An optional LLM rewrite (`ANTHROPIC_API_KEY` + `anthropic`) is accepted only if it passes the
  same grounding check; that optional path could not be exercised without an API key and is untested.
* **Recovery planner** (`src/oryva/advanced/recovery.py`): candidates, objective and shared-resource limits come from the optimizer; the coordinated selection is the cheapest jointly-feasible plan found from several starts (repaired independent picks, Lagrangian solver, engine picks) with a 1-swap local search. All options are stacked on copies of the inputs and the engine is re-run once; outcomes are never summed from estimates. Side effects are measured by the verification run, not optimised directly.
* **Decision room** (`src/oryva/advanced/decision.py`): verifies mitigations instead of trusting estimates. Each option is represented in the input tables (new planned order, expedited ETA, extra production order, or a planned stock movement for transfers/substitutions) and the unchanged planning engine is re-run. Planned movements use a small optional engine input (`PlannedMovement`) that exported datasets never contain, so mandatory outputs are byte-identical (tested).
* **Scenario simulator**: applies a parameter overlay to *copies* of the input tables and re-runs the same engine; isolation is tested
  in memory and on disk (SHA-256 of every file unchanged).
* **Replenishment**: proposals come from the engine's recommended supplier orders, re-validated against source tables (MOQ,
  multiple, remaining capacity in the order week incl. already-approved drafts, lead time, supplier status); approvals create draft
  orders in the application state; orders above the spend threshold need an Ops manager/Admin.
* **Supplier intelligence / Risk**: deterministic scores whose weights and definitions are documented in the module docstrings;
  every score shows its components. The risk score is backtested by re-running the engine under a stress scenario (never used to
  compute the score).
* **Optimizer**: pure-numpy Lagrangian relaxation with greedy repair (scipy is blocked by an application-control policy on the
  target machine). Feasibility is verified independently; the dual bound gives an optimality gap. It is a heuristic, not an exact MILP.

## 9. Validation and reproducibility

682 validation checks (PK, FK incl. composite, enums, ID patterns, dates, arithmetic, lifecycle, duplicates, coverage, volumes,
acceptance criteria) with negative tests for each rule; **independent audit** (`scripts/audit.py`) re-checks exports from disk
(SQLite load + `foreign_key_check`, independent balance and shortage recomputation, MOQ/multiple/capacity/lead-time checks for
*every* mitigation type, label-leak scan, engine re-run from inputs only, JSON/CSV parity, checksums).
Reproducibility: named RNG streams, no wall-clock/UUID/hash-order dependence, deterministic gzip; `python -m oryva repro` regenerates
twice and compares row counts + SHA-256 of every file; the fresh-clone script proves a clean checkout regenerates byte-identical starter data.

## 10. Known limitations (see FINAL_REPORT.md for the complete list)

* One PO row = one SKU line; exactly 10,000 rows in the exported `PurchaseOrder` table (baseline + injected duplicates).
* Time model: `as_of_date = 2025-12-29`; no event is dated after it, so transport delays are known only for shipments already
  under way at `as_of` (178 delay events in `full`).
* FINISHED_MAKE SKUs and components are stocked at plants only; production is not reduced for component shortages.
* Cost = *incremental* cost of acting; do-nothing cost = backorder penalty.
* The planning engine is a static single-pass plan (no re-planning loop): scenario shocks therefore cause large shortage changes.
* Role-based access is application-level (demo credentials, session based) — not a production identity system.

## 11. Layout

```
app.py                     Streamlit entry
profiles/                  tiny|starter|full.yaml, policies.yaml
src/oryva/                 MANDATORY core: schema, ids, weeks, config, datagen, inject, dq, planning, validate, evaluate, export, pipeline, cli
src/oryva/advanced/        OPTIONAL: scenario, supplier_intel, risk, replenish, optimize, assistant, kpi, data
src/oryva/app/             OPTIONAL: Streamlit UI (views, ui, cache, main) + application state (users, audit log, approvals)
tests/                     unit, golden, validator-negative, edge-case, firewall, reproducibility, advanced, assistant, app
scripts/                   audit.py, fresh_clone_test.ps1, ui_smoke.py
data/starter|full/         generated exports (+ ground_truth/, docs/, manifest.json)
docs/                      reproducibility reports, audit evidence, test results, data model
```

License: MIT.
