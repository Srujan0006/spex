"""Mutation run for the reference interpreter and the compiler: each mutant in tests/model/mutants.py must make tests/model fail.
    python3 -B scripts/mutate_model.py          (writes scripts/mutate_model_results.json)"""
import concurrent.futures as cf
import json
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tests", "model"))
from mutants import MUTANTS  # noqa: E402


def run(i):
    f, name, rule, old, new, killer = MUTANTS[i]
    with tempfile.TemporaryDirectory() as d:
        for sub in ("spex", "tests"):
            shutil.copytree(os.path.join(ROOT, sub), os.path.join(d, sub),
                            ignore=shutil.ignore_patterns("__pycache__"))
        shutil.copy(os.path.join(ROOT, "pyproject.toml"), d)
        p = os.path.join(d, f)
        src = open(p).read()
        assert src.count(old) == 1, name
        open(p, "w").write(src.replace(old, new))
        r = subprocess.run([sys.executable, "-B", "-m", "pytest", "-x", "-q", "tests/model",
                            "--deselect", "tests/model/test_mutants_wellformed.py"],
                           cwd=d, capture_output=True, text=True)
        failed = [l for l in r.stdout.splitlines() if l.startswith("FAILED")]
    return {"file": f, "mutant": name, "rule": rule, "killed": r.returncode != 0, "first_failure": failed[:1]}


def main():
    base = subprocess.run([sys.executable, "-B", "-m", "pytest", "-x", "-q", "tests/model"], cwd=ROOT,
                          capture_output=True, text=True)
    if base.returncode != 0:                       # a red baseline would "kill" every mutant
        print("baseline tests fail; fix them before the mutation run\n" + base.stdout[-2000:])
        return 2
    with cf.ProcessPoolExecutor() as ex:
        results = list(ex.map(run, range(len(MUTANTS))))
    for r in results:
        print(("KILLED  " if r["killed"] else "SURVIVED") + f"  [{r['rule']}] {r['mutant']}  {r['first_failure']}")
    killed = sum(r["killed"] for r in results)
    print(f"{killed}/{len(results)} mutants killed")
    json.dump(results, open(os.path.join(ROOT, "scripts", "mutate_model_results.json"), "w"), indent=1)
    return 0 if killed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
