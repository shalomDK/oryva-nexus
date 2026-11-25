# REQUIREMENTS_AUDIT.md — strict audit against `ORYVA_AI_Assignment.pdf`

Last updated: 24 Nov 2026 (after Phases 1–5). Every status rests on commands **executed** against the exports in `data/full` and
`data/starter`; the existence of code was never accepted as evidence. Raw evidence is committed in `docs/`.

## 0. Evidence runs

| # | Command | Result | Artifact |
|---|---|---|---|
| E1 | `python -m pytest -v` | **217 passed** (1 skipped), 0 failed | `docs/test_results.txt` |
| E2 | `python -m oryva generate --profile full --out data/full` | exit 0; 682 checks, **0 unexpected failures** | `data/full/docs/validation_summary.md` |
| E3 | `python -m oryva generate --profile starter --out data/starter` | exit 0; 682 checks, 0 unexpected failures | `data/starter/docs/validation_summary.md` |
| E4 | `python -m oryva repro --profile full` (two independent generations) | **PASS, 105/105 files identical** (row counts + SHA-256) | `docs/reproducibility_full.md` |
| E5 | `python -m oryva repro --profile starter` | **PASS, 105/105 files identical** | `docs/reproducibility_starter.md` |
| E6 | `python -m oryva validate --data-dir data/full` / `data/starter` (re-reads CSV from disk) | exit 0, 0 unexpected failures, 0 checksum mismatches | console |
| E7 | `python scripts/audit.py data/full` / `data/starter` — independent re-check from disk (SQLite load + `foreign_key_check`, FK/PK from DDL, independent balance and shortage recomputation, MOQ / multiple / capacity / lead-time check of every mitigation type, label-leak scan, engine re-run from inputs only, JSON/CSV parity, checksums) | all clean (below) | `docs/audit_evidence_full.json`, `docs/audit_evidence_starter.json` |
| E8 | `scripts/fresh_clone_test.ps1`: copy of the project (no `.git`, no caches, no full data) → **new virtualenv** → `pip install -e ".[dev]"` → README steps (`generate`, `validate`, `load-sql`, `pytest`) → compare with the committed `data/starter` | 105/105 files byte-identical (SHA-256), `load-sql` clean, validation clean, **217 tests pass (1 skipped) inside the clean clone** (re-run 25 Nov 2026) | script output |
| E9 | `python scripts/ui_smoke.py full` | all 17 dashboard pages render with 0 errors on the full dataset (first load 18 s, then cached) | console |

Measured facts (full dataset, E7): SKU 3,000 · Location 50 · Supplier 500 · PurchaseOrder 10,000 · demand weeks 52 · ForecastDemand 764,400
(= 14,700 active pairs × 52) · SKULocation 15,000 (density 0.1000) · Inventory 14,700 · SupplierCapacity 1,066 · LeadTime 4,457 ·
ProductionPlan 35,872 · Shortage 1,600 · MitigationOption 7,135 · 32 tables · 32 PKs (0 duplicates) · 57 FK relationships (0 orphans;
SQLite `foreign_key_check` = 0) · SQL rows == CSV rows == manifest · JSON/CSV parity 32/32.

## 1. The 57 requirements

### 1.1 Problem, scope, workflow (PDF §1–§3)

