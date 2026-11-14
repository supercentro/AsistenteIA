"""Test wrapper around the real docker client: records every argument and the standard input of `exec ... -f -`, then forwards both."""

import os
import subprocess
import sys

args = sys.argv[1:]
with open(os.environ["ROT_SHIM_ARGLOG"], "a", encoding="utf-8") as log:
    log.write(" ".join(args) + chr(10))
data = None
if args[:1] == ["exec"] and "-f -" in " ".join(args):
    data = sys.stdin.buffer.read()
    with open(os.environ["ROT_SHIM_STDINLOG"], "ab") as log:
        log.write(data + chr(10).encode())
proc = subprocess.run([os.environ["ROT_SHIM_REAL"], *args], input=data, capture_output=True, check=False)
sys.stdout.buffer.write(proc.stdout)
sys.stderr.buffer.write(proc.stderr)
sys.exit(proc.returncode)
