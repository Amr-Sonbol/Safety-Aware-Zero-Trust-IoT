"""Entry point for Phase 0 validation.

Run:
    python run_phase0.py

Prints a PASS/FAIL report for all six Phase 0 checks and exits with code 0
(all pass) or 1 (any fail).
"""

import sys
import os

# Ensure the package root is on the path when invoked from the project root.
sys.path.insert(0, os.path.dirname(__file__))

from zt_cps_phase0.src import runner

if __name__ == "__main__":
    ok = runner.run_phase0()
    sys.exit(0 if ok else 1)
