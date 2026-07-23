#!/usr/bin/env python3
"""Micro-benchmark to compare initialization + generate latency for local vs cloud path.

Usage:
  python3 scripts/bench_latency.py --mode local
  python3 scripts/bench_latency.py --mode cloud

It runs a small DriftBrain init and one `think()` call and reports elapsed time.
"""

import os
import subprocess
import sys

MODE = "local"
if len(sys.argv) > 1:
    MODE = sys.argv[1]

# Determine env overrides
env = os.environ.copy()
if MODE == "local":
    env["DRIFT_PREFER_LOCAL"] = "true"
else:
    env["DRIFT_PREFER_LOCAL"] = "false"

snippet = r"""
import time, os
from drift.core.brain import DriftBrain
b = DriftBrain()
start = time.time()
# run a quick think — use short prompt
try:
    out = b.think('Hello test latency')
except Exception as e:
    out = str(e)
print('elapsed', time.time()-start)
print('sdk', getattr(b,'sdk',None))
"""

cmd = [sys.executable, "-c", snippet]
print(f"Running benchmark mode={MODE}...")
proc = subprocess.run(cmd, env=env, capture_output=True, text=True)
print(proc.stdout)
if proc.stderr:
    print(proc.stderr, file=sys.stderr)
