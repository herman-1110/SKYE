#!/usr/bin/env python3
"""
analyze_measure_112.py — Handoff v19 §7.1 analysis

Usage:
    python3 analyze_measure_112.py <logfile>

Reads the raw tee'd capture. Needs the [OMADA] dumps present — they carry the
RSSI-presence layer, which [MEASURE-112] alone cannot show.

stdlib only. Reports MEASURE #1-#5 plus per-AP report cadence and empty-RSSI rate.
"""

import json
import math
import re
import statistics
import sys
from collections import defaultdict
from datetime import datetime

HOLD_SECONDS = 10.0        # POSITION_EXACT_HOLD_SECONDS
MIN_APS = 3                # MIN_APS_FOR_POSITION
BUFFER_WINDOW_S = 2.0      # staleness TTL + wait window (double duty)
MAN_DOWN_EPSILON_M = 2.0   # MAN_DOWN_MOVEMENT_EPSILON_M (uncalibrated guess)

RE_MEASURE = re.compile(
    r"\[MEASURE-112\]\s+ts=(\S+)\s+id=(\S+)\s+ap_count=(\d+)\s+aps=\[(.*?)\]"
)
RE_SOLVE = re.compile(r"\[MEASURE-112-SOLVE\]\s+(.*)")
RE_KV = re.compile(r"(\w+)=([^\s]+)")
RE_MAC_IN_LIST = re.compile(r"'([0-9A-Fa-f:]+)'")
RE_RAW_JSON = re.compile(r"\[OMADA\]\s+(\{.*\})\s*$")


def norm_mac(mac):
    return re.sub(r"[^0-9A-Fa-f]", "", mac).upper()


def open_log(path):
    """PS 5.1 Tee-Object writes UTF-16LE; PS 6+ writes UTF-8; plain redirects may be
    cp1252. Sniff the BOM, then fall back."""
    with open(path, "rb") as fh:
        head = fh.read(4)
    if head[:2] in (b"\xff\xfe", b"\xfe\xff"):
        enc = "utf-16"
    elif head[:3] == b"\xef\xbb\xbf":
        enc = "utf-8-sig"
    else:
        enc = "utf-8"
    try:
        return open(path, "r", encoding=enc, errors="replace")
    except (LookupError, UnicodeError):
        return open(path, "r", encoding="cp1252", errors="replace")


def parse(path):
    flushes = []          # (ts, beacon_id, ap_count, [normalised macs])
    solves = []           # dict of parsed key=values
    reports = []          # (reporter_mac, reporter_name, time, [(beacon_id, has_rssi)])

    with open_log(path) as fh:
        for line in fh:
            m = RE_MEASURE.search(line)
            if m:
                ts_s, bid, count, aps_s = m.groups()
                try:
                    ts = datetime.fromisoformat(ts_s)
                except ValueError:
                    continue
                macs = [norm_mac(x) for x in RE_MAC_IN_LIST.findall(aps_s)]
                flushes.append((ts, bid, int(count), macs))
                continue

            m = RE_SOLVE.search(line)
            if m:
                solves.append(dict(RE_KV.findall(m.group(1))))
                continue

            m = RE_RAW_JSON.search(line)
            if m:
                try:
                    doc = json.loads(m.group(1))
                except json.JSONDecodeError:
                    continue        # truncated / interleaved line
                rep = doc.get("reporter", {})
                rmac = norm_mac(rep.get("mac", ""))
                if not rmac:
                    continue
                beacons = []
                for b in doc.get("reported", []):
                    ib = b.get("ibeacon") or {}
                    if not ib:
                        continue
                    bid = f"{ib.get('uuid','')}:{ib.get('major','')}:{ib.get('minor','')}"
                    has_rssi = "avg" in (b.get("rssi") or {})
                    beacons.append((bid, has_rssi))
                reports.append((rmac, rep.get("name", "?"), rep.get("time", ""), beacons))

    return flushes, solves, reports


def hr(title):
    print(f"\n{'=' * 72}\n{title}\n{'=' * 72}")


