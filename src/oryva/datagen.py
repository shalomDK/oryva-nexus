"""Synthetic baseline generator (valid data only; edge cases are injected later by inject.py).

Dependency order: UoM/Location/Carrier/Supplier -> SKU -> assortment (SKULocation) -> conversions,
SKUSupplier, substitutes -> LeadTime -> ForecastDemand -> BOM/ProductionPlan/WorkCenter -> Inventory
and PurchaseOrder (+events) -> SupplierCapacity (derived from committed load) -> ProductionCapacity.
All counts come from the profile (scale parameters); randomness uses named streams (config.rng).
"""
from __future__ import annotations

import math
from datetime import date, timedelta

import numpy as np
import pandas as pd

from . import ids, weeks as W
from .config import rng
from .frames import finalize

REGIONS = ["NORTH", "SOUTH", "EAST", "WEST", "CENTRAL"]
COUNTRY = {"NORTH": "Canada", "SOUTH": "Brazil", "EAST": "India", "WEST": "USA", "CENTRAL": "Germany"}
PO_STATUS_OF = {"CREATED": "PLANNED", "CONFIRMED": "CONFIRMED", "SHIPPED": "IN_TRANSIT",
                "DELAYED": "DELAYED", "RECEIVED": "RECEIVED", "CANCELLED": "CANCELLED"}
DELAY_REASONS = ["WEATHER", "PORT_CONGESTION", "CUSTOMS", "BREAKDOWN", "DOCUMENTATION"]


