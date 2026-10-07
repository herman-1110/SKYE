"""Compare two ab_run.py traces + their console (stdout) files -> a text report.

usage: python -B ab_compare.py <A_trace.json> <B_trace.json> <A_stdout.txt> <B_stdout.txt> <out.txt>
The last replay step (p5 rssinull, a JSON-null rssi) is reported separately: it differs by
design between a pre-128 A and a post-128 B. Console lines are compared with every
[MEMBERSHIP-128] line removed from BOTH sides (a pre-128 A has none), and raw as well."""
import json, sys, io, re
a = json.load(open(sys.argv[1], encoding="utf-8")); b = json.load(open(sys.argv[2], encoding="utf-8"))
out = io.open(sys.argv[5], "w", encoding="utf-8")
out.write(f"steps A={len(a)} B={len(b)}\n")
diffs = [(x["label"], k) for x, y in zip(a, b) for k in x if x[k] != y[k]]
out.write(f"steps differing (excluding last): {[d for d in diffs if not d[0].startswith('p5')]}\n")
out.write(f"last step A: {a[-1]['res']}\nlast step B: {b[-1]['res']}\n")
out.write(f"last step diffs: {[d for d in diffs if d[0].startswith('p5')]}\n")
out.write(f"worker position before/after p5 A={a[-2]['positions'].get('test-128-worker', {}).get('timestamp')}->{a[-1]['positions'].get('test-128-worker', {}).get('timestamp')} B={b[-2]['positions'].get('test-128-worker', {}).get('timestamp')}->{b[-1]['positions'].get('test-128-worker', {}).get('timestamp')}\n")
out.write(f"null counters end A={a[-1]['null']} B={b[-1]['null']}\n")
# decisions: count position writes by type over the run (from timestamp changes)
def writes(tr):
    n = {"exact": 0, "approx": 0}; prev = {}
    for s in tr[:-1]:
        for k, v in s["positions"].items():
            if prev.get(k) != v.get("timestamp") and v.get("timestamp") and not k.startswith("test-128-stale"):
                n["approx" if v["is_approximate"] else "exact"] += 1
            prev[k] = v.get("timestamp")
    return n
out.write(f"position writes before p5 A={writes(a)} B={writes(b)}\n")
# console: identical once [MEMBERSHIP-128] lines are removed?
ha = open(sys.argv[3], "rb").read().decode("utf-8").splitlines()
hb = open(sys.argv[4], "rb").read().decode("utf-8").splitlines()
is_mem = lambda l: l.startswith("[MEMBERSHIP-128]")
ha_wo = [l for l in ha if not is_mem(l)]
hb_wo = [l for l in hb if not is_mem(l)]
mem_a = [l for l in ha if is_mem(l)]
mem_b = [l for l in hb if is_mem(l)]
out.write(f"console lines A={len(ha)} B={len(hb)} A-without-MEMBERSHIP={len(ha_wo)} "
          f"B-without-MEMBERSHIP={len(hb_wo)} identical={ha_wo == hb_wo} raw_identical={ha == hb}\n")
if ha_wo != hb_wo:
    import difflib
    out.write("\n".join(list(difflib.unified_diff(ha_wo, hb_wo, lineterm="", n=1))[:40]) + "\n")
from collections import Counter
oc = lambda mem: dict(Counter(re.search(r'outcome=(\S+)( reason=\S+)?', l).group(0) for l in mem))
out.write(f"MEMBERSHIP outcomes A: {oc(mem_a)}\n")
out.write(f"MEMBERSHIP outcomes B: {oc(mem_b)}\n")
out.close()
