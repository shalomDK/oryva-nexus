"""Application state (SQLite, separate from the baseline dataset): users/roles, tamper-evident audit log, approval workflow
for replenishment proposals and mitigations, draft purchase orders and saved scenarios.

* The baseline CSV/SQL exports are NEVER written by the application.
* Every state-changing action goes through `State.audit()` which appends a hash-chained row (prev_hash + payload),
  so edits/deletions of history are detectable with `verify_chain()`.
* Passwords are stored as salted PBKDF2-SHA256 hashes."""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

ROLES = ("ADMIN", "OPS_MANAGER", "PLANNER", "LOGISTICS_ANALYST", "CARRIER_WAREHOUSE", "SUPPLIER")

# page access per role (None = every page)
PAGE_ACCESS = {
    "ADMIN": None,
    "OPS_MANAGER": None,
    "PLANNER": None,
    "LOGISTICS_ANALYST": ["Overview", "Inventory", "Demand", "Suppliers", "Shortages", "Decision room", "Recovery planner", "Stress test", "Mitigation", "Purchase orders", "Data quality",
                          "Scenarios", "Risk", "Reports", "Audit history", "AI assistant"],
    "CARRIER_WAREHOUSE": ["Overview", "Inventory", "Purchase orders", "Reports"],
    "SUPPLIER": ["Overview", "Suppliers", "Purchase orders"],
}
ACTIONS = {  # who may perform which state-changing action
    "decide_proposal": {"ADMIN", "OPS_MANAGER", "PLANNER"},
    "decide_high_value": {"ADMIN", "OPS_MANAGER"},
    "decide_mitigation": {"ADMIN", "OPS_MANAGER", "PLANNER"},
    "save_scenario": {"ADMIN", "OPS_MANAGER", "PLANNER", "LOGISTICS_ANALYST"},
    "manage_users": {"ADMIN"},
    "export": {"ADMIN", "OPS_MANAGER", "PLANNER", "LOGISTICS_ANALYST", "CARRIER_WAREHOUSE"},
}
FLOW = {None: {"PROPOSED"}, "PROPOSED": {"APPROVED", "REJECTED"}, "REJECTED": {"PROPOSED"}, "APPROVED": {"CANCELLED"}, "CANCELLED": set()}
GENESIS = "0" * 64

SCHEMA = """
CREATE TABLE IF NOT EXISTS users(username TEXT PRIMARY KEY, role TEXT NOT NULL, display_name TEXT NOT NULL, supplier_id TEXT,
    salt TEXT NOT NULL, pw_hash TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1);
CREATE TABLE IF NOT EXISTS audit_log(id INTEGER PRIMARY KEY AUTOINCREMENT, ts_utc TEXT NOT NULL, username TEXT NOT NULL, role TEXT NOT NULL,
    action TEXT NOT NULL, entity_type TEXT, entity_id TEXT, details TEXT NOT NULL, prev_hash TEXT NOT NULL, hash TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS decision_events(id INTEGER PRIMARY KEY AUTOINCREMENT, ts_utc TEXT NOT NULL, dataset TEXT NOT NULL,
    entity_type TEXT NOT NULL, entity_id TEXT NOT NULL, from_status TEXT, to_status TEXT NOT NULL, username TEXT NOT NULL, role TEXT NOT NULL, note TEXT);
CREATE TABLE IF NOT EXISTS draft_orders(order_id TEXT PRIMARY KEY, dataset TEXT NOT NULL, proposal_id TEXT NOT NULL UNIQUE, supplier_id TEXT NOT NULL,
    sku_id TEXT NOT NULL, location_id TEXT NOT NULL, qty_base INTEGER NOT NULL, order_uom TEXT NOT NULL, order_qty INTEGER NOT NULL, unit_price REAL NOT NULL,
    order_date TEXT NOT NULL, expected_arrival TEXT NOT NULL, status TEXT NOT NULL, created_by TEXT NOT NULL, created_ts TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS scenarios(id INTEGER PRIMARY KEY AUTOINCREMENT, ts_utc TEXT NOT NULL, dataset TEXT NOT NULL, name TEXT NOT NULL,
    params TEXT NOT NULL, kpis TEXT NOT NULL, username TEXT NOT NULL);
"""


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def hash_pw(password: str, salt: str | None = None) -> tuple[str, str]:
    salt = salt or secrets.token_hex(16)
    return salt, hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 120_000).hex()


