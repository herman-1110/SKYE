"""List (path, size, mtime) of every file under the repo except venv/.git/node_modules and
tools/harness/runs -> json. Read-only. Take one before and one after a harness run and diff
them to prove nothing outside the run dirs changed (catches git-ignored files too).

usage: python -B repo_snapshot.py <out_json>"""
import json, os, sys
HARNESS_DIR = os.path.dirname(os.path.abspath(__file__))
root = os.path.dirname(os.path.dirname(HARNESS_DIR))   # tools/harness -> repo root
runs = os.path.normcase(os.path.join(HARNESS_DIR, "runs"))
out = {}
for dp, dns, fns in os.walk(root):
    dns[:] = [d for d in dns if d not in ("venv", ".git", "node_modules")
              and os.path.normcase(os.path.join(dp, d)) != runs]
    for fn in fns:
        p = os.path.join(dp, fn)
        try:
            st = os.stat(p)
            out[os.path.relpath(p, root)] = [st.st_size, st.st_mtime_ns]
        except OSError:
            pass
json.dump(out, open(sys.argv[1], "w", encoding="utf-8"))
print(len(out))
