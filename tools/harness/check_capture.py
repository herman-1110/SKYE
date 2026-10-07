"""Console-vs-capture coverage check for one run: reads every skye-* capture file in <capture_dir>
and the run's console logs (<run_dir>/stdout.log, stderr.log), and reports encoding/BOM, timestamp
prefixes, [OMADA] dump, access/request_logger lines, [MEMBERSHIP-128] outcomes, and every console
line that is missing from the capture file.

usage: python -B check_capture.py <capture_dir> <run_dir> <out.txt>
  e.g. <capture_dir> = <export>/backend/logs, <run_dir> = a run_smoke.py or kill_test.py run dir"""
import sys, io, re, glob, os
logdir, rundir, out_path = sys.argv[1], sys.argv[2], sys.argv[3]
out = io.open(out_path, "w", encoding="utf-8")
files = sorted(glob.glob(os.path.join(logdir, "skye-*")))
out.write(f"capture files: {[os.path.basename(f) for f in files]}\n")
raw = b"".join(open(f, "rb").read() for f in files)
out.write(f"bytes={len(raw)} utf8_bom={raw[:3]==b'\xef\xbb\xbf'} utf16_bom={raw[:2] in (b'\xff\xfe', b'\xfe\xff')}\n")
txt = raw.decode("utf-8")  # strict
lines = txt.splitlines()
pref = re.compile(r"^(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}Z) (.*)$")
bodies = []
bad = 0
for l in lines:
    m = pref.match(l)
    if not m: bad += 1; continue
    bodies.append(m.group(2))
out.write(f"lines={len(lines)} unprefixed={bad}\n")
body_set = set(bodies)
out.write(f"box-drawing dump lines: {sum(1 for b in bodies if '[OMADA]' in b and any(c in b for c in '═┌│└─'))}\n")
out.write(f"sample dump line: {next((b for b in bodies if '┌─ Beacon' in b), None)}\n")
out.write(f"uvicorn access 200s: {sum(1 for b in bodies if 'POST /telemetry/omada HTTP/1.1' in b)}\n")
out.write(f"request_logger lines: {sum(1 for b in bodies if '[POST] /telemetry/omada' in b)}\n")
out.write(f"uvicorn lifecycle: {[b for b in bodies if any(k in b for k in ('Started server process','Application startup complete','Uvicorn running','Shutting down','Finished server process'))]}\n")
out.write(f"NULL-RATE lines: {[b for b in bodies if 'OMADA-NULL-RATE' in b]}\n")
out.write(f"harness clean exit in file: {any('[HARNESS] clean exit' in b for b in bodies)}\n")
mem = [b for b in bodies if b.startswith('[MEMBERSHIP-128]')]
from collections import Counter
oc = Counter(re.search(r'outcome=(\S+)', b).group(1) + (('/' + re.search(r'reason=(\S+)', b).group(1)) if 'reason=' in b else '') for b in mem)
out.write(f"MEMBERSHIP lines={len(mem)} outcomes={dict(oc)}\n")
ok_tok = all(all('=' in t for t in b.split()[1:]) for b in mem)
out.write(f"every membership token is key=value: {ok_tok}\n")
out.write("--- all MEMBERSHIP lines (with file timestamp) ---\n")
for l in lines:
    if '[MEMBERSHIP-128]' in l: out.write(l + "\n")
# console coverage: every console line should be in the file (except lines printed before install)
ansi = re.compile(r"\x1b\[[0-9;]*m")
missing = []
for name in ("stdout.log", "stderr.log"):
    craw = open(os.path.join(rundir, name), "rb").read().decode("utf-8", "replace")
    for cl in craw.splitlines():
        c = ansi.sub("", cl).rstrip("\r")
        if c and c not in body_set:
            missing.append((name, c[:160]))
out.write(f"--- console lines NOT in capture file: {len(missing)} ---\n")
for m in missing: out.write(f"{m}\n")
out.close()