def ru(x, m):
    """Round up x to a multiple of m (ints)."""
    return int(-(-int(x) // int(m)) * int(m))


def _d(s: str) -> date:
    return date.fromisoformat(s)


def _s(d: date) -> str:
    return d.isoformat()


def alloc_counts(w: np.ndarray, N: int, cap: int) -> np.ndarray:
    n = np.zeros(len(w), dtype=int)
    if N <= 0 or len(w) == 0:
        return n
    avail = np.ones(len(w), bool)
    rem = N
    for _ in range(60):
        ww = w * avail
        share = ww / ww.sum() * rem
        add = np.floor(share).astype(int)
        left = rem - add.sum()
        order = np.argsort(-(share - add), kind="stable")
        add[order[:left]] += 1
        n = np.minimum(n + add, cap)
        rem = N - n.sum()
        avail = n < cap
        if rem == 0 or not avail.any():
            break
    if rem:
        raise ValueError(f"cannot allocate {N} purchase orders (cap {cap} per pair, {len(w)} pairs)")
    return n


def generate_baseline(P: dict, reserve_po: int = 0) -> tuple[dict, dict]:
    """Return (tables, meta). `reserve_po` POs are left out of the baseline and added by the injector so the
    exported PurchaseOrder table has exactly P['n_purchase_orders'] rows."""
    seed = P["seed"]
    nS, nL, nW, nU = P["n_skus"], P["n_locations"], P["n_weeks"], P["n_suppliers"]
    as_of = P["as_of_date"]
    as_of_d = _d(as_of)
    sc = P["scenario"]
    EFF0 = "2025-01-01"

    # ------------------------------------------------------------------ UoM, carriers
    uom = pd.DataFrame([("EA", "Each", "COUNT"), ("CASE", "Case", "COUNT"), ("KG", "Kilogram", "MASS"),
                        ("BAG", "Bag", "MASS")], columns=["uom_code", "uom_name", "uom_class"])
    car_def = [("ROAD", "LOCAL"), ("ROAD", "REGIONAL"), ("ROAD", "LOCAL"), ("RAIL", "REGIONAL"),
               ("SEA", "OVERSEAS"), ("SEA", "OVERSEAS"), ("AIR", "OVERSEAS"), ("AIR", "OVERSEAS")]
    carriers = pd.DataFrame([{"carrier_id": f"CAR-{i+1:02d}", "carrier_name": f"Carrier {i+1:02d} {m.title()}",
                              "mode": m, "sourcing_region": rg} for i, (m, rg) in enumerate(car_def)])
    car_by_mode: dict = {}
    for _, c in carriers.iterrows():
        car_by_mode.setdefault(c["mode"], []).append(c["carrier_id"])

    # ------------------------------------------------------------------ locations
    r = rng(seed, "location")
    n_plant = max(1, round(P["location_mix"]["plant"] * nL))
    n_dc = max(1, round(P["location_mix"]["dc"] * nL))
    types = np.array(["PLANT"] * n_plant + ["DC"] * n_dc + ["STORE"] * (nL - n_plant - n_dc))
    types = types[r.permutation(nL)]
    reg = np.array(REGIONS)[r.permutation(nL) % 5]
    locf = np.where(types == "STORE", r.uniform(0.6, 1.5, nL), np.where(types == "DC", r.uniform(2, 4, nL),
                                                                          r.uniform(1.5, 3, nL)))
    loc_ids = [ids.loc(i + 1) for i in range(nL)]
    locations = pd.DataFrame({"location_id": loc_ids,
                              "location_name": [f"{t.title()} {rg.title()} {i+1:03d}" for i, (t, rg) in enumerate(zip(types, reg))],
                              "location_type": types, "region": reg, "country": [COUNTRY[x] for x in reg],
                              "status": "ACTIVE", "effective_from": EFF0, "effective_to": None})
    plants = [i for i in range(nL) if types[i] == "PLANT"]

    # ------------------------------------------------------------------ suppliers
    r = rng(seed, "supplier")
    F = min(P["n_families"], max(1, nU // 2))
    fam_names = [f"FAM-{i+1:02d}" for i in range(F)]
    s_region = r.choice(["LOCAL", "REGIONAL", "OVERSEAS"], size=nU, p=[0.45, 0.30, 0.25])
    s_tier = r.choice(["STRATEGIC", "PREFERRED", "STANDARD"], size=nU, p=[0.15, 0.35, 0.50])
    s_status = r.choice(["ACTIVE", "ON_HOLD"], size=nU, p=[0.97, 0.03])
    s_status[:F] = "ACTIVE"
    s_constrained = r.random(nU) < sc["constrained_supplier_share"]
    s_prod_base = r.integers(2, 21, nU)
    s_fams = []
    for i in range(nU):
        fs = {i % F}
        for _ in range(int(r.integers(0, 3))):
            fs.add(int(r.integers(0, F)))
        s_fams.append(sorted(fs))
    sf_params = {}
    for i in range(nU):
        for fi in s_fams[i]:
            mult = int(r.choice([1, 6, 12, 24, 48], p=[0.25, 0.20, 0.25, 0.20, 0.10]))
            sf_params[(i, fi)] = (mult * int(r.choice([1, 2, 4], p=[0.5, 0.3, 0.2])), mult)
    sup_ids = [ids.sup(i + 1) for i in range(nU)]
    suppliers = pd.DataFrame({
        "supplier_id": sup_ids, "supplier_name": [f"Supplier {i+1:04d}" for i in range(nU)],
        "country": [COUNTRY[REGIONS[int(x) % 5]] for x in r.integers(0, 5, nU)],
        "region": s_region, "tier": s_tier, "status": s_status, "currency": "USD",
        "payment_terms_days": r.choice([30, 45, 60, 90], nU),
        "onboarded_date": [_s(as_of_d - timedelta(days=int(x))) for x in r.integers(200, 2500, nU)],
        "effective_from": EFF0, "effective_to": None})
    sups_by_fam = {fi: [i for i in range(nU) if fi in s_fams[i]] for fi in range(F)}

    # ------------------------------------------------------------------ SKU master
    r = rng(seed, "sku")
    n_make, n_comp = round(P["sku_mix"]["make"] * nS), round(P["sku_mix"]["component"] * nS)
    stype = np.array(["FINISHED_MAKE"] * n_make + ["COMPONENT"] * n_comp + ["FINISHED_BUY"] * (nS - n_make - n_comp))
    stype = stype[r.permutation(nS)]
    sfam = r.integers(0, F, nS)
    base_uom = np.where(stype == "FINISHED_MAKE", "EA",
                        np.where(r.random(nS) < np.where(stype == "COMPONENT", 0.30, 0.10), "KG", "EA"))
    pop = r.lognormal(0, 1.0, nS)
    cost = np.round(np.clip(r.lognormal(np.log(18), 0.8, nS), 0.5, 900), 2)
    price = np.round(cost * r.uniform(1.2, 2.0, nS), 2)
    sku_ids = [ids.sku(i + 1) for i in range(nS)]
    make_idx = [i for i in range(nS) if stype[i] == "FINISHED_MAKE"]
    comp_idx = [i for i in range(nS) if stype[i] == "COMPONENT"]
    buy_idx = [i for i in range(nS) if stype[i] == "FINISHED_BUY"]

    # ------------------------------------------------------------------ assortment (SKULocation) - configurable density
    r = rng(seed, "assortment")
    pairs: set = set()
    for s in comp_idx:
        pairs.update((s, l) for l in plants)  # components are stocked at every plant so BOMs are feasible
    for s in make_idx:
        k = int(r.integers(1, min(3, len(plants)) + 1))
        pairs.update((s, int(l)) for l in r.choice(plants, k, replace=False))
    target = round(P["assortment_density"] * nS * nL)
    nb = len(buy_idx)
    if nb:
        extra_total = max(0, target - len(pairs) - nb)
        w = pop[buy_idx] ** 0.5
        w = w / w.sum()
        cnt = 1 + r.multinomial(extra_total, w)
        cnt = np.minimum(cnt, nL)
        guard = 0
        while cnt.sum() < extra_total + nb and (cnt < nL).any() and guard < 200000:
            j = int(r.integers(0, nb))
            if cnt[j] < nL:
                cnt[j] += 1
            guard += 1
        lw = locf / locf.sum()
        for j, s in enumerate(buy_idx):
            pairs.update((s, int(l)) for l in r.choice(nL, int(cnt[j]), replace=False, p=lw))
        covered = {l for _, l in pairs}
        for l in range(nL):  # every location must be represented
            if l not in covered:
                pairs.add((int(buy_idx[int(r.integers(0, nb))]), l))
    pairs_sorted = sorted(pairs)
    # a small share of buy-SKU pairs are INACTIVE (no demand); each SKU and location keeps >=1 ACTIVE pair
    cnt_s = np.zeros(nS, int)
    cnt_l = np.zeros(nL, int)
    for s, l in pairs_sorted:
        cnt_s[s] += 1
        cnt_l[l] += 1
    n_inactive = round(P["inactive_pair_share"] * len(pairs_sorted))
    cand = [pairs_sorted[i] for i in r.permutation(len(pairs_sorted)) if stype[pairs_sorted[i][0]] == "FINISHED_BUY"]
    inactive = set()
    for s, l in cand:
        if len(inactive) >= n_inactive:
            break
        if cnt_s[s] > 1 and cnt_l[l] > 1:
            inactive.add((s, l))
            cnt_s[s] -= 1
            cnt_l[l] -= 1
    skuloc = pd.DataFrame([{"sku_id": sku_ids[s], "location_id": loc_ids[l],
                            "stocking_status": "INACTIVE" if (s, l) in inactive else "ACTIVE",
                            "effective_from": EFF0, "effective_to": None} for s, l in pairs_sorted])
    ap = [p for p in pairs_sorted if p not in inactive]
    nP = len(ap)
    ps = np.array([p[0] for p in ap])
    pl = np.array([p[1] for p in ap])
    pidx = {p: i for i, p in enumerate(ap)}
    locs_of_sku = {}
    for s, l in ap:
        locs_of_sku.setdefault(s, set()).add(l)

    # ------------------------------------------------------------------ UoM conversions, sourcing, substitutes
    r = rng(seed, "sourcing")
    pack_f, conv_rows = {}, []
    for s in range(nS):
        if stype[s] == "FINISHED_MAKE":
            continue
        kg = base_uom[s] == "KG"
        pack_f[s] = int(r.choice([10, 20, 25]) if kg else r.choice([6, 12, 24]))
        pu = "BAG" if kg else "CASE"
        conv_rows.append({"conversion_id": f"UOMC-{sku_ids[s]}-{pu}", "sku_id": sku_ids[s], "from_uom": pu,
                          "to_uom": base_uom[s], "factor": float(pack_f[s])})
    sku_sup: dict = {}  # s -> list of (sup_idx, preferred, approval, price)
    ss_rows = []
    for s in sorted(buy_idx + comp_idx):
        cands = sups_by_fam[int(sfam[s])]
        act = [c for c in cands if s_status[c] == "ACTIVE"] or cands
        n_s = min(len(cands), int(r.choice([1, 2, 3], p=[0.4, 0.4, 0.2])))
        first = int(r.choice(act))
        chosen = [first] + [int(c) for c in r.permutation([c for c in cands if c != first])[: n_s - 1]]
        lst = []
        for j, c in enumerate(chosen):
            appr = "APPROVED" if (j == 0 or r.random() > 0.04) else "BLOCKED"
            pr = round(max(0.01, float(cost[s]) * float(r.uniform(0.85, 1.05))), 2)
            lst.append((c, 1 if j == 0 else 0, appr, pr))
            ss_rows.append({"sku_id": sku_ids[s], "supplier_id": sup_ids[c], "is_preferred": 1 if j == 0 else 0,
                            "approval_status": appr, "unit_price": pr, "effective_from": EFF0, "effective_to": None})
        sku_sup[s] = lst
    sub_rows = []
    groups: dict = {}
    for s in buy_idx:
        groups.setdefault((int(sfam[s]), base_uom[s]), []).append(s)
    for s in buy_idx:
        if r.random() >= sc["substitute_share"] or s not in locs_of_sku:
            continue
        alts = [a for a in groups[(int(sfam[s]), base_uom[s])] if a != s and locs_of_sku.get(a, set()) & locs_of_sku[s]]
        if not alts:
            continue
        for a in r.permutation(alts)[: int(r.integers(1, 3))]:
            ad = as_of_d - timedelta(days=int(r.integers(30, 400)))
            sub_rows.append({"sku_id": sku_ids[s], "substitute_sku_id": sku_ids[int(a)],
                             "substitution_ratio": float(r.choice([1.0, 1.0, 1.1, 1.2])),
                             "approval_status": "APPROVED", "approved_by_role": str(r.choice(["PLANNER", "OPS_MANAGER"])),
                             "approved_date": _s(ad), "cost_penalty_pct": float(r.choice([0, 2, 5, 8])),
                             "effective_from": _s(ad), "effective_to": None})

    # ------------------------------------------------------------------ lead times
    r = rng(seed, "leadtime")
    lt_rows, lt_def, lt_ovr = [], {}, {}
    for s in sorted(sku_sup):
        for (c, _, _, _) in sku_sup[s]:
            rg = s_region[c]
            mode = "ROAD" if rg == "LOCAL" else ("ROAD" if r.random() < 0.6 else "RAIL") if rg == "REGIONAL" else \
                ("SEA" if r.random() < 0.7 else "AIR")
            tr = {"ROAD": (1, 5), "RAIL": (4, 11), "SEA": (25, 46), "AIR": (3, 8)}[mode]
            prod = int(s_prod_base[c] + r.integers(0, 5))
            tran = int(r.integers(*tr))
            tot = prod + tran
            lt_def[(c, s)] = (prod, tran, tot, mode)
            lt_rows.append((sup_ids[c], sku_ids[s], None, prod, tran, tot, int(math.ceil(tot * r.uniform(1.15, 1.5))), mode))
            if r.random() < 0.05 and s in locs_of_sku:
                lo = int(r.choice(sorted(locs_of_sku[s])))
                tr2 = max(1, tran + int(r.integers(-1, 4)))
                lt_ovr[(c, s, lo)] = (prod, tr2, prod + tr2, mode)
                lt_rows.append((sup_ids[c], sku_ids[s], loc_ids[lo], prod, tr2, prod + tr2,
                                int(math.ceil((prod + tr2) * r.uniform(1.15, 1.5))), mode))
    lt_rows.sort(key=lambda x: (x[0], x[1], x[2] or ""))
    leadtime = pd.DataFrame([{"lead_time_id": ids.counter("LT", i + 1), "supplier_id": a, "sku_id": b,
                              "ship_to_location_id": c, "production_days": d, "transit_days": e,
                              "total_lead_days": f, "p90_lead_days": g, "transport_mode": h,
                              "effective_from": EFF0, "effective_to": None}
                             for i, (a, b, c, d, e, f, g, h) in enumerate(lt_rows)])

    # ------------------------------------------------------------------ demand
    r = rng(seed, "demand")
    t = np.arange(1, nW + 1)
    fam_amp = r.uniform(0.05, 0.35, F)
    fam_ph = r.uniform(0, 52, F)
    lam = 6.0 * pop[ps] * locf[pl] * np.where(stype[ps] == "COMPONENT", 0.15, 1.0)
    amp = fam_amp[sfam[ps]][:, None]
    ph = fam_ph[sfam[ps]][:, None]
    season = 1 + amp * np.sin(2 * np.pi * (t[None, :] - ph) / 52)
    trend = 1 + r.normal(0, 0.002, nP)[:, None] * t[None, :]
    mean = lam[:, None] * season * trend * r.lognormal(0, 0.12, (nP, nW))
    promo = np.ones((nP, nW))
    for p in np.nonzero(r.random(nP) < sc["promo_pair_share"])[0]:
        st = int(r.integers(0, nW - 3))
        promo[p, st: st + int(r.integers(1, 4))] = r.uniform(1.3, 1.8)
    inter = lam < 2
    base = np.where(inter[:, None], r.poisson(np.maximum(mean * promo, 0)), np.rint(mean * promo)).astype(np.int64)
    Fq = base.copy()
    spike = np.zeros((nP, nW), bool)
    for p in np.nonzero((r.random(nP) < sc["spike_pair_share"]) & (lam >= 3))[0]:
        for st in r.choice(nW, int(r.integers(1, 3)), replace=False):
            m = r.uniform(1.8, 3.5)
            Fq[p, st] = max(int(Fq[p, st]), int(math.ceil(max(base[p, st], mean[p, st]) * m)))
            spike[p, st] = Fq[p, st] > base[p, st]
    cv = np.where(inter, r.uniform(0.35, 0.7, nP), r.uniform(0.15, 0.45, nP))
    stdev = np.round(cv[:, None] * np.maximum(base, 1), 2)
    driver = np.where(spike, "SPIKE", np.where(promo > 1.0, "PROMO", np.where(season >= 1.2, "SEASONAL", "BASELINE")))
    wl = [W.label(int(w)) for w in t]
    wd = [W.week_start_s(int(w)) for w in t]
    sk_p = [sku_ids[s] for s in ps]
    lo_p = [loc_ids[l] for l in pl]
    demand = pd.DataFrame({
        "demand_id": [f"DEM-{a}-{b}-{c}" for a, b in zip(sk_p, lo_p) for c in wl],
        "sku_id": np.repeat(sk_p, nW), "location_id": np.repeat(lo_p, nW),
        "iso_week": np.tile(wl, nP), "week_start_date": np.tile(wd, nP),
        "forecast_qty": Fq.reshape(-1), "demand_driver": driver.reshape(-1), "forecast_stdev": stdev.reshape(-1)})
    # criticality (ABC) derived from forecast revenue
    rev = np.zeros(nS)
    np.add.at(rev, ps, Fq.sum(1) * price[ps])
    order = np.argsort(-rev, kind="stable")
    cumb = np.concatenate([[0], np.cumsum(rev[order])[:-1]]) / max(rev.sum(), 1e-9)
    crit = np.empty(nS, dtype="<U1")
    crit[order] = np.where(cumb < 0.80, "A", np.where(cumb < 0.95, "B", "C"))
    slt = np.where(crit == "A", 0.98, np.where(crit == "B", 0.95, 0.90))
    zval = np.where(crit == "A", 2.05, np.where(crit == "B", 1.65, 1.28))
    sku = pd.DataFrame({"sku_id": sku_ids, "sku_name": [f"{fam_names[int(sfam[i])]} item {i+1:06d}" for i in range(nS)],
                        "product_family": [fam_names[int(x)] for x in sfam], "sku_type": stype,
                        "base_uom": base_uom, "unit_cost": cost, "unit_price": price,
                        "service_level_target": slt, "criticality": crit, "lifecycle_status": "ACTIVE",
                        "effective_from": EFF0, "effective_to": None})
    sku.loc[r.choice(nS, max(1, nS // 100), replace=False), "lifecycle_status"] = "PHASING_OUT"

    # ------------------------------------------------------------------ BOM, production plan, work centres
    r = rng(seed, "production")
    wc_rows, wcs_of_plant = [], {}
    for l in plants:
        wcs_of_plant[l] = []
        for k in range(2):
            wid = f"WC-{loc_ids[l]}-{k+1:02d}"
            wcs_of_plant[l].append(wid)
            wc_rows.append({"work_center_id": wid, "location_id": loc_ids[l], "work_center_name": f"Line {k+1}", "status": "ACTIVE"})
    bom_rows, line_rows, bom_of, bom_lines = [], [], {}, {}
    for j, s in enumerate(make_idx):
        mw = float(np.mean([base[pidx[(s, l)]].mean() for l in range(nL) if (s, l) in pidx]))
        lot = max(1, int(round(mw * float(r.choice([1, 2, 3])))))
        bid = ids.counter("BOM", j + 1)
        rt = round(float(r.uniform(0.02, 0.3)), 4)
        bom_of[s] = (bid, rt, lot)
        bom_rows.append({"bom_id": bid, "parent_sku_id": sku_ids[s], "bom_version": 1, "run_time_hours_per_unit": rt,
                         "lot_size": lot, "effective_from": EFF0, "effective_to": None})
        nc = min(len(comp_idx), int(r.integers(2, 5)))
        lines = []
        for c in sorted(int(x) for x in r.choice(comp_idx, nc, replace=False)) if nc else []:
            q, sp = int(r.integers(1, 5)), float(r.choice([0.0, 0.02, 0.05]))
            lines.append((c, q, sp))
            line_rows.append({"bom_id": bid, "component_sku_id": sku_ids[c], "qty_per": q, "scrap_pct": sp})
        bom_lines[s] = lines
    tight = r.random(nP) < sc["tight_pair_share"]
    bfac = np.where(tight, r.uniform(0.55, 0.92, nP), np.clip(r.normal(1.04, 0.04, nP), 1.0, 1.12))
    plan_rows = []  # (sku_idx, loc_idx, week, qty, wc)
    DEP = np.zeros((nP, nW), dtype=np.int64)
    cum_f = np.cumsum(base, axis=1)
    for p in range(nP):
        s, l = int(ps[p]), int(pl[p])
        if stype[s] != "FINISHED_MAKE":
            continue
        lot = bom_of[s][2]
        wc = wcs_of_plant[l][int(r.integers(0, len(wcs_of_plant[l])))]
        prod_cum = 0
        for w in range(nW):
            tgt = int(math.ceil(bfac[p] * cum_f[p, w]))
            if tgt > prod_cum:
                q = ru(tgt - prod_cum, lot)
                prod_cum += q
                plan_rows.append((s, l, w + 1, q, wc))
                for (c, qp, sp) in bom_lines[s]:
                    DEP[pidx[(c, l)], w] += int(math.ceil(q * qp * (1 + sp)))
    # ------------------------------------------------------------------ inventory sizing + purchase orders
    r = rng(seed, "inventory")
    elig = np.array([i for i in range(nP) if stype[ps[i]] != "FINISHED_MAKE"], dtype=int)
    tot_base = base + DEP
    lt_weeks = np.ones(nP)
    for i in elig:
        c0 = sku_sup[int(ps[i])][0][0]
        lt_weeks[i] = lt_def[(c0, int(ps[i]))][2] / 7.0
    sigma = stdev.mean(1) + 0.1 * DEP.mean(1)
    ss = np.ceil(zval[ps] * sigma * np.sqrt(np.maximum(lt_weeks, 1.0))).astype(np.int64)
    mean_w = np.maximum(tot_base.mean(1), 0.0)

    n_hist = round(sc["historic_po_share"] * P["n_purchase_orders"])
    n_reg = P["n_purchase_orders"] - n_hist - reserve_po
    vol = tot_base[elig].sum(1).astype(float) + 1.0
    wts = vol ** 0.6
    n_po = np.zeros(nP, dtype=int)
    n_po[elig] = alloc_counts(wts, n_reg, 13)
    hist_pairs = elig[r.choice(len(elig), n_hist, replace=False, p=wts / wts.sum())] if n_hist else np.array([], int)

    rp = rng(seed, "purchase_orders")
    po_raw, ev_raw, tr_raw, ie_raw = [], [], [], []
    avail = np.zeros(nP, dtype=np.int64)
    hist_q = {}

    def new_po(p, qty_base, requested, hist):
        s, l = int(ps[p]), int(pl[p])
        opts = [o for o in sku_sup[s] if o[2] == "APPROVED"]
        pref = opts[0]
        o = pref if (len(opts) == 1 or rp.random() < 0.65) else opts[int(rp.integers(1, len(opts)))]
        c = o[0]
        lt = lt_ovr.get((c, s, l)) or lt_def[(c, s)]
        prod_d, tran_d, tot_d, mode = lt
        req_d = requested
        order_d = req_d - timedelta(days=tot_d)
        moq, mult = sf_params[(c, int(sfam[s]))]
        qb = ru(max(moq, qty_base), mult)
        uom_o = base_uom[s]
        qo = qb
        pf = pack_f.get(s)
        if pf and qb % pf == 0 and rp.random() < 0.7:
            uom_o = "BAG" if base_uom[s] == "KG" else "CASE"
            qo = qb // pf
        row = {"supplier": c, "sku": s, "loc": l, "order": order_d, "req": req_d, "qb": qb, "qo": qo, "uom": uom_o,
               "price": o[3], "mode": mode, "prod": prod_d, "tran": tran_d, "hist": hist}
        # lifecycle ------------------------------------------------------------------
        ev = []
        slip = 0
        cancel = (not hist) and order_d > as_of_d and rp.random() < sc["cancelled_po_share"]
        if order_d <= as_of_d:
            created = order_d - timedelta(days=int(rp.integers(0, 4)))
            ev.append(("CREATED", created, "PLANNER", None, None))
            ev.append(("CONFIRMED", order_d, "SUPPLIER", None, None))
            confirmed = True
        else:
            created = as_of_d - timedelta(days=int(rp.integers(6, 41)))
            ev.append(("CREATED", created, "PLANNER", None, None))
            confirmed = (not cancel) and order_d <= as_of_d + timedelta(days=90) and rp.random() < 0.25
            if confirmed:
                ev.append(("CONFIRMED", as_of_d - timedelta(days=int(rp.integers(0, 6))), "SUPPLIER", None, None))
        if cancel:
            ev.append(("CANCELLED", created + timedelta(days=int(rp.integers(1, (as_of_d - created).days + 1))), "PLANNER", None, None))
        if confirmed and not cancel:
            pslip = 0.08 + (0.30 if s_constrained[c] else 0.0)
            if rp.random() < pslip:
                slip = int(rp.integers(3, 15) if s_constrained[c] else rp.integers(1, 8))
        promised = req_d + timedelta(days=slip)
        if hist and promised >= as_of_d:
            promised, slip = req_d, 0
        delay = 0
        ship_d = None
        carrier = None
        if confirmed and not cancel and order_d <= as_of_d:
            ship_d = order_d + timedelta(days=prod_d)
            if ship_d <= as_of_d:
                carrier = str(rp.choice(car_by_mode[mode]))
                ev.append(("SHIPPED", ship_d, "CARRIER_WAREHOUSE", None, None))
                if rp.random() < sc["delay_share"]:
                    dd = ship_d + timedelta(days=int(rp.integers(1, max(2, tran_d) + 1)))
                    dl = int(rp.integers(3, 36))
                    if dd <= as_of_d and (not hist or promised + timedelta(days=dl) < as_of_d):
                        delay = dl
                        reason = str(rp.choice(DELAY_REASONS))
                        ev.append(("DELAYED", dd, "LOGISTICS_ANALYST", dl, reason))
                        row["delay_date"], row["delay_reason"] = dd, reason
            else:
                ship_d = None
        eta = promised + timedelta(days=delay)
        actual = None
        if "SHIPPED" in [e[0] for e in ev] and eta < as_of_d:
            ev.append(("RECEIVED", eta, "CARRIER_WAREHOUSE", None, None))
            actual = eta
        row.update(created=created, promised=promised, eta=eta, actual=actual, ship=ship_d, carrier=carrier, ev=ev,
                   delay=delay, slip=slip)
        return row

    for p in range(nP):
        s = int(ps[p])
        if stype[s] == "FINISHED_MAKE":
            avail[p] = ss[p] + int(math.ceil(float(r.uniform(0.5, 2.0)) * mean_w[p]))
            continue
        n = int(n_po[p])
        b = bfac[p]
        if n == 0:
            avail[p] = ss[p] + int(math.ceil(b * tot_base[p].sum() + r.uniform(0, 1) * mean_w[p]))
        else:
            u = float(r.uniform(0.05, 0.95))
            if r.random() < sc.get("early_arrival_share", 0.0):  # first PO already in transit at as_of
                u = float(r.uniform(0.02, min(0.95, 8.0 * n / 52.0)))
            arr = [int(math.floor(nW * ((j) + u) / n)) + 1 for j in range(n)]
            first_cover = tot_base[p, : arr[0] - 1].sum()
            avail[p] = ss[p] + int(math.ceil(b * first_cover + r.uniform(0, 1) * mean_w[p]))
            for j in range(n):
                end = arr[j + 1] - 1 if j + 1 < n else nW
                seg = tot_base[p, arr[j] - 1: end].sum()
                requested = W.week_start(arr[j]) + timedelta(days=int(rp.integers(0, 5)))
                po_raw.append((p, new_po(p, int(math.ceil(b * seg)), requested, False)))
    for p in hist_pairs:
        p = int(p)
        qh = int(math.ceil(mean_w[p] * float(rp.uniform(4, 10))))
        requested = as_of_d - timedelta(days=int(rp.integers(1, 57)))
        row = new_po(p, max(1, qh), requested, True)
        po_raw.append((p, row))
        avail[p] = max(avail[p], row["qb"])
    # ------------------------------------------------------------------ finalize POs / events (sorted -> immutable IDs)
    po_raw.sort(key=lambda x: (x[1]["order"], sku_ids[x[1]["sku"]], loc_ids[x[1]["loc"]], x[1]["supplier"], x[1]["req"]))
    po_rows, poe_rows, tre_rows, ine_rows = [], [], [], []
    eid = {"POE": 0, "TRE": 0, "INE": 0}

    def nxt(k):
        eid[k] += 1
        return f"{k}-{eid[k]:06d}"

    for n, (p, x) in enumerate(po_raw, start=1):
        pid = ids.po(n)
        evs = x["ev"]
        status = PO_STATUS_OF[evs[-1][0]]
        prev = None
        for (et, ed, role, dd, rs) in evs:
            to = PO_STATUS_OF[et]
            poe_rows.append({"event_id": nxt("POE"), "po_id": pid, "event_type": et, "from_status": prev, "to_status": to,
                             "event_date": _s(ed), "actor_role": role, "delay_days": dd, "reason_code": rs})
            prev = to
        if x["carrier"]:
            tre_rows.append({"event_id": nxt("TRE"), "po_id": pid, "carrier_id": x["carrier"], "event_type": "DEPARTED",
                             "event_date": _s(x["ship"]), "delay_days": None, "reason_code": None, "actor_role": "CARRIER_WAREHOUSE"})
            if x["delay"]:
                tre_rows.append({"event_id": nxt("TRE"), "po_id": pid, "carrier_id": x["carrier"], "event_type": "DELAYED",
                                 "event_date": _s(x["delay_date"]), "delay_days": x["delay"], "reason_code": x["delay_reason"],
                                 "actor_role": "CARRIER_WAREHOUSE"})
            if x["actual"]:
                tre_rows.append({"event_id": nxt("TRE"), "po_id": pid, "carrier_id": x["carrier"], "event_type": "ARRIVED",
                                 "event_date": _s(x["actual"]), "delay_days": None, "reason_code": None, "actor_role": "CARRIER_WAREHOUSE"})
        if x["actual"]:
            ine_rows.append({"event_id": nxt("INE"), "sku_id": sku_ids[x["sku"]], "location_id": loc_ids[x["loc"]],
                             "event_type": "RECEIPT", "qty": x["qb"], "event_date": _s(x["actual"]), "po_id": pid,
                             "actor_role": "CARRIER_WAREHOUSE"})
        po_rows.append({"po_id": pid, "supplier_id": sup_ids[x["supplier"]], "sku_id": sku_ids[x["sku"]],
                        "ship_to_location_id": loc_ids[x["loc"]], "carrier_id": x["carrier"],
                        "created_date": _s(x["created"]), "order_date": _s(x["order"]), "requested_date": _s(x["req"]),
                        "promised_date": _s(x["promised"]), "eta_date": _s(x["eta"]),
                        "actual_receipt_date": _s(x["actual"]) if x["actual"] else None,
                        "order_qty": x["qo"], "order_uom": x["uom"], "qty_base": x["qb"], "unit_price": x["price"],
                        "total_cost": round(x["qb"] * x["price"], 2), "supplier_ref_no": f"SR-{sup_ids[x['supplier']]}-{n:06d}",
                        "status": status})
    po = pd.DataFrame(po_rows)

    # inventory snapshot
    alloc = np.floor(avail * r.uniform(0, 0.05, nP)).astype(np.int64)
    hold = np.where(r.random(nP) < 0.02, np.floor(avail * 0.1), 0).astype(np.int64)
    onhand = avail + alloc + hold
    inventory = pd.DataFrame({
        "inventory_id": [ids.inv(a, b) for a, b in zip(sk_p, lo_p)], "sku_id": sk_p, "location_id": lo_p,
        "as_of_date": as_of, "on_hand_qty": onhand, "allocated_qty": alloc, "quality_hold_qty": hold,
        "safety_stock_qty": ss, "available_qty": onhand - alloc - hold,
        "inventory_status": np.where(hold > 0, "QUALITY_HOLD", "AVAILABLE")})

    # ------------------------------------------------------------------ production plan (+events) and capacity
    plan_rows.sort(key=lambda x: (sku_ids[x[0]], loc_ids[x[1]], x[2]))
    pp, ppe = [], []
    r2 = rng(seed, "production_events")
    hours = {}
    for n, (s, l, w, q, wc) in enumerate(plan_rows, start=1):
        pid = ids.counter("PP-2026", n)
        bid, rt, lot = bom_of[s]
        hrs = round(q * rt, 4)
        hours[(wc, w)] = hours.get((wc, w), 0.0) + hrs
        cancelled = r2.random() < 0.004
        created = as_of_d - timedelta(days=int(r2.integers(7, 31)))
        evs = [("PLANNED", created)]
        if cancelled:
            evs.append(("CANCELLED", as_of_d - timedelta(days=int(r2.integers(0, 6)))))
        elif w <= 2:
            evs += [("FIRMED", as_of_d - timedelta(days=int(r2.integers(3, 7)))), ("RELEASED", as_of_d - timedelta(days=int(r2.integers(0, 3))))]
        elif w <= 6:
            evs.append(("FIRMED", as_of_d - timedelta(days=int(r2.integers(0, 3)))))
        prev = None
        for to, ed in evs:
            ppe.append({"production_plan_id": pid, "from_status": prev, "to_status": to, "event_date": _s(ed),
                        "actor_role": "PLANNER"})
            prev = to
        pp.append({"production_plan_id": pid, "sku_id": sku_ids[s], "location_id": loc_ids[l], "work_center_id": wc,
                   "bom_id": bid, "iso_week": W.label(w), "week_start_date": W.week_start_s(w), "planned_qty": q,
                   "required_hours": hrs, "status": prev})
    for i, e in enumerate(ppe, start=1):
        e["event_id"] = f"PPE-{i:06d}"
    wc_names = [w["work_center_id"] for w in wc_rows]
    n_con = max(1, round(sc["constrained_work_center_share"] * len(wc_names))) if sc["constrained_work_center_share"] > 0 else 0
    con_set = {wc_names[int(i)] for i in r2.choice(len(wc_names), n_con, replace=False)} if n_con else set()
    constrained_wc = {w: (w in con_set) for w in wc_names}
    maint = {w["work_center_id"]: set(int(x) for x in r2.choice(np.arange(1, nW + 1), 2, replace=False)) for w in wc_rows}
    pc_rows = []
    for wrow in wc_rows:
        wid = wrow["work_center_id"]
        hs = [hours.get((wid, w), 0.0) for w in range(1, nW + 1)]
        peak = max(hs) if max(hs) > 0 else 40.0
        capb = peak * (float(r2.uniform(0.76, 0.86)) if constrained_wc[wid] else float(r2.uniform(1.05, 1.25)))
        for w in range(1, nW + 1):
            pc_rows.append({"work_center_id": wid, "iso_week": W.label(w), "week_start_date": W.week_start_s(w),
                            "available_hours": round(capb * (0.92 if w in maint[wid] else 1.0), 2)})
    for i, rrow in enumerate(pc_rows, start=1):
        rrow["prod_capacity_id"] = ids.counter("PCAP", i)

    # ------------------------------------------------------------------ supplier capacity from committed load
    r3 = rng(seed, "supplier_capacity")
    fam_of_sku = {sku_ids[i]: int(sfam[i]) for i in range(nS)}
    sup_idx = {sid: i for i, sid in enumerate(sup_ids)}
    load = {}
    for rw in po_rows:
        if rw["status"] == "CANCELLED":
            continue
        od = _d(rw["order_date"])
        ws = od - timedelta(days=od.weekday())
        k = (sup_idx[rw["supplier_id"]], fam_of_sku[rw["sku_id"]])
        load.setdefault(k, {})
        load[k][ws] = load[k].get(ws, 0) + rw["qty_base"]
    cap_rows = []
    for i in range(nU):
        for fi in s_fams[i]:
            peak = max(load.get((i, fi), {0: 0}).values())
            u = float(r3.uniform(0.90, 1.0)) if s_constrained[i] else float(r3.uniform(0.35, 0.80))
            capq = int(math.ceil(peak / u)) if peak > 0 else int(r3.integers(200, 2000))
            moq, mult = sf_params[(i, fi)]
            cap_rows.append({"supplier_id": sup_ids[i], "product_family": fam_names[fi], "weekly_capacity_qty": max(capq, moq),
                             "min_order_qty": moq, "order_multiple": mult, "capacity_uom": "MIXED", "status": "ACTIVE",
                             "effective_from": EFF0, "effective_to": None})
            if r3.random() < 0.10:  # capacity expansion row supersedes the base row from 2026-07-01
                cap_rows.append({"supplier_id": sup_ids[i], "product_family": fam_names[fi],
                                 "weekly_capacity_qty": int(math.ceil(max(capq, moq) * 1.2)), "min_order_qty": moq,
                                 "order_multiple": mult, "capacity_uom": "MIXED", "status": "ACTIVE",
                                 "effective_from": "2026-07-01", "effective_to": None})
    for i, c in enumerate(cap_rows, start=1):
        c["capacity_id"] = ids.counter("SCAP", i)

    uoc = pd.DataFrame(conv_rows)
    tables = {
        "UnitOfMeasure": uom, "Location": locations, "Carrier": carriers, "Supplier": suppliers, "SKU": sku,
        "UoMConversion": uoc, "SKULocation": skuloc, "SKUSupplier": pd.DataFrame(ss_rows),
        "SKUSubstitute": pd.DataFrame(sub_rows, columns=["sku_id", "substitute_sku_id", "substitution_ratio",
                                                         "approval_status", "approved_by_role", "approved_date",
                                                         "cost_penalty_pct", "effective_from", "effective_to"]),
        "BillOfMaterial": pd.DataFrame(bom_rows), "BOMLine": pd.DataFrame(line_rows), "WorkCenter": pd.DataFrame(wc_rows),
        "ProductionCapacity": pd.DataFrame(pc_rows), "ForecastDemand": demand, "Inventory": inventory,
        "SupplierCapacity": pd.DataFrame(cap_rows), "LeadTime": leadtime, "PurchaseOrder": po,
        "ProductionPlan": pd.DataFrame(pp), "PurchaseOrderEvent": pd.DataFrame(poe_rows),
        "TransportEvent": pd.DataFrame(tre_rows), "InventoryEvent": pd.DataFrame(ine_rows),
        "ProductionPlanEvent": pd.DataFrame(ppe),
    }
    tables = {k: finalize(k, v) for k, v in tables.items()}
    n_pairs_total = len(pairs_sorted)
    meta = {"actual_assortment_density": round(n_pairs_total / (nS * nL), 6), "n_pairs_total": n_pairs_total,
            "n_pairs_active": nP, "n_pairs_inactive": len(inactive), "n_families": F, "n_plants": len(plants)}
    return tables, meta