| ID | Status | Evidence | Missing work |
|---|---|---|---|
| R-001 | PASS | Engine joins forecast, inventory, supplier capacity ledger, lead times and production hours; E7 independently recomputed 516,048 balance cells for 9,924 bought-SKU pairs: **0 mismatches**; golden test | – |
| R-002 | PASS | 1,600 shortages, all with causes (0 without), `priority_score` / `priority_rank`; causes sum exactly to `shortage_qty` | – |
| R-003 | PASS | `ShortageEvent`/`MitigationEvent` decisions, `DataQualityFinding` exceptions, `NEEDS_REVIEW`; role report; **dashboard pages Shortages, Mitigation, Data quality, Audit history** | – |
| R-004 | PASS | `ShortageCause.source_table/source_id` validated to exist; mitigation rows reference supplier/PO/alt-SKU/donor; assistant cites source IDs | – |
| R-005 | PASS | KPI block + edge-case precision/recall in `validation_summary.md`; dashboard KPIs computed from data (test `test_no_hardcoded_numeric_kpis_in_views`, `test_dashboard_overview_numbers_come_from_the_data`) | – |
| R-006 | PASS | 32 related tables, conditional rules, five exception paths, metrics | – |
| R-007 | PASS | `actor_role` on event tables, `approval_required_role`, role report, **application roles (6) with permissions** (`tests/test_app.py`) | – |
| R-008 | PASS | Generation order in `datagen.py`; 62 FK checks pass | – |
| R-009 | PASS | E7: 0 orphans over 57 FK relationships; composite FKs 0 violations | – |
| R-010 | PASS | Planning stages incl. production capacity + BOM (600 BOMs, 1,824 lines), PAB, shortages, mitigations | – |
| R-011 | PASS | Six append-only event tables; header status == last event; capacity changes are new rows; application decisions are append-only too | Injected UoM case edits one PO row in place (labelled, by design) |
| R-012 | PASS | Outcomes derived from source rows; label selection deterministic; engine re-run from inputs reproduces outputs exactly | Scenario inputs (spikes, delays) are seeded-random by design |

### 1.2 Entities, relationships, IDs (PDF §4)

| ID | Status | Evidence | Missing work |
|---|---|---|---|
| R-013 | PASS | All 11 core tables non-empty (E7 `entity_volumes_present`) | – |
| R-014 | PASS | 32 tables / 32 PRIMARY KEY / 57 FOREIGN KEY; 0 duplicate PKs; 0 orphans; SQLite FK check 0 | – |
| R-015 | PASS | `docs/data_model.md` (cardinality, optional relationships, effective dating, lifecycles); lifecycles enforced by validator | `PROJECT_PLAN.md` §4 partly stale (status note added); `data_model.md` is authoritative |
| R-016 | PASS | Bridges `SKULocation`, `SKUSupplier`, `SKUSubstitute`, `BOMLine`, `ShortageCause` | – |
| R-017 | PASS | Event tables + validator (62 FK, 17 lifecycle, 26 date-order checks) | – |
| R-018 | PASS | Labels only in `ground_truth/`; blast-radius test proves only labelled rows changed | – |
| R-019–R-023 | PASS | E7 `id_patterns_nonmatching` = 0 for SKU, DEM, PO, SHORT, MIT; `demand_id == DEM-<sku>-<loc>-<week>` for all 764,400 rows; mitigation prefix == shortage_id | – |
| R-024 | PASS | Cross-file FK checks; `test_ids_are_identical_across_regenerations`; E4 identical checksums | – |

### 1.3 Synthetic data generation (PDF §5)

| ID | Status | Evidence | Missing work |
|---|---|---|---|
| R-025 | PASS | Data dictionary for all 32 tables incl. the 11 mandatory; no empty cell (test) | `unit` is `-` for non-quantity fields |
| R-026 | PASS | Dependency order in `datagen.py`; no orphans | – |
| R-027 | PASS | Deterministic counters; E4/E5 | – |
| R-028 | PASS | Exact volumes; variation: **846 SPIKE rows, constrained suppliers (supplier-weeks ≥ 90 %), 353 approved substitute links, 178 transport-delay events** (up from 75), seed 20261022, one generator for all profiles | Delay variation limited by the as-of time model (§4, W1) |
| R-029 | PASS | Clean baseline validated (677 checks) before injection; blast-radius test | – |
| R-030 | PASS | 11 arithmetic checks + independent recomputation | – |
| R-031 | PASS | `ground_truth/` separate; engine, advanced and app modules never read it (tests + E7 scan) | – |
| R-032 | PASS | 682 checks, 9 validator-negative tests | – |
| R-033 | PASS | CSV(.gz), JSON(.json.gz for 2 large tables), SQL seed, README, dictionary, manifest (command + seed), source manifest, validation summary; JSON/CSV parity 32/32; SQL loads | Large tables gzip-compressed |
| R-034 | PASS | E4 (full) and E5 (starter): 105/105 identical files; E8 byte-identical regeneration in a clean checkout | – |

