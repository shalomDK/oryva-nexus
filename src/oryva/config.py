"""Profile / policy loading and named, order-independent random streams."""
from __future__ import annotations

import copy
import hashlib
import json
import zlib
from pathlib import Path

import numpy as np
import yaml

ROOT = Path(__file__).resolve().parents[2]
PROFILE_DIR = ROOT / "profiles"


def rng(seed: int, name: str) -> np.random.Generator:
    """Independent stream per stage name: adding a stage never shifts another stage's numbers."""
    return np.random.default_rng(np.random.SeedSequence([int(seed), zlib.crc32(name.encode())]))


def _coerce(v: str):
    try:
        return json.loads(v)
    except Exception:
        return v


def load_profile(name_or_path: str, overrides: list[str] | None = None) -> dict:
    p = Path(name_or_path)
    if not p.exists():
        p = PROFILE_DIR / f"{name_or_path}.yaml"
    prof = yaml.safe_load(p.read_text(encoding="utf-8"))
    for ov in overrides or []:
        key, val = ov.split("=", 1)
        node = prof
        parts = key.split(".")
        for k in parts[:-1]:
            node = node[k]
        node[parts[-1]] = _coerce(val)
    prof["as_of_date"] = str(prof["as_of_date"])
    return prof


def load_policy() -> dict:
    return yaml.safe_load((PROFILE_DIR / "policies.yaml").read_text(encoding="utf-8"))


def policy_hash(policy: dict) -> str:
    return hashlib.sha256(json.dumps(policy, sort_keys=True).encode()).hexdigest()[:16]


def clone(d: dict) -> dict:
    return copy.deepcopy(d)
