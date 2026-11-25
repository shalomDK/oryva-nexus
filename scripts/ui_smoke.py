"""Render every dashboard page headlessly (Streamlit AppTest) against a dataset and report errors + timings.
Usage: python scripts/ui_smoke.py starter|full [role]"""
import os
import sys
import tempfile
import time
from pathlib import Path

from streamlit.testing.v1 import AppTest

from oryva.app.views import PAGES

name = sys.argv[1] if len(sys.argv) > 1 else "starter"
role = sys.argv[2] if len(sys.argv) > 2 else "ADMIN"
tmp = tempfile.mkdtemp()
os.environ.update(ORYVA_DEFAULT_DATASET=name, ORYVA_STATE_DB=str(Path(tmp) / "s.sqlite"), ORYVA_LOG_DIR=str(Path(tmp) / "logs"))
app = str(Path(__file__).resolve().parents[1] / "app.py")
bad = 0
for page, _, _ in PAGES:
    t = time.time()
    at = AppTest.from_file(app, default_timeout=600)
    at.session_state["user"] = {"username": "admin", "role": role, "display_name": "smoke", "supplier_id": None}
    at.session_state["nav"] = page
    at.run()
    errs = [str(e.value) for e in at.exception] + [str(e.value) for e in at.error]
    bad += bool(errs)
    print(f"{'FAIL' if errs else 'ok  '} {page:18s} {time.time() - t:6.1f}s  {errs[:2]}", flush=True)
sys.exit(1 if bad else 0)