### 1.4 Edge cases (PDF §6) — full dataset: labelled / TP / FP / FN

| ID | Status | Evidence | Missing work |
|---|---|---|---|
| R-035 Inbound counted twice | PASS | 45 / 45 / 0 / 0 — **two variants**: (A) 30 duplicate POs, (B) 15 already-RECEIVED orders re-listed as open; +1 boundary near-duplicate not flagged; PAB identical to clean run | – |
| R-036 Substitute not approved | PASS | 30 / 30 / 0 / 0; 0 recommended unapproved substitutes | – |
| R-037 Capacity exceeded | PASS | 30 / 30 / 0 / 0; boundary `committed == capacity` not flagged | – |
| R-038 No lead time | PASS | 60 / 60 / 0 / 0; shortages `NEEDS_REVIEW`; 0 recommendable options with missing lead time | – |
| R-039 UoM mismatch | PASS | 30 / 30 / 0 / 0 | Missing-factor variant exists only as an engine finding |
| R-040 Label + traceability | PASS | `ground_truth` rows carry `issue_type`, `record_id`, `related_record_ids`, original/injected values; IDs exist in source tables | – |

### 1.5 Acceptance criteria (PDF §7)

| ID | Status | Evidence | Missing work |
|---|---|---|---|
| R-041 | PASS | Residual 0 on all 764,400 rows; opening == previous closing; independent recompute 516,048 cells 0 mismatches; 914 == 914 shortage episodes identical | Make/component pairs: identity + engine capping only |
| R-042 | PASS | 1,600/1,600 shortages have causes; Σ contribution == `shortage_qty` | – |
| **R-043** | **PASS** (was PARTIAL) | Independent E7 checks, **every mitigation type, 0 violations**: 1,852 supplier POs (MOQ, multiple, remaining capacity, lead days vs LeadTime, supplier ACTIVE, arrival = as-of + lead, aggregate rank-1 load within capacity); 2,653 transfers (donor surplus, aggregate donor surplus, lead days); 36 substitutes (approved, stocked, qty ≥ ratio × covered, surplus, aggregate surplus); 470 production re-plans (frozen horizon, lot multiple, hours vs available − requested); 165 expedites (status, 0 < gain ≤ 14 d, earliest date, covered ≤ corrected PO qty, premium = 12 %); `weeks_late` and `fill_rate_pct` recomputed. The audit also exposed and fixed two verification defects (expedite check used the recorded rather than UoM-corrected quantity) | – |
| R-044 | PASS | Every shortage ≥ 2 options; 0 options missing cost/service fields | – |
| R-045, R-046 | PASS | See R-014; 11 arithmetic + 17 lifecycle + 26 date checks | – |

### 1.6 Lawful data use, Submission

| ID | Status | Evidence | Missing work |
|---|---|---|---|
| R-047–R-049 | PASS | No external data; `SOURCE_MANIFEST.md` | – |
| R-050 | **OPEN** | Repository prepared locally (`.gitignore`, license, README) but **not committed or pushed** — deliberately, publishing needs the owner's approval | Commit, create public repository, push (steps in FINAL_REPORT.md) |
| R-051 | **PASS** (was PARTIAL) | README commands verified: E8 fresh-clone dry run in a new virtualenv + `tests/test_readme.py` (every CLI sub-command, script and file referenced in the README exists; profile table matches) | `streamlit run app.py` was verified headlessly (E9, AppTest) and visually in the browser pane, not from a second machine |
| R-052 | PASS | `docs/test_results.txt` (217 passed) + validation summaries | – |
| R-053 | PASS | See R-033 | – |
| R-054 | PASS | Separate ground truth; reproducibility reports | – |
| R-055 | **OPEN** | Local build/test done; push and form submission not done | Student action |
| R-056 | **PASS** (was PARTIAL) | Reproducible (E4, E5, E8 in a clean environment), auditable (events, findings, hash-chained audit log, `scripts/audit.py`), explainable | Not verified on a different physical machine |
| R-057 | **OPEN** | Deadline 25 Nov 2026 EOD; submission not done | Complete R-050 / R-055 |

