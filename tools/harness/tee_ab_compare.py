"""Compare two AB runs made with AB_CAPTURE_DIR set: console bytes and capture-file bodies (timestamps stripped).

usage: python -B tee_ab_compare.py <A_stdout.txt> <B_stdout.txt> <A_capture_dir> <B_capture_dir>
Each capture dir must hold only that run's skye-* files (put it inside the ab_run --run-dir,
which is wiped at the start of every run)."""
import sys, glob, io, os
a_console, b_console, a_dir, b_dir = sys.argv[1:5]
def lines(p): return open(p, "rb").read().decode("utf-8").splitlines()
def cap(d):
    L = []
    for f in sorted(glob.glob(os.path.join(d, "skye-*"))): L += io.open(f, encoding="utf-8").read().splitlines()
    return [l[25:] for l in L]
drop = lambda L: [l for l in L if not l.startswith("[CAPTURE-128] writing console output to")]
ca, cb = drop(lines(a_console)), drop(lines(b_console))
fa, fb = drop(cap(a_dir)), drop(cap(b_dir))
print(f"console lines A={len(ca)} B={len(cb)} identical={ca == cb}")
print(f"capture lines A={len(fa)} B={len(fb)} identical={fa == fb}")
print(f"every console line also in B's capture: {set(cb) <= set(fb)}  (missing {len(set(cb) - set(fb))})")
print(f"console-dead warnings in B capture: {sum('WARNING: console' in l for l in fb)}")
