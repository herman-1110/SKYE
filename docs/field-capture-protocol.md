# SKYE — field capture protocol

*Updated 30 Sep. Replaces the 23 Sep version: the backend writes its own capture file now, the launch command changed, and the guard/worker mapping is settled.*

One session, about an hour, three APs live, post-upgrade firmware. It produces four things that are currently missing:

1. AP geometry ground truth (tape measure, not Firestore).
2. A measured TX reference **and** a measured path-loss exponent, per AP.
3. Null run-length data with three APs reporting.
4. A reproducible stationary precision table.

Nothing here changes code. One `.env` flag goes on for the session and off afterwards. Read the whole thing once before starting.

---

## Launch the capture

Since Prompt 128 the backend writes its own capture file: `backend\logs\skye-<UTC yyyymmdd-HHMMSS>.log`, UTF-8, no BOM, a UTC timestamp on every line. No `Tee-Object`, no encoding check.

1. In `backend\.env`, set `OMADA_RAW_DUMP_ENABLED=true`. Settings are read once at startup, so it goes in before the launch.
2. Stop the running dev server (Ctrl+C in its window).
3. Open a **fresh** PowerShell window, so nothing carries over from the old capture ritual. A variable set in a terminal silently overrides `.env`.
4. From `backend`:

   ```powershell
   .\venv\Scripts\python.exe -m uvicorn main:app --host 0.0.0.0 --port 8000
   ```

   No `--reload`: with it, saving any `.py` file (yours or the Codex agent's) restarts the server mid-capture. No `-u`, no `Tee-Object`.

5. Within 30 seconds, in a second window:

   ```powershell
   Get-ChildItem .\logs | Sort-Object LastWriteTime | Select-Object -Last 1
   ```

   Write the file name in the notebook. Run it again a few seconds later; the size should have grown. The server window should be scrolling both `[OMADA] AP REPORT` blocks and `[MEMBERSHIP-128]` lines.

If the backend restarts for any reason, a new file starts on its own: note the time. If a file reaches its size limit it continues as `skye-<ts>.part002.log`; keep every part.

**Carry a paper notebook.** Every dwell needs a start and stop time to the second, in local time. Write "+08:00" once at the top; the file is in UTC. Check the phone clock against the PC clock and note any offset.

---

## Pre-flight (10 min, before any measurement)

- [x] All three APs POSTing — confirmed 30 Sep 09:06, from `.3`, `.4` and `.6`. DHCP moved them; nothing to fix.
- [x] `guard-001` is `0000:0001` (`C3:00:00:71:FA:74`); `worker-001` is `0000:0000` (`C3:00:00:71:FA:AA`). Settled from live `[MEMBERSHIP-128]` lines.
- [ ] From each AP's first `[OMADA]` reporter block: name, mac, IP, `swVersion`, `swBuild`. `34:5C` was on 1.6.6 on 10 Sep, one version behind `34:5A`; a firmware difference alone could explain a different null rate.
- [ ] Beacon batteries from the first report of each. FAAA was at 59%, FA74 at 85%. A weak cell transmits weaker, so record it before calibrating against it.
- [ ] How each AP is mounted (ceiling, wall or desk) and its height above the floor, plus the height you'll hold the beacons at. Every distance below depends on these.

---

## Slant range — read this before measuring anything

An AP mounted above the beacon is never at zero distance from it, even directly underneath:

```
slant = sqrt( horizontal² + (AP_height − beacon_height)² )
```

With the AP at 3.0 m and the beacon at 1.0 m, directly underneath is 2.0 m of slant range, and 1 m horizontal is 2.24 m. The positioning model is 2D and treats every range as horizontal, so this matters twice: once for the calibration, and once because a ceiling AP inflates every computed distance near it.

Measure and record **horizontal** distance along the floor; the replay converts to slant from the heights. If an AP sits at beacon height (desk or wall), slant and horizontal are the same.

---

## Part A — geometry (15 min)

Mark the floor point directly beneath each AP with tape. A plumb line, or a phone level against the mount, is accurate enough.

| Measurement | Value |
|---|---|
| EAP770 ↔ 34:5A | |
| EAP770 ↔ 34:5C | |
| 34:5A ↔ 34:5C | |
| Height, EAP770 | |
| Height, 34:5A | |
| Height, 34:5C | |
| Beacon height | |

Then pick a floor origin and an axis direction — a room corner and a wall — and measure each AP's x and y from it. Write down which corner and which wall; a future session has to reproduce this.

Note the Firestore `x_m`/`y_m` beside them. **Record both, change nothing.** Correcting Firestore means dragging AP icons on the floor plan, which adds its own error, and the replay can test the tape coordinates offline anyway. It also checks itself against today's live positions, which were computed with today's coordinates, so leave them alone until it has run.

Leave the tape marks in place.

---

## Part B — RSSI against distance (18 min)

The core of the session. Several distances give you the TX reference *and* the path-loss exponent from one fit, instead of measuring one and assuming the other.

**EAP770, full sweep.** Both beacons side by side on a stand or box at the recorded height, clear line of sight, nobody between them and the AP. Move along one straight line away from the AP and write down its direction (for example "towards 34:5A"). Distances by tape, not by eye: at 1 m, a 30 cm error is 3–4 dB.

| Horizontal | Start | Stop |
|---|---|---|
| 0 m (directly beneath; skip if the AP is at beacon height) | | |
| 1 m | | |
| 2 m | | |
| 4 m | | |
| 8 m | | |

**90 seconds at each point**, timed from when you've stepped back. At about 1 Hz with a quarter of readings null, that's roughly 65 usable readings per AP — enough for a stable median.

**The other two APs, short version:** 1 m and 4 m horizontal, 90 s each. Enough to see whether they need their own TX constant.

---

## Part C — body attenuation (5 min)

Skip only if you're out of time. At the EAP770's 4 m point, three 90-second dwells:

1. Beacons on the stand, nobody near.
2. One beacon worn as a guard would wear it, facing the AP.
3. Same, facing away.

2.4 GHz through a torso typically costs several dB. If it does here, every constant calibrated on a bare beacon is wrong for a worn one.

---

## Part D — stationary precision and null runs (6 min)

One point roughly in the middle of the three APs, recorded in Part A's frame. Both beacons on the stand. **Five continuous minutes**, nobody moving nearby.

This gives the reproducible precision table, and the null run-length distribution with all three APs live, which is what sizes Prompt 129's grace period. The middle matters: parked near one AP, the far APs may null more (today's first counters hint at it), and the run lengths would describe the placement rather than the system.

