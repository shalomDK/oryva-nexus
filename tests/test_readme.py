"""README verification: every command and file referenced in the README exists and parses."""
import re
import subprocess
import sys
from pathlib import Path

README = Path("README.md").read_text(encoding="utf-8")
BLOCKS = "\n".join(re.findall(r"```powershell\n(.*?)```", README, re.S))


def test_readme_has_no_encoding_damage():
    assert not re.search(r"[âÃÂ]", README)


def test_every_oryva_subcommand_in_readme_is_a_real_cli_command():
    from oryva.cli import main
    cmds = set(re.findall(r"python -m oryva (\S+)", BLOCKS))
    assert {"generate", "validate", "repro", "load-sql", "report"} <= cmds
    for c in cmds:
        r = subprocess.run([sys.executable, "-m", "oryva", c, "--help"], capture_output=True, text=True)
        assert r.returncode == 0, (c, r.stderr[-300:])


def test_every_script_and_path_referenced_in_readme_exists():
    for p in set(re.findall(r"(?:python|powershell -File) (scripts/[\w./-]+)", BLOCKS)):
        assert Path(p).exists(), p
    for p in ("app.py", "profiles/full.yaml", "profiles/starter.yaml", "profiles/tiny.yaml", "profiles/policies.yaml", "PROJECT_PLAN.md",
              "REQUIREMENTS_AUDIT.md", "FINAL_REPORT.md", "docs/data_model.md", "docs/test_results.txt", "docs/reproducibility_full.md",
              "docs/reproducibility_starter.md", "docs/audit_evidence_full.json", "docs/audit_evidence_starter.json"):
        assert Path(p).exists(), p


def test_readme_profile_table_matches_profiles():
    from oryva.config import load_profile
    for name, skus in (("tiny", 60), ("starter", 300), ("full", 3000)):
        p = load_profile(name)
        assert p["n_skus"] == skus and re.search(rf"\| `{name}` \| {skus:,}".replace(",", ",?") if name == "full" else rf"\| `{name}` \| {skus}", README.replace("**", "")), name
    assert load_profile("full")["assortment_density"] == 0.10 and "20261022" in README