**Tally (57):** PASS 54 · OPEN 3 (R-050, R-055, R-057 — owner actions: publish and submit). All technically achievable requirements pass.

## 2. Edge cases — injected, detected, tested

| Issue type (full) | Injected | Engine TP/FP/FN | Validator == labelled set | Tests |
|---|---|---|---|---|
| INBOUND_DOUBLE_COUNT | 45 (30 A + 15 B) +1 boundary | 45/0/0 | yes | `test_duplicate_inbound_is_not_counted_twice`, `test_double_count_variant_b_…`, `test_injected_data_gives_same_shortages_as_clean…` |
| SUBSTITUTE_NOT_APPROVED | 30 | 30/0/0 | yes | `test_missing_lead_time_chains…substitutes_never_recommended`, validator-negative test |
| SUPPLIER_CAPACITY_EXCEEDED | 30 +1 boundary | 30/0/0 | yes | `test_capacity_exceeded_flagged_and_boundary_is_not` |
| SHORTAGE_MISSING_LEAD_TIME | 60 keys | 60/0/0 | yes | `test_missing_lead_time_is_never_silently_defaulted`, `test_lead_time_of_zero_days_is_valid_not_missing` |
| UOM_MISMATCH | 30 | 30/0/0 | yes | `test_uom_mismatch_uses_converted_quantity` |

## 3. Optional modules (separate from the mandatory core — none read ground truth; the mandatory modules do not import them: `test_mandatory_pipeline_does_not_import_optional_modules`)

AI assistant · what-if simulator · supplier intelligence · replenishment · risk prediction · optimisation engine · Streamlit application — see FINAL_REPORT.md for evidence and limits.

## 4. Bugs found and weaknesses

Fixed (re-verified by the evidence runs above): quadratic validator loop (38 min → ~70 s); validator crash on duplicate PK; missing JSON for two large tables; empty dictionary rule text; lot-cut rule creating artificial shortages; **audit false positive on UoM-corrected PO quantity**; optimiser candidate capacities used recorded (not corrected) PO quantity and a too-conservative substitute horizon (engine plan showed 3 spurious violations); **assistant grounding false positive on engine-generated explanation strings** (found by visual testing); assistant intent routing (risk vs location); my own accidental truncation of `scripts/audit.py` (restored and re-verified).

Open weaknesses:
* **W1 Transport delays**: 178 delay events; 42 shortages have `INBOUND_LATE_TRANSPORT` as primary cause (was 3). Delays remain confined to shipments under way at `as_of` (no events after `as_of`).
* **W2 Static plan**: no re-planning loop; scenario shocks (e.g. demand +20 %) put most SKU-locations short.
* **W3 Independence**: balances are independently recomputed for bought SKUs only; the engine-rerun evidence proves determinism and label-independence, not correctness; production capping is audited by a conservative bound.
* **W4 Capacity units**: `weekly_capacity_qty` mixes EA/KG per family (`capacity_uom = MIXED`).
* **W5 Edge-case variants**: "missing UoM factor" is detected by the engine but not injected.
* **W6** Tests assume the repository root as working directory.
* **W7** Repo size ≈ 159 MB (largest file 13.6 MB).
* **W8** The optional LLM rewrite path of the assistant is untested (no API key); scipy-based optimisation was impossible (application-control policy blocks scipy), so the optimiser is a numpy Lagrangian heuristic with a reported dual gap.