def main(path):
    flushes, solves, reports = parse(path)
    if not flushes:
        print("No [MEASURE-112] lines found. Wrong file?")
        return

    span = (flushes[-1][0] - flushes[0][0]).total_seconds()
    beacons = sorted({b for _, b, _, _ in flushes})
    print(f"Capture span : {span:.1f}s ({span/60:.1f} min)")
    print(f"Flush lines  : {len(flushes)}   Solve lines: {len(solves)}   "
          f"AP reports: {len(reports)}")
    print(f"Beacons      : {len(beacons)}")

    # ---------------------------------------------------------------- MEASURE #1
    hr("MEASURE #1 — AP-count distribution per flush, per beacon")
    per_beacon = defaultdict(list)
    for ts, bid, count, macs in flushes:
        per_beacon[bid].append((ts, count, macs))

    for bid in beacons:
        rows = per_beacon[bid]
        n = len(rows)
        dist = defaultdict(int)
        for _, c, _ in rows:
            dist[c] += 1
        eligible = sum(v for k, v in dist.items() if k >= MIN_APS)
        print(f"\n  {bid}   n={n}")
        for k in sorted(dist):
            pct = 100.0 * dist[k] / n
            print(f"    ap_count={k}: {dist[k]:5d}  {pct:5.1f}%  {'#' * int(pct / 2)}")
        print(f"    -> exact-solve eligible (>={MIN_APS}): {100.0*eligible/n:.1f}%")

    # ---------------------------------------------------------------- MEASURE #2
    hr("MEASURE #2 — per-AP presence rate (consistent offender vs rotating)")
    all_aps = sorted({m for _, _, _, macs in flushes for m in macs})
    for bid in beacons:
        rows = per_beacon[bid]
        n = len(rows)
        print(f"\n  {bid}")
        for ap in all_aps:
            present = sum(1 for _, _, macs in rows if ap in macs)
            print(f"    {ap}: present in {present:5d}/{n} flushes  "
                  f"{100.0*present/n:5.1f}%")
    print("\n  Flat rates across APs -> rotating dropout (RF / scan duty-cycle).")
    print("  One AP markedly lower  -> consistent offender (placement or config).")

    # ---------------------------------------------------------------- MEASURE #3
    hr("MEASURE #3 — exact-solve spread  (is_approximate=False ONLY)")
    if not solves:
        print("  No [MEASURE-112-SOLVE] lines. Cannot compute. This is the number")
        print("  that has never been measured — do not substitute anything else.")
    else:
        by_beacon = defaultdict(list)
        contaminated = 0
        for s in solves:
            approx = str(s.get("is_approximate", "")).lower()
            if approx in ("true", "1"):
                contaminated += 1
                continue            # §3: filter FIRST, compute SECOND
            try:
                x, y = float(s.get("x")), float(s.get("y"))
            except (TypeError, ValueError):
                continue
            by_beacon[s.get("id", "?")].append((x, y))

        if contaminated:
            print(f"  !! {contaminated} approximate sample(s) excluded. Correct — a")
            print("     statistic over a mixed sample measures AP separation, not")
            print("     accuracy. This is exactly how the 4.96m error happened.\n")

        for bid, pts in sorted(by_beacon.items()):
            n = len(pts)
            xs = [p[0] for p in pts]
            ys = [p[1] for p in pts]
            print(f"  {bid}   n={n}")
            if n < 2:
                print("    too few exact solves to compute spread")
                continue
            print(f"    x: mean={statistics.mean(xs):7.3f}  "
                  f"stdev={statistics.stdev(xs):6.3f}  "
                  f"range={max(xs)-min(xs):6.3f}")
            print(f"    y: mean={statistics.mean(ys):7.3f}  "
                  f"stdev={statistics.stdev(ys):6.3f}  "
                  f"range={max(ys)-min(ys):6.3f}")

            mx, my = statistics.mean(xs), statistics.mean(ys)
            ax, ay = pts[0]
            d_mean = [math.hypot(x - mx, y - my) for x, y in pts]
            d_anchor = [math.hypot(x - ax, y - ay) for x, y in pts]
            over = sum(1 for d in d_anchor if d > MAN_DOWN_EPSILON_M)
            print(f"    2D displacement from mean : max={max(d_mean):6.3f}m")
            print(f"    2D displacement from first: max={max(d_anchor):6.3f}m  "
                  f"(man-down anchor proxy)")
            print(f"    samples over MAN_DOWN_MOVEMENT_EPSILON_M "
                  f"({MAN_DOWN_EPSILON_M}m): {over}/{n}")
            if max(d_anchor) > MAN_DOWN_EPSILON_M:
                print("    !! ON A STATIONARY CAPTURE this means man-down is defeated")
                print("       by solve noise alone: the anchor resets and the stillness")
                print("       timer restarts. Separate from the §4 approximate-position")
                print("       defect, and NOT fixed by Prompt 111.")
                print("       On a moving capture it means nothing — check which.")
        print("\n  Cross-check: if two beacons report near-identical spread to the")
        print("  centimetre, that is an AP-separation artefact, not RF noise.")
        print("  Compare any range against your AP pair distances before believing it.")

    # ---------------------------------------------------------------- MEASURE #4
    hr("MEASURE #4 — flap rate, from ap_count (NOT emitted is_approximate)")
    for bid in beacons:
        rows = per_beacon[bid]
        sub = sum(1 for _, c, _ in rows if c < MIN_APS)
        print(f"  {bid}: under-{MIN_APS}-AP in {sub}/{len(rows)} flushes  "
              f"{100.0*sub/len(rows):.1f}%")
    print("\n  Baseline to beat: ~50% (v19 §1). Expect roughly UNCHANGED — Prompt 111")
    print("  suppressed the consequence, not the cause. A large drop here means the")
    print("  log is wired to the suppressed path and the measurement is worthless.")

    # ---------------------------------------------------------------- MEASURE #5
    hr(f"MEASURE #5 — continuous under-{MIN_APS}-AP runs vs "
       f"POSITION_EXACT_HOLD_SECONDS ({HOLD_SECONDS}s)")
    for bid in beacons:
        rows = sorted(per_beacon[bid], key=lambda r: r[0])
        runs, start, censored = [], None, False
        for i, (ts, c, _) in enumerate(rows):
            if c < MIN_APS and start is None:
                start = ts
            elif c >= MIN_APS and start is not None:
                runs.append((ts - start).total_seconds())
                start = None
        if start is not None:
            runs.append((rows[-1][0] - start).total_seconds())
            censored = True

        print(f"\n  {bid}: {len(runs)} run(s)")
        if not runs:
            print("    none")
            continue
        over = [r for r in runs if r > HOLD_SECONDS]
        print(f"    longest={max(runs):.2f}s  median={statistics.median(runs):.2f}s  "
              f"mean={statistics.mean(runs):.2f}s")
        print(f"    runs exceeding {HOLD_SECONDS}s hold window: {len(over)}"
              f"  ({100.0*len(over)/len(runs):.1f}%)")
        if censored:
            print("    NOTE: final run was still open at end of capture "
                  "(right-censored, may be longer)")
        if over:
            print("    -> §6 anchor-guard edge case IS REAL. Hold expires, anchor goes")
            print("       approximate, 5m teleport returns. Cross-check against the")
            print("       marginal-coverage man-down test (runbook C2).")
        else:
            print("    -> hold window covers every observed run. Edge case not")
            print("       reproduced in this capture.")

    # ------------------------------------------------- AP cadence + empty RSSI
    hr("AP report cadence  (vs BUFFER_WINDOW_S = %.1fs staleness TTL)" % BUFFER_WINDOW_S)
    by_ap_ts = defaultdict(list)
    order = defaultdict(list)
    for idx, (rmac, rname, rtime, _) in enumerate(reports):
        by_ap_ts[(rmac, rname)].append(idx)
    for (rmac, rname), idxs in sorted(by_ap_ts.items()):
        rate = len(idxs) / span if span else 0
        print(f"  {rname:12s} {rmac}: {len(idxs):5d} reports  ~{rate:.2f}/s")
    print(f"\n  An AP reporting slower than 1/{BUFFER_WINDOW_S:.0f}s has its readings")
    print("  expire before the next arrives — it can never contribute two windows")
    print("  running. That is an Omada-side config lever, not a code fix.")

    hr("BEACON VISIBILITY PER AP — three-way (absent / rssi-null / rssi-ok)")
    if not reports:
        print("  No parseable [OMADA] raw JSON. Re-run against the unfiltered log —")
        print("  [MEASURE-112] alone cannot distinguish 'did not hear' from")
        print("  'heard, omitted RSSI'.")
    else:
        totals = defaultdict(int)
        stat = defaultdict(lambda: [0, 0])   # (rname, rmac, bid) -> [seen, has_rssi]
        all_bids = set()
        for rmac, rname, _, blist in reports:
            totals[(rname, rmac)] += 1
            for bid, has in blist:
                all_bids.add(bid)
                stat[(rname, rmac, bid)][0] += 1
                stat[(rname, rmac, bid)][1] += 1 if has else 0

        for (rname, rmac), tot in sorted(totals.items()):
            print(f"\n  {rname} {rmac} — {tot} reports")
            for bid in sorted(all_bids):
                seen, has = stat.get((rname, rmac, bid), [0, 0])
                absent, null = tot - seen, seen - has
                print(f"    {bid[-9:]}: absent {absent:5d} ({100.0*absent/tot:5.1f}%)  "
                      f"rssi-null {null:5d} ({100.0*null/tot:5.1f}%)  "
                      f"rssi-ok {has:5d} ({100.0*has/tot:5.1f}%)")

        print("\n  rssi-null dominant -> AP reporting behaviour, fixable in Omada config.")
        print("  absent dominant     -> genuine non-hearing: placement or RF.")
        print("  Both non-trivial    -> two problems; the config one is far cheaper.")
        print("\n  Watch for any beacon with low rssi-ok across ALL THREE APs at once.")
        print("  That is the /beacon_scans blackout (omada_ingest_service.py:384-386):")
        print("  the beacon reads OFFLINE while every AP is hearing it, and an")
        print("  unregistered one never appears in register-from-scan at all.")

    hr("Solve pairing")
    eligible = sum(1 for _, _, c, _ in flushes if c >= MIN_APS)
    print(f"  flushes with ap_count>={MIN_APS}: {eligible}")
    print(f"  [MEASURE-112-SOLVE] lines      : {len(solves)}")
    if eligible and len(solves) < eligible * 0.9:
        print("  -> Fewer solves than eligible flushes. Most likely EMIT_MIN_INTERVAL_S")
        print("     (1.8s) pacing emission, with the SOLVE log sitting after the emit")
        print("     check. Confirm before reading any gap as a failed solve.")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(1)
    main(sys.argv[1])