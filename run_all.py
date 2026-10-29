"""Run everything: fetch data, build datasets, tests, all notebooks.

    python run_all.py [--refresh | --skip-fetch]
"""

import argparse
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
NOTEBOOKS = ["01_eda", "02_why_it_changed", "03_forecasts_to_2030", "04_prevention_scenarios"]


def step(title, cmd, cwd=ROOT):
    print(f"\n=== {title} ===", flush=True)
    start = time.time()
    result = subprocess.run(cmd, cwd=cwd)
    if result.returncode != 0:
        sys.exit(f"\nStopped: '{title}' failed (see the error above). Fix it, then run again "
                 f"(add --skip-fetch to reuse the data already downloaded).")
    print(f"--- done in {time.time() - start:.0f}s", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--refresh", action="store_true", help="re-download cached data")
    parser.add_argument("--skip-fetch", action="store_true", help="don't download, use existing data/raw files")
    args = parser.parse_args()
    py = sys.executable

    if not args.skip_fetch:
        step("1/4 Downloading data from WHO and the World Bank (several minutes)",
             [py, "-m", "src.fetch_data"] + (["--refresh"] if args.refresh else []))
    step("2/4 Building the analysis datasets", [py, "-m", "src.build_dataset"])
    step("3/4 Running tests", [py, "-m", "pytest", "-q"])
    for i, nb in enumerate(NOTEBOOKS, 1):
        step(f"4/4 Running notebook {i} of {len(NOTEBOOKS)}: {nb}",
             [py, "-m", "jupyter", "nbconvert", "--to", "notebook", "--execute", "--inplace",
              "--ExecutePreprocessor.timeout=1800", f"{nb}.ipynb"],
             cwd=ROOT / "notebooks")

    print("\nAll done. Open the notebooks to read the results:  jupyter lab")
    print(f"Charts are in {ROOT / 'reports' / 'figures'}")


if __name__ == "__main__":
    main()