class State:
    def __init__(self, path: str | Path = "data/app_state.sqlite"):
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._mem = sqlite3.connect(":memory:", check_same_thread=False) if self.path == ":memory:" else None
        with self.conn() as c:
            c.executescript(SCHEMA)

    @contextmanager
    def conn(self):
        c = self._mem or sqlite3.connect(self.path, timeout=30)
        c.row_factory = sqlite3.Row
        try:
            yield c
            c.commit()
        except Exception:
            c.rollback()
            raise
        finally:
            if self._mem is None:
                c.close()

    # ------------------------------------------------------------------ users
    def seed_demo_users(self, password: str | None = None):
        pw = password or os.environ.get("ORYVA_DEMO_PASSWORD", "oryva-demo")
        users = [("admin", "ADMIN", "Alex Admin", None), ("ops", "OPS_MANAGER", "Olivia Ops-Manager", None), ("planner", "PLANNER", "Priya Planner", None),
                 ("analyst", "LOGISTICS_ANALYST", "Liam Analyst", None), ("warehouse", "CARRIER_WAREHOUSE", "Wes Warehouse", None),
                 ("supplier", "SUPPLIER", "Sam Supplier (SUP-0001)", "SUP-0001")]
        with self.conn() as c:
            for u, r, n, s in users:
                if not c.execute("SELECT 1 FROM users WHERE username=?", (u,)).fetchone():
                    salt, h = hash_pw(pw)
                    c.execute("INSERT INTO users VALUES(?,?,?,?,?,?,1)", (u, r, n, s, salt, h))

    def authenticate(self, username: str, password: str) -> dict | None:
        with self.conn() as c:
            r = c.execute("SELECT * FROM users WHERE username=? AND active=1", (username,)).fetchone()
        if not r:
            return None
        _, h = hash_pw(password, r["salt"])
        return dict(r) if hmac.compare_digest(h, r["pw_hash"]) else None

    def list_users(self) -> list[dict]:
        with self.conn() as c:
            return [dict(r) for r in c.execute("SELECT username, role, display_name, supplier_id, active FROM users ORDER BY username")]

    def set_user_active(self, actor: dict, username: str, active: bool):
        self.require(actor, "manage_users")
        with self.conn() as c:
            c.execute("UPDATE users SET active=? WHERE username=?", (1 if active else 0, username))
        self.audit(actor, "user.activate" if active else "user.deactivate", "user", username, {})

    # ------------------------------------------------------------------ permissions
    @staticmethod
    def can(user: dict, action: str) -> bool:
        return user["role"] in ACTIONS.get(action, set())

    def require(self, user: dict, action: str):
        if not self.can(user, action):
            self.audit(user, "permission.denied", "action", action, {})
            raise PermissionError(f"role {user['role']} may not perform '{action}'")

    # ------------------------------------------------------------------ audit log (hash chain)
    def audit(self, user: dict, action: str, entity_type: str | None = None, entity_id: str | None = None, details: dict | None = None):
        details_s = json.dumps(details or {}, sort_keys=True, default=str)
        ts = now()
        with self.conn() as c:
            prev = c.execute("SELECT hash FROM audit_log ORDER BY id DESC LIMIT 1").fetchone()
            prev_h = prev["hash"] if prev else GENESIS
            payload = "|".join([prev_h, ts, user["username"], user["role"], action, entity_type or "", entity_id or "", details_s])
            h = hashlib.sha256(payload.encode()).hexdigest()
            c.execute("INSERT INTO audit_log(ts_utc, username, role, action, entity_type, entity_id, details, prev_hash, hash) VALUES(?,?,?,?,?,?,?,?,?)",
                      (ts, user["username"], user["role"], action, entity_type, entity_id, details_s, prev_h, h))

    def audit_rows(self, limit: int = 1000) -> list[dict]:
        with self.conn() as c:
            return [dict(r) for r in c.execute("SELECT * FROM audit_log ORDER BY id DESC LIMIT ?", (limit,))]

    def verify_chain(self) -> tuple[bool, int, int | None]:
        """(ok, rows checked, first bad id)."""
        prev, n = GENESIS, 0
        with self.conn() as c:
            for r in c.execute("SELECT * FROM audit_log ORDER BY id"):
                payload = "|".join([prev, r["ts_utc"], r["username"], r["role"], r["action"], r["entity_type"] or "", r["entity_id"] or "", r["details"]])
                if r["prev_hash"] != prev or hashlib.sha256(payload.encode()).hexdigest() != r["hash"]:
                    return False, n, r["id"]
                prev, n = r["hash"], n + 1
        return True, n, None

    # ------------------------------------------------------------------ approval workflow (append-only)
    def status_of(self, dataset: str, entity_type: str, entity_id: str) -> str | None:
        with self.conn() as c:
            r = c.execute("SELECT to_status FROM decision_events WHERE dataset=? AND entity_type=? AND entity_id=? ORDER BY id DESC LIMIT 1",
                          (dataset, entity_type, entity_id)).fetchone()
        return r["to_status"] if r else None

    def statuses(self, dataset: str, entity_type: str) -> dict:
        with self.conn() as c:
            rows = c.execute("SELECT entity_id, to_status FROM decision_events WHERE dataset=? AND entity_type=? ORDER BY id", (dataset, entity_type)).fetchall()
        return {r["entity_id"]: r["to_status"] for r in rows}

    def transition(self, user: dict, dataset: str, entity_type: str, entity_id: str, to: str, note: str = "", action_perm: str = "decide_proposal"):
        self.require(user, action_perm)
        cur = self.status_of(dataset, entity_type, entity_id)
        if to not in FLOW.get(cur, set()):
            raise ValueError(f"illegal transition {cur} -> {to} for {entity_id}")
        if to == "REJECTED" and not note.strip():
            raise ValueError("a rejection requires a note")
        with self.conn() as c:
            c.execute("INSERT INTO decision_events(ts_utc, dataset, entity_type, entity_id, from_status, to_status, username, role, note) VALUES(?,?,?,?,?,?,?,?,?)",
                      (now(), dataset, entity_type, entity_id, cur, to, user["username"], user["role"], note))
        self.audit(user, f"{entity_type}.{to.lower()}", entity_type, entity_id, {"from": cur, "note": note, "dataset": dataset})

    def decision_history(self, dataset: str | None = None) -> list[dict]:
        with self.conn() as c:
            q = "SELECT * FROM decision_events" + (" WHERE dataset=?" if dataset else "") + " ORDER BY id DESC"
            return [dict(r) for r in c.execute(q, (dataset,) if dataset else ())]

    # ------------------------------------------------------------------ draft orders
    def approve_proposal(self, user: dict, dataset: str, p: dict, threshold: float, note: str = "") -> str:
        """Approve a (validated) replenishment proposal and create a draft purchase order."""
        self.require(user, "decide_proposal")
        if p["order_value"] > threshold:
            self.require(user, "decide_high_value")
        if self.status_of(dataset, "proposal", p["proposal_id"]) is None:
            self.transition(user, dataset, "proposal", p["proposal_id"], "PROPOSED", "", "decide_proposal")
        self.transition(user, dataset, "proposal", p["proposal_id"], "APPROVED", note, "decide_proposal")
        with self.conn() as c:
            n = c.execute("SELECT COUNT(*) AS n FROM draft_orders").fetchone()["n"] + 1
            oid = f"RPO-{n:06d}"
            c.execute("INSERT INTO draft_orders VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                      (oid, dataset, str(p["proposal_id"]), str(p["supplier_id"]), str(p["sku_id"]), str(p["location_id"]), int(p["qty_base"]),
                       str(p["order_uom"]), int(p["order_qty"]), float(p["unit_price"]), str(p["order_date"]), str(p["expected_arrival"]),
                       "DRAFT", user["username"], now()))
        self.audit(user, "draft_order.created", "draft_order", oid, {"proposal": p["proposal_id"], "qty_base": p["qty_base"], "supplier": p["supplier_id"]})
        return oid

    def reject_proposal(self, user: dict, dataset: str, proposal_id: str, note: str):
        self.require(user, "decide_proposal")
        if self.status_of(dataset, "proposal", proposal_id) is None:
            self.transition(user, dataset, "proposal", proposal_id, "PROPOSED", "", "decide_proposal")
        self.transition(user, dataset, "proposal", proposal_id, "REJECTED", note, "decide_proposal")

    def draft_orders(self, dataset: str) -> list[dict]:
        with self.conn() as c:
            return [dict(r) for r in c.execute("SELECT * FROM draft_orders WHERE dataset=? ORDER BY order_id", (dataset,))]

    def approved_load(self, dataset: str) -> list[dict]:
        return [o for o in self.draft_orders(dataset) if o["status"] == "DRAFT"]

    # ------------------------------------------------------------------ scenarios
    def save_scenario(self, user: dict, dataset: str, name: str, params: dict, kpis: dict) -> int:
        self.require(user, "save_scenario")
        with self.conn() as c:
            cur = c.execute("INSERT INTO scenarios(ts_utc, dataset, name, params, kpis, username) VALUES(?,?,?,?,?,?)",
                            (now(), dataset, name, json.dumps(params, default=str), json.dumps(kpis, default=str), user["username"]))
            sid = cur.lastrowid
        self.audit(user, "scenario.saved", "scenario", str(sid), {"name": name, "dataset": dataset})
        return sid

    def scenarios(self, dataset: str) -> list[dict]:
        with self.conn() as c:
            return [dict(r) for r in c.execute("SELECT * FROM scenarios WHERE dataset=? ORDER BY id DESC", (dataset,))]