---

## Part E — one walk (5 min)

Mark two floor points 10–15 m apart. Walk between them at patrol pace, twice each way, pausing 10 s at each end. Note the times.

Shows error in motion, and whether the 10-second hold and the strongest-AP snap fire during normal movement. Each `[MEMBERSHIP-128]` line says which.

---

## If the hour runs short

Pre-flight → A → B (EAP770) → D → C → B (other two APs) → E.

A and B at the EAP770 are the must-haves. Everything after them can be a second session.

---

## Before you leave the site

- [ ] Ctrl+C the server.
- [ ] Set `OMADA_RAW_DUMP_ENABLED=false` in `.env`. With the dump on, the log grows about 36 MB an hour.
- [ ] **Copy the capture file, every part, to a second location** — USB, cloud or email. Never the only copy on that laptop.
- [ ] Record its SHA256 and line count:

  ```powershell
  Get-FileHash .\logs\skye-<ts>.log -Algorithm SHA256
  (Get-Content .\logs\skye-<ts>.log).Count
  ```

- [ ] Photograph the notebook pages, the tape marks and each AP mount.
- [ ] Restart the dev server the usual way.

The hash matters because the replay has to run against provably the same file.

---

## Do not, during the session

- Change `TX_POWER_DEFAULT`, `PATH_LOSS_EXPONENT`, the radius, or any other setting, in code, `.env` or the database.
- Edit AP positions in Firestore, enable patrol, or change a route.
- Restart the backend unless forced. If forced, note the time.
- Delete anything.

Each of these breaks the comparison the session exists to make.
