# FINAL_REPORT.md — ORYVA NEXUS

Date: 24 Nov 2026. Deadline: 25 Nov 2026 (end of day). **Nothing has been published or submitted.**

## 1. What was implemented

**Mandatory core (unchanged architecture, extended in Phase 1)** — synthetic generator (3,000 SKUs · 50 locations · 52 weeks · 500 suppliers ·
10,000 POs, seed 20261022, same code for tiny/starter/full), configurable assortment density (default 0.10), planning engine, five labelled
edge cases (double count now in two variants), separate ground truth, 682-check validator, exports (CSV/JSON/SQL), reproducibility harness,
independent audit script, fresh-clone script.

**Phase 1 changes:** R-043 closed (independent verification of *every* mitigation type); double-count variant B (received order re-listed as
open); transport-delay variation (178 delay events, 42 transport-caused shortages, previously 75 / 3); README verified by a fresh clone in a new
virtualenv and by tests.

**Application (Streamlit, `streamlit run app.py`)** — 17 pages: Overview, Inventory, Demand, Suppliers, Shortages, Decision room, Recovery planner, Stress test, Mitigation, Purchase orders
(+ replenishment proposals, draft orders), Data quality, Scenarios, Risk, Optimizer, AI assistant, Reports, Audit history. Design system
(cards, consistent charts, filters, search, empty/error states, responsive layout), login with 6 roles and page/action permissions, per-page
error boundary, rotating log file, hash-chained audit log, append-only approval workflow, dataset selector (starter/full), downloads (audited).

**Advanced modules (`src/oryva/advanced/`, separate from the core)**

| Module | What it does | Verification |
|---|---|---|
| AI assistant | grounded Q&A: explain a shortage, recommend with independent validation, problematic suppliers/locations, risks, what-if | every answer passes `verify_grounded` (IDs exist, numbers come from lookups); unknown IDs refused; fabricated text caught; every shortage's explanation and recommendation in the tiny dataset is checked; recommended options are re-validated |
| What-if simulator | demand, lead time, capacity, transport delay, disabled suppliers on **copies** of the inputs; same engine; baseline-vs-scenario KPIs and shortage diffs | isolation tested in memory and on disk (SHA-256 of all files), no-op scenario reproduces baseline, monotonicity |
| Supplier intelligence | on-time, fulfilment, delays, lead-time ratio, capacity utilisation, shortage exposure; composite score with documented weights | components sum to score; counts reconcile to source tables |
| Automated replenishment | proposals (quantity, supplier, order date, arrival) from recommended supplier orders, re-validated (MOQ, multiple, capacity incl. approved drafts, lead time, status); approve/reject; draft orders | MOQ/capacity violations rejected; aggregate capacity respected; baseline untouched |
| Risk prediction | explainable 0–100 shortage-risk score (7 weighted factors with per-factor points) and supplier disruption risk | contributions sum to score; stress backtest (demand +15 %, +7 d delays) on the full dataset: AUC 0.97, precision@top-10 % 0.82 (base rate 0.20, lift 4.1) — *caveat: the stress shocks act on the same buffers the score measures, so this is a consistency check, not out-of-sample forecasting accuracy* |
| Optimizer | one mitigation per shortage minimising action + uncovered-demand cost under shared supplier/donor/substitute/hours/PO capacity; 4 strategies | feasibility verified independently; dual bound. Full dataset: engine ranking 2,641,153 (94.17 % service) vs minimum-cost 2,618,769 (−0.85 %, 93.43 % service, gap 0.16 %); a 95 % service floor is reported as **not attainable** (max 94.19 %) |

## 2. Mandatory requirements

54 of 57 pass with execution evidence; the 3 open items (R-050 public repository, R-055 form submission, R-057 deadline) are owner actions.
R-043, R-051 and R-056 were closed in this round. Details: [REQUIREMENTS_AUDIT.md](REQUIREMENTS_AUDIT.md).

## 3. Tests

* `python -m pytest`: **217 passed, 1 skipped, 0 failed** (core 7, data-quality/validators 20, edge cases + firewall 11, golden 6, reproducibility 3, phase-1 3,
  advanced 14, assistant 19, assistant multi-part/follow-up 60, decision room 14, recovery planner 14, stress test 8, application 25, phase-5 7, README 4). Output: `docs/test_results.txt`.
* Full dataset: validation 682 checks / 0 unexpected failures; edge-case detection precision = recall = 1.0 (45/60/30/30/30 labelled);
  reproducibility 105/105 identical files (twice); independent audit clean; all 17 pages render on the full dataset.
* Visual check in the browser pane found and led to fixing one real defect (assistant grounding false positive) that the unit tests had missed.

## 4. Known limitations / remaining issues

1. Not published: no git commit, no GitHub repository, no form submission (by instruction).
2. Role-based access is application-level with demo credentials (`oryva-demo`, or `ORYVA_DEMO_PASSWORD`); not a production identity system.
3. The optional LLM rewrite of assistant answers is untested (no API key); the deterministic grounded mode is what was verified.
4. Optimizer is a Lagrangian heuristic with greedy repair (scipy blocked by policy), not an exact MILP; gap reported per run.
5. Risk-score backtest is a consistency check against a stress run, not independent forecasting validation.
6. Static single-pass plan (no re-planning); scenario shocks therefore have large effects.
7. Transport-delay knowledge is limited to shipments under way at the as-of date (data-time model).
8. Independent recomputation of projected balances covers bought SKUs; production capping is checked by a conservative bound.
9. Performance: full dataset first load ≈ 12–18 s, scenario run ≈ 17 s, optimizer ≈ 7 s, risk scoring ≈ 9 s (cached afterwards). Repo ≈ 159 MB.
10. Verified on one Windows machine (Python 3.13); a second machine has not been tried.

## 5. Commands

```powershell
pip install -e ".[dev]"
python -m oryva generate --profile starter --out data/starter
python -m oryva generate --profile full --out data/full
streamlit run app.py                      # login: planner / oryva-demo  (also admin, ops, analyst, warehouse, supplier)
python -m pytest
python -m oryva repro --profile full --report docs/reproducibility_full.md
python scripts/audit.py data/full docs/audit_evidence_full.json
powershell -File scripts/fresh_clone_test.ps1
```

## 6. Steps remaining for GitHub submission (need your approval — nothing below has been done)

1. Review `git status`; confirm no secrets (`.env`, `data/app_state.sqlite`, `logs/` are git-ignored; 281 files / ≈159 MB would be added).
2. `git add -A` · `git commit -m "ORYVA NEXUS: planning engine, synthetic data, application"`.
3. Create a **public** GitHub repository (e.g. `oryva-nexus`), then `git remote add origin <url>` · `git push -u origin master`.
4. On GitHub, clone into a new folder and run the README quick start (`pip install -e ".[dev]"`, `python -m oryva generate --profile starter …`, `python -m pytest`) — this is the only remaining check of R-051/R-056 from a second location.
5. Submit the repository URL through the assignment form before **25 Nov 2026 EOD**.
