"""probe.py <script> [args...]: run a script as __main__ until argparse parses its arguments, print them, exit 0.

Observes the effective defaults (and flag overrides) a script ends up with, without depending on its variable names.
"""
import argparse
import json
import os
import runpy
import sys

_orig_parse_known = argparse.ArgumentParser.parse_known_args


def _hook(self, args=None, namespace=None):
    ns, rest = _orig_parse_known(self, args, namespace)
    if getattr(self, "_probe_inner", False):
        return ns, rest
    sys.stdout.write("PROBE_ARGS " + json.dumps(vars(ns), default=str) + "\n")
    sys.stdout.flush()
    os._exit(0)


argparse.ArgumentParser.parse_known_args = _hook   # parse_args calls parse_known_args

script = sys.argv[1]
sys.argv = [script] + sys.argv[2:]
sys.path.insert(0, os.path.dirname(os.path.abspath(script)))
runpy.run_path(script, run_name="__main__")
print("PROBE_NO_ARGPARSE")
sys.exit(3)
