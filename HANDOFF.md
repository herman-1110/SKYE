# SKYE Sentinel-AI — Handoff (v4, continuing from Prompt 128 + follow-ups `1ec17c6`, `e6a608c`; updated 2026-09-25)

Paste this into a new chat to resume. Project: FastAPI + Firebase (Firestore/RTDB/Storage) backend, Next.js/TypeScript frontend. Indoor BLE positioning → safety alerting (man-down, collision, patrol compliance) → real-time patrol tracking/reporting.

**This replaces v3**, which stopped at Prompt 126. **Check every claim here against the current code, git history and data before you rely on it.**
- v4 was fact-checked by six independent agents on 2026-09-24, and their corrections are applied. It was updated on 2026-09-25 with the user's decisions and the work that followed. It is still a snapshot.
- `HANDOFF.md` is untracked and was overwritten each time.
  - v3's text survives only in Claude transcript `171bfa4c-1400-44a1-8644-9260f3b117a6.jsonl`, plus a copy in that session's scratchpad (`…\scratchpad\handoff_check\completeness\v3_latest.md`), which is session-specific.
  - Two older versions, from 7 and 8 Sep (earlier than v2), survived in the Recycle Bin. They are now in `Project\skye-log-archive\` (see the next section).

## ⚠ The 10 Sep calibration capture — both runs' logs recovered (section rewritten 2026-09-30)

- **Nothing from 10 Sep is lost.** Both runs' source logs survive.
- **Run 2: `skye-calib-eap770-20260910-132241.log`, dump on.** It holds the raw `[OMADA]` payloads.
  - It was deleted from `backend/` to the **Recycle Bin** on 2026-09-22 at 15:19:41, outside any Claude session.
  - It was declared lost because earlier searches looked only under `C:\Users\Intern`. The bin is `C:\$Recycle.Bin\<SID>`.
  - It was recovered on 2026-09-30 to `C:\Users\Intern\Downloads\Omada\Project\skye-log-archive\`, next to the repo. SHA-256 `9f22722f82f101d6cba8dc24b7c1a6ff87ae0cc6244d6009758d6950660d7fb1`, verified against the bin copy, which is still in the bin.
  - 960,766 bytes, 5,996 lines, UTF-16LE, mtime 2026-09-10 13:23:54, launched as `python -u -m uvicorn … | Tee-Object`. All three APs, 62 reports each.
  - Its 23 `[MEASURE-119]` lines (13:22:55–13:23:53) give run 2's positions in the CSV exactly, in order. All are `guard-001`, on floor `abf7e4a2…` (Level 2). It holds the cp0 = 1.795 tick.
  - **The ≈−51 dBm EAP770 reading at 1 m can be re-derived from its dump.** Nobody has computed it yet; the fitted Prompt 127 will.
  - That reading was on EAP770 firmware 1.3.13. The AP is now on 1.4.3, so today's 1 m reference is a separate measurement.
  - **It stays out of git**, because the dump holds the ingest token (`meta.access_token`).
- **Run 1: `skye-capture-20260910-131300.log`, dump off.**
  - A `Tee-Object` UTF-16LE log covering 13:16:31–13:17:25, with three APs posting (`.100/.103/.105`). It has no RSSI.
  - Its 23 `[MEASURE-119]` lines give run 1's positions in the CSV exactly, in order. All are `guard-001` with `new_candidate=None`, on floor `abf7e4a2…` (Level 2).
  - It holds the cp0 = 1.983 and 1.902 ticks.
  - `.gitignore:63` (`backend/skye-capture-*.log`) hid it from `git status`, which is why earlier sessions missed it.
  - It was deleted to the Recycle Bin on 2026-09-30 at 09:41:51, along with the five other `backend/*.log` files.
  - It is committed as **`docs/evidence/skye-capture-20260910-131300.log` (`7ed3cdc`)**, byte-identical (SHA-256 `2058d6e4…`). It is also in the archive.
- **The precision table:**
  - The 46 solved positions are committed as **`docs/evidence/2026-09-10-stationary-positions.csv`** (`621e8cd`).
    - Run 1 is 13:16–13:17 and run 2 is 13:22–13:23, 23 positions each. The beacon was about 1 m from the EAP770, with TX −59 and n 2.5.
    - The header was updated in `7ed3cdc` and `951fd05`. Both runs are now `guard-001`, and each run's source log is named. For run 2 that means the archive path and SHA-256.
  - The positions reproduce the table exactly: centroids (combined N=46 is (21.505, 23.151)), sample standard deviations, and radial mean and max for run 1, run 2 and combined.
  - **The p95 values match only with the floor-index percentile** (numpy `method="lower"`). Linear interpolation gives 0.948 / 0.892 / 1.117 instead of 0.878 / 0.672 / 1.051.
- **Archive (`C:\Users\Intern\Downloads\Omada\Project\skye-log-archive\`):**
  - All 11 `skye*.log` files that were in the Recycle Bin: the 7 Sep measure logs, the three 9 Sep captures, both 10 Sep runs and both 22 Sep postupgrade logs.
  - The two binned `HANDOFF.md` versions from 7 and 8 Sep.
  - `MANIFEST.csv`: name, original path, deletion time, size, mtime and SHA-256 for each file.
  - These are copies; the bin items are untouched. Dump-on logs stay out of git.
- **The 7 and 8 Sep handoffs do not hold the v2 text** that Prompt 127's D3 and claim 10 quote.
  - They have no Kalman, Mystery Man or hysteresis thread, and they predate the 10 Sep capture.
  - The phrase "Kalman filter deadlock" survives in Claude transcripts `a2601a37…` (9 Sep), `baae6118…` (10 Sep), `fa1e315c…` (17 Sep), `171bfa4c…` (23 Sep) and `eb083435…` (25 Sep).
- **Floor frames differ.**
  - The 10 Sep lines are on Level 2 (`abf7e4a2…`): 1254×1254 px at 37.11 px/m, so 33.79 m square. It is now inactive with 0 APs.
  - Since 23 Sep the APs are on TPLink (`fc6e663e…`): 1024×1536 px at 34.33 px/m, so 29.83 × 44.74 m.
  - So the 1.8–3.3 m solve-to-AP distances and the bias relative to the EAP770 can't be recomputed from today's AP coordinates unless the two frames are shown to be one.
  - The fitted Prompt 127's D4 checks this. If they can't be shown to share a frame, the 10 Sep accuracy comparison is dropped.
- **10 Sep "inside the radius, no candidate":** three ticks read cp0 = 1.983 / 1.902 / 1.795 m with `new_candidate=None`.
  - The first two are in run 1's log and the third is in run 2's.
  - They were logged as unexplained because the radius was believed to be 2.0 m.
  - On 10 Sep the committed default of `PATROL_PROXIMITY_RADIUS_M` (`backend/config/settings.py:62`) was **1.0 m**. It was 5.0 from `79cd151` (4 Sep) and 1.0 from `cabcf63` (8 Sep 10:08), and was never 2.0 in any commit.
  - All three ticks were outside 1.0 m, so the tracker behaved correctly.
  - Whether an env override was set that day can't be checked, because `.env` isn't in git.

## Working methodology

Work is driven by numbered, user-authored "Prompt N" specs: **CONTEXT → DIAGNOSE (read-only recon) → TASK → VALIDATION**, with explicit STOP conditions.

- Real measured evidence over assumption. Never fabricate a measurement, a commit's contents, or a "yes it's live" without checking.
- If DIAGNOSE contradicts the prompt, or hits one of its STOP conditions, stop and report. Don't work around it. Example: Prompt 128's STOP 1 fired, the user was asked, and approved going ahead.
- Confirm or refute earlier claims explicitly, with file:line citations, and don't trust summaries from earlier sessions.
- Git hygiene:
  - Don't commit unless asked. Split commits cleanly by prompt.
  - **Run `git diff --cached --stat` immediately before every commit.**
  - Run `$env:GIT_PAGER = "cat"` before git commands in PowerShell.
- Don't clean up seeded test data, capture logs or instrumentation without asking.
- Always run `git log`/`git status` fresh before you report anything. **Other actors change this tree:**
  - the user;
  - an **OpenAI Codex agent running in the same VS Code** (`codex.exe` app-server, plus a `node_repl` computer-use process since 2026-09-23 11:37).

  Unexplained edits or reloads may come from either. Ask; don't assume.
- **Use commit hashes, not "HEAD".** HEAD has moved five times since Prompt 128 began (`3485013` → `d1c34e0` → `1ec17c6` → `e6a608c` → `670dcd5` → `621e8cd`), and "HEAD" in older notes means different things.
- **Changes to the live system:** the live backend runs `uvicorn --reload` with real AP traffic, so every saved `.py` under `backend/` restarts it straight away. That takes about 7–19 s and loses a few in-flight AP requests.
  - Build and test backend changes in a detached git worktree or a `git archive` export in the scratchpad, against the fake-Firebase test harness (see below).
  - Copy the finished files into the real tree only once, in an order that won't break the import chain on reload.
  - The **Next.js dev server is also live** (`next dev` on :3000, PID 7400, since 2026-09-23 09:00), so frontend saves hot-reload the dashboard the user is watching.

## Status by prompt

| Prompt | Topic | Status |
|---|---|---|
| 104–126 | (126 = `GET /health/tracker` + UTF-8 stdout; older detail only in the v3 transcript) | Committed |
| — | Read-only audit: "is there a buffer for null RSSI?" | **Answered: no** (see below) |
| 128 | Capture readiness: durable capture log, `[MEMBERSHIP-128]` line, `"rssi": null` crash fix, rate limit moved to config | **Committed `d1c34e0`, pushed** |
| 128 follow-up | Guard `_log_membership`'s fallback print (review found it could raise when stdout breaks) | **Committed `1ec17c6`, pushed**, live 2026-09-24 08:51 |
| 128 follow-up | Capture tee writes the file first and survives a dead console (see "Prompt 128" #6) | **Committed `e6a608c`, pushed**, live since 2026-09-25 12:12 |
| — | Test harness moved into the repo as `tools/harness/` | **Committed `670dcd5`, pushed** |
| — | `docs/evidence/2026-09-10-stationary-positions.csv` (the 46 positions behind the precision table) | **Committed `621e8cd`, pushed** |
| — | Capture tee: only `OSError` marks a console dead (decided 2026-09-25) | **Pending, not built.** Rides along with the next change that needs a reload. See Open #0. |
| 127 | Offline calibration replay (read-only) | **Stopped at its preconditions (2026-09-24):** the source-log and ground-truth fields were blank. See Open #6. |
| 129 | Null-RSSI grace period / last-good-RSSI hold | Not started. Deliberately left until real capture data exists to size it. |

**Branch state:**
- `claude/repo-review-r1fviz` @ `621e8cd` matches `origin` (pushed 2026-09-25).
- Against **`origin/main` it is 30 commits ahead and 1 behind.** The 1 is PR #1's merge commit `13e515c`, from 2026-08-12, which already merged this branch's first two commits (`c41ef76`, `bb6e911`). Nothing since has been merged.
- Local `main` (`3cdd6bb`) is stale, 3 behind `origin/main`, so counts against it come out higher.
- `origin/*` hasn't been fetched since 2026-08-12. A plain `git fetch` hung earlier, probably on a credential prompt. Fetch with `GIT_TERMINAL_PROMPT=0 GCM_INTERACTIVE=never` before any PR, merge or rebase work.
- `main` has none of Prompt 111's exact-hold, 119's null counter or anything since.

## Null-RSSI audit (asked before Prompt 128; verified by code, git, logs, simulation and adversarial checks)

- **There is no buffer or grace period for null RSSI, and there never has been, on any branch.**
  - Omada sends a null as `"rssi": {}`: all 2,029 of 2,029 nulls in the Sep 7–22 captures had that shape.
  - It is counted (Prompt 119 counter) and discarded at the `if rssi_avg is None: continue` in `omada_ingest_service._ingest_locked`.
  - Discarding it doesn't evict the AP's previous reading. That reading survives until it is older than `BUFFER_WINDOW_S = 2.0`.
- **APs report at ~1 Hz** (median 0.99–1.01 s per AP on Sep 7, Sep 22 and Sep 23), not the ~2 s old comments claimed. At that rate, on Sep 7 (a replay of the real decision chain that reproduces all 80 logged solves):
  - a single isolated null never removed the AP at a position decision (0 of 115);
  - runs of 2 nulls removed it **6 of 21** times;
  - runs of 3 or more almost always did (25 of 26);
  - about half of all null readings sit in runs of 2 or more.
- **What cushions the effect:** Prompt 111's 10 s hold of the last accurate position. Nothing is written and no safety checks run during the hold. After it, the position snaps to the strongest AP, or nothing is written if that AP is weaker than −90 dBm.
- **Sizing for Prompt 129 (a hypothetical grace for the last good reading):**
  - Replaying the real Sep 7 trace, 3-AP decisions go from **73% now to 95.5% with a 2 s grace and 98% with 4 s**.
  - A synthetic simulation with independent nulls at 20–31% per AP gives 73–91% now and 97–99.9% with a grace.
  - The cost in position lag was not measured.
- **Null rates per AP (34:5A / 34:5C / EAP770):**

  | Session | Null rates | Notes |
  |---|---|---|
  | Sep 9 | 19–50% | |
  | Sep 22 | 31.3% / absent / 25.7% | EAP770 on fw 1.4.3 |
  | Sep 23 16:46–17:03 | 18.2% / 22.1% / 14.7% | |
  | Sep 24 09:08–09:26 | 22.6% / 31.0% / 17.0% | |

  These sessions aren't controlled against each other.

## Prompt 128 — what `d1c34e0` + `1ec17c6` + `e6a608c` do

1. **Durable capture log** (`backend/utils/capture_log.py`, installed in `main.py` right after Prompt 126's UTF-8 reconfigure).
   - Tees stdout and stderr (print output including the `[OMADA]` dump, the root logger, and uvicorn's own handlers) into `backend/logs/skye-<UTC yyyymmdd-HHMMSS>.log`. The console is unchanged.
   - The file is UTF-8 with no BOM and CRLF line endings. Each line gets a UTC timestamp prefix and is flushed as it's written.
   - Rotation starts new part files (`skye-<ts>.part002.log` …) and never renames or deletes, because Windows can't rename a file another process has open.
   - If the file can't be opened it falls back to console only. `backend/logs/` is gitignored.
   - **Nothing ever prunes `backend/logs`.** One file per process start or reload; about 36 MB/h while the raw dump is on. It held 4 files on 2026-09-25.
   - The reloader parent's own lines ("WatchFiles detected changes…") are not captured.
   - Since `e6a608c` the file is written first and doesn't depend on the console (#6 below).
2. **`[MEMBERSHIP-128]`** in `_flush_ready_beacons`: one line per position decision after the rate limit. It carries:
   - `mono=` (the flush's own `time.monotonic()` freshness clock), `id=`, `person=`, `floor=`, `fresh=N/M`;
   - `outcome=solve|hold|fallback|not_written`, with `reason=no_solution|below_rssi_floor|error` when nothing was written;
   - `x/y` when a position was written;
   - `aps=[MAC/-61dBm/0.42s,MAC/absent,…]`, which lists every AP on the floor, no spaces.

   **What x/y mean:**
   - For `solve` they are the **Kalman-smoothed position, clamped to the floor bounds**, not the raw multilateration fix.
   - For `fallback` they are the anchor AP's own registered coordinate.
   - The log does not record AP coordinates, beacon `tx_power` or `PATH_LOSS_EXPONENT`.
   - **Before correcting AP `x_m`/`y_m` in Firestore after tape-measuring, write down the old values.** Otherwise earlier captures can no longer be replayed.

   It replaces the TEMP `[MEASURE-112]` line that `a703717` removed. STOP 1 fired on that, and the user approved building a new permanent line.
3. **`"rssi": null`** is now counted and discarded like `{}`: `entry.get("rssi") or {}` at both read sites. At `3485013` it raised `AttributeError` and returned HTTP 500, and the rest of that AP's report was lost.
4. **Rate limit:**
   - The stale "~every 2 s" comment is corrected to ~1 Hz.
   - `EMIT_MIN_INTERVAL_S` now reads env `POSITION_EMIT_MIN_INTERVAL_S` (default **1.8, unchanged**), documented in `backend/.env.example`.
   - It is not set in the real `.env`.
5. **`1ec17c6`:** `_log_membership`'s fallback warning `print` is now guarded, so the function really never raises.
   - At `d1c34e0`, unbuffered broken stdout made 10 of 30 ingests raise (each one a 500).
   - At `1ec17c6`, 0 of 30 do.
6. **`e6a608c`, the root fix for the capture tee.**
   - **Problem:** at `1ec17c6` the tee wrote to the console first. When the console failed (e.g. the pipe of a `python -u … 2>&1 | Tee-Object` launch closing), the exception fired before the capture. The file then silently stopped receiving lines, while ingest kept returning 200 (dump off) or returned 500 on every request (dump on).
   - **Fix:** every write now goes to the file first, then to the console, each in its own `try`. The first console failure on a stream writes **one** warning to the file (`[CAPTURE-128] WARNING: console stdout|stderr failed …`) and stops that stream's console writes, `flush()` included, for the rest of the process. The file keeps receiving everything. `1ec17c6`'s guard stays.
   - **Verification:** harness test with stdout and stderr on **one** pipe, broken mid-run (`2>&1`).
     - All four rows (unbuffered/buffered × dump off/on) returned **200 on every request after the break**. The two dump-on rows ran for 311 s, with 867 and 864 requests.
     - The file kept growing linearly (60 s samples) with `[MEMBERSHIP-128]`, access lines and `[OMADA]` when the dump was on.
     - One warning per stream, 0 tracebacks, graceful stop.
     - `1ec17c6` in the same test: the file stopped completely (request-log lines too), the dump-on row returned 500 on every request, and graceful stop hung.
     - With a working console, the tee A/B replay is byte-identical to `1ec17c6`: console 1,172 lines, capture 1,175 lines, positions identical.
   - **As committed**, following the instruction literally ("after the first console failure"), *any* exception from the console switches it off. That includes a `UnicodeEncodeError` from a lone surrogate in a payload string printed by the dump, even though the console still works. Real data has never contained one, and 4 of 4 review skeptics rejected it as a defect. **The user has since decided to narrow the rule. It is pending, not built: see Open #0.**

**Verification (fake-Firebase harness, nothing written to `skye-3fa05`):**
- Deterministic A/B, `3485013` against the new code, on a fake clock: 48 of 49 steps gave identical positions, scans, null counters, rate-limit state and console output (the new line aside). Only the `rssi: null` step differs.
- No alert fired in either A/B run. Alert logic was exercised only by a harness sweeper run: 1 `signal_loss` alert.
- `1ec17c6` replays byte-identically to `d1c34e0` when stdout works.
- The capture file survives a normal exit and a `taskkill /F` of the **real interpreter PID**.
- Two review rounds fixed a traceback flood on write failure, and rename-based rotation losing lines and deleting backups on Windows.

## Live observations

**Sep 23** (`backend/logs/skye-20260923-084630.log`, worker reloaded onto the Prompt 128 code at 16:46:29):
- **Traffic:** AP traffic until 17:02:50 local.
  - 2,647 access-logged ingests, all 200.
  - **At least 9 more got no response:** 8× `RuntimeError: No response returned.` plus one 5.1 s request at 16:59:16 whose AP had disconnected.
  - That error is raised in Starlette `BaseHTTPMiddleware.call_next` under `MaxBodySizeMiddleware.dispatch` (`main.py:110`), and passes up through `request_logger.py:16`. It means the client disconnected first.
  - 6 of the errors came at 16:46:40.7–41.6, within about 1 s of the new worker finishing startup (about 11–12 s after the reload began). **2 came at 16:50:45**, at the end of a ~6.2 s stall in which no request completed; a separate ~2.1 s stall just before it left 3 requests at 2.1–2.2 s.
- **Decisions:** 808 `solve`, 130 `hold`, 4 `fallback`. The median solve-to-solve interval was 2.015 s.
- **Alerts:** at 17:05:47 the sweeper raised **real signal-loss man-down alerts for `guard-001` and `worker-001`**. That is expected once the APs go quiet.
- **Latency:** median 322 ms, p90 1,297 ms, p99 2,296 ms, 433 requests over 1 s.

**Sep 24:**
- **Reloads:**
  - 08:51:33: my reload onto `1ec17c6`. APs weren't posting, so there were 0 errors.
  - **09:08:47: reload triggered by a save of `backend/encode.py` at 09:08:46, not by Claude.** Worker PID 33052 ran until the Sep 25 reload. There were 3 `No response returned` errors within 0.13 s of its startup, the usual burst when reloading under traffic.
- **Traffic:** real AP traffic 08:53–09:26:38 local on **new AP IPs `192.168.0.4/.5/.6`**. The current capture has 3,188 ingests, all 200.
- **Latency:** **median 162 ms, p90 346 ms, p99 897 ms, 24 over 1 s. That is the same code, but much better than Sep 23** (see Open #3).
- **Decisions:** 909 `solve`, 151 `hold`, 2 `fallback`.
- **Alerts:** at 09:28:54 the sweeper again raised signal-loss man-down alerts for `guard-001`/`worker-001` after the APs stopped.

**Sep 25:**
- 12:12:11: my single reload onto `e6a608c`, with `OMADA_RAW_DUMP_ENABLED=false` set in `.env` just before it.
  - The old worker (33052) shut down gracefully.
  - Worker **26740** finished startup at 12:12:48 (33 s; Firebase init was slow) with 0 errors.
  - Capture file `backend/logs/skye-20260925-041215.log`.
- **The APs have not posted since 2026-09-24 09:26:38**, so neither the new tee nor the dump-off setting has been seen on real traffic yet. On the first AP reports, check that the new capture has `[MEMBERSHIP-128]` lines and **no `[OMADA] AP REPORT` lines**.

## Unresolved / open threads — ask the user, don't assume

0. **PENDING, decided, not built: narrow the capture tee's console-death rule** (user decision, 2026-09-25).
   - **Rule:** in `backend/utils/capture_log.py` `_Tee`, **only an `OSError` marks a stream's console dead.** Any other exception from a console write or flush **skips that line on the console only, and warns once**. The console stays in use for later lines, and the line still goes to the file, which is written first.
   - Today (`e6a608c`) any exception marks the console dead (see "Prompt 128" #6).
   - **Don't build it on its own.** Build it together with the next change that needs a live reload, so the server doesn't take an extra reload.
   - Follow the usual path: a scratch export, the `tools/harness` broken-pipe matrix plus the tee A/B, then one copy into the live tree.
   - **Two consequences to test:**
     - `UnicodeEncodeError` (a lone surrogate from the dump) is a `ValueError`, so it becomes skip-and-warn, which is the point of the change.
     - `ValueError("I/O operation on closed file")` is not an `OSError` either. A closed console would then be skipped line by line, after one warning, instead of being marked dead. The file is unaffected either way.
   - "Warns once": one warning per stream for non-OSError skips, in the file, separate from the one console-dead warning.

1. **Resolved by `e6a608c` (2026-09-25): the capture silently lost stdout lines when stdout was unbuffered and broken.** Details and the validation matrix are under "Prompt 128" #6.
   - Before the fix, with only stdout broken, `1ec17c6` returned 90/90 × 200 with the dump off yet added 0 `[MEMBERSHIP-128]`, dump or access lines. The capture looked alive while its data had stopped.
   - With `2>&1` broken it was worse: the file stopped completely.
   - A field session may now be launched either way. Tee-Object is still unnecessary.
2. **Firestore `settings/safety.man_down_minutes = 60` overrides `.env` `MAN_DOWN_MINUTES=5`.**
   - `safety_service._get_settings` prefers the Firestore doc (lines 73–88, used at :169). So stillness man-down currently needs 60 minutes; the doc was last updated 2026-09-09T02:17:33Z.
   - **The user owns this value (2026-09-25): don't change it, and don't re-raise it.** Prompt 127's D1 notes that a movement test set it to 1 at one point.
3. **Live ingest latency on Sep 23 was much worse than any other capture.**
   - Sep 23 had a median of 322 ms and p99 of 2.3 s. Sep 24, **on the same code**, had 162 ms / 897 ms. Sep 22 had 132 ms / 349 ms.
   - The Prompt 128 code adds only about 3–5 ms per request on the harness. So the Sep 23 cause is something else and still unknown.
   - Ingest is **serialized**: every `/telemetry/omada` POST holds `positioning_service.pipeline_lock` for the whole call, including Firebase round-trips and safety checks. Sep 23 lock utilisation was about 73%, with 57% of requests queued; Sep 10 (3 APs) queued 64%.
   - **Lowering `POSITION_EMIT_MIN_INTERVAL_S` adds solve work under that lock.** Watch latency and `No response returned` errors if you do.
   - The Sep 23 backend console was a **VS Code integrated terminal**, not a standalone console. The raw dump is about 30 lines (~3.5 KB) per POST.
4. **Resolved (2026-09-25): `OMADA_RAW_DUMP_ENABLED=false` in the local `backend/.env`**, by the user's decision. It goes on **only for captures**.
   - It took effect with the 12:12 reload (#5 explains why a reload is needed).
   - Not yet observed on real traffic (see "Sep 25").
   - When it is on, it is the main source of console and log volume, and it writes each payload's `meta.access_token` into the capture file.
5. **`.env` changes don't reach the live server by themselves.**
   - `--reload` watches only `*.py`, and `settings` is read once, when it is imported.
   - So a change to `OMADA_RAW_DUMP_ENABLED` or `POSITION_EMIT_MIN_INTERVAL_S` needs a `.py` save or a restart, which costs about 10 s of AP requests and starts a new capture file.
   - A variable set in the terminal's own environment overrides `.env` without warning.
6. **Prompt 129 and the field session.** Checklist, from Prompt 128:
   - (a) All 3 APs reporting: **yes on Sep 23 and 24.** Note the new IPs, and re-check on the day.
   - (b) Tape-measure all three APs; record the old `x_m`/`y_m` before correcting anything.
   - (c) Record the beacon's ground-truth position, with the times it was placed and moved.
   - (d) Set `POSITION_EMIT_MIN_INTERVAL_S` lower for the capture, then set it back. This needs a reload (#5) and adds load (#3).
   - (e) Turn `OMADA_RAW_DUMP_ENABLED` on for the capture (the 1 m RSSI re-measurement needs the per-AP `rssi.avg` from the dump), and off afterwards. Each change needs a reload (#5).
   - **Prompt 127** (offline calibration replay) needs a named source log with reports from all three APs, and a recorded ground truth (beacon, position, placed/moved times). Both fields were blank when it was issued, so it stopped at its preconditions.
     - Its claim 8 input now exists (`621e8cd`).
     - Its D3 ("HANDOFF.md, untracked v2", Kalman thread verbatim) and claim 10 ("`HANDOFF.md:37` cites the Sep 10 log") refer to v2/v3 text that is no longer in this file. That text is in the v3 transcript.
7. **Prompt 126's `GET /health/tracker` has no frontend consumer.** Offered in v3, not approved. Building it touches the live Next.js dev server.
8. **Kalman filter lock-up** (`kalman_service.py`):
   - A solve more than 8 m from the estimate is rejected (lines 69 and 97).
   - Rejected solves still refresh `_last_seen`. So the filter only resets after **more than 10 s with no ≥3-AP solve** for that beacon (`positioning_service.py:24`, `:225`), or on a process restart.
   - `invalidate_scale_cache()` clears `_last_seen` but not `_filters`, so floor or zone edits never reset a stuck filter.
   - Proposed fix: force a reset after about 3 rejections in a row. Never decided.
9. **Unchanged from v3:**
   - **"Mystery Man" beacon:** UUID `7E66DA30-0A96-4DB5-A15B-066CE9032E70`, `person_id: "pika"`, still unidentified.
   - Whether 117's hysteresis is live is still inconclusive.
   - An untracked Firestore composite index was never reconciled.
   - `eac8b38`'s beacon-delete RTDB cleanup doesn't handle simulated beacons.
   - **RTDB `/alerts`, v3's audit:** 57 nodes. 13 have cause `no_patrol`/`short_dwell` on 2026-09-09: 9 real `guard-001`, 4 synthetic `test-123-guard-e/e2/g`. All unresolved. Since then, real `signal_loss` alerts were added on Sep 23 17:05 and Sep 24 09:28; these were not re-verified in RTDB.
10. **Untracked files, not created by Claude:**
    - **`backend/encode.py`:** a TP-Link IP-camera SHA-256 digest-auth hash script.
      - Created 2026-09-23 13:20, then saved again at 15:48:12 and on 2026-09-24 at 09:08:46. **Each save reloaded the live server.**
      - It **contains a hard-coded plaintext camera password. Do not commit it.**
      - **The user owns this file (2026-09-25): don't touch it.**
    - **`backend/skye-calib-eap770-postupgrade-20260922-135717.log`:** launched with `python -u … | Tee-Object`.
      - AP traffic only covers 14:20:07–14:23:35.
      - Per AP: **EAP770 `A8:29:48:C3:88:A0` sent 206 reports; EAP660 `40:AE:30:9D:34:5A` sent 204; `40:AE:30:9D:34:5C` sent 0.**
      - **"postupgrade" is confirmed** (user, 2026-09-25): v23 named this file for the **post-upgrade 1 m re-measurement**, after the EAP770 went from firmware 1.3.13 to 1.4.3.
      - With `34:5C` silent, every position in it is a fallback. So it can't serve as the 3-AP replay source for Prompt 127 (its STOP 6).
    - `HANDOFF.md` itself is untracked.
11. **Stale or wrong documentation:**
    - **`kalman_service.py:13-16`** cites a "~2 s telemetry cadence" for the time between Kalman updates. It was written in `d9b1c2f` on the same wrong belief that APs report every ~2 s. As an update interval it holds only by coincidence: the 1.8 s rate limit on ~1 Hz reports gives a measured median of 2.015 s (p90 about 3.9 s). It's wrong for the ~1 s simulation path and will be wrong if the rate limit is changed. Documentation only.
    - **`SYSTEM_OVERVIEW.md`** says fewer than 3 APs goes straight to proximity at lines 70, 133, 196 (§3.7), 306 and 418, and never mentions the 10 s hold. §4.2 (line 246) still calls `patrol_tracker_service` a future component.
    - **`README.md:114`** documents `MAN_DOWN_MOVEMENT_THRESHOLD`, which doesn't exist. The real setting is `MAN_DOWN_MOVEMENT_EPSILON_M`, default 2.0.
    - **`.env.example:60`**: the comment for `COLLISION_DISTANCE_M` describes man-down movement.
    - `TEMP-MEASURE-119` prints are still live in `patrol_tracker_service.py`.
    - `patrol_tracker_service.py:14-17` refers to 3 APs on "Level 2". The active floor is now "TPLink" (3 APs); "Level 2" is inactive with 0 APs.
12. **Radius settings (answered read-only on 2026-09-24):**
    - The "Radius 1.0" in Prompt 128's V1 table is almost certainly **`PATROL_PROXIMITY_RADIUS_M`** (`settings.py:62`, default 1.0 m; about 85–90% confidence).
    - It is overridable only by env, which is not set. The per-floor Firestore field `patrol_proximity_radius_m` is absent on both floors and **ignored anyway**: `patrol_tracker_service.py:166,176` reads `settings` directly.
    - **Latent bug:** a floor created from now on would store `patrol_proximity_radius_m = 0.0` (`floor_repository.save`). It has no visible effect today, only because the frontend prop it would feed is unused.
    - Other radius-like settings: `PATROL_PROXIMITY_EXIT_MARGIN_M` 0.5, `MAN_DOWN_MOVEMENT_EPSILON_M` 2.0, simulation `WANDER_RADIUS_M` 1.0 (×3), Kalman outlier gate 8.0 m, and the proximity `radius_m` computed from RSSI (at most ~17.4 m).
    - Patrol isn't running on real data right now: both floors have `patrol_enabled=false` and an empty route.
13. **Minor:**
    - A gitignored stray `backend/__pycache__/analyze_measure_112.cpython-312.pyc` is left from harness analysis.
    - A review hardening idea, rejected as not a real defect here: the tee's lock ordering could deadlock if a garbage-collector finalizer logs through root. The app never produces such a finalizer.

## Test harness — `tools/harness/` (`670dcd5`)

**`tools/harness/README.md` has the commands.** In short:
- **What it is:** an isolated uvicorn running `main:app` against in-memory RTDB/Firestore fakes with a network tripwire, so it never touches `skye-3fa05`. It refuses port 8000.
- **Contents:**
  - the smoke run;
  - the deterministic A/B replay (`ab_run`/`ab_compare`), plus the tee A/B via `AB_CAPTURE_DIR`;
  - the broken-pipe matrix (`broken_pipe_capture.py`, stdout and stderr on one pipe);
  - the kill test and a console-vs-capture coverage check.
- **`--backend-dir` is required with no default.** Point it at a `git archive <commit> backend | tar -x -C <dir>` export, **never at the live `backend/`**. Otherwise the test server's capture file lands in the real `backend/logs`, looking like a real capture.
- Paths are repo-relative. Run dirs go to `tools/harness/runs/`, which is gitignored. Run it with `python -B`.

## Environment quirks

- **Shells and tools:**
  - Windows: PowerShell is primary; the Bash tool is Git Bash. Don't mix path styles.
  - Use the venv directly (`backend\venv\Scripts\python.exe`), run from `backend` (the relative `./serviceAccountKey.json` needs the right cwd).
- **Live backend process chain:**
  1. PowerShell (a VS Code integrated terminal)
  2. `venv\Scripts\uvicorn.exe` (PID 11064, `main:app --reload --host 0.0.0.0 --port 8000`, since 2026-09-23 09:00:51)
  3. venv `python.exe` **uv trampoline** (26608)
  4. uv cpython 3.12 reloader (21452, owns :8000)
  5. `multiprocessing.spawn` worker (26740 since 2026-09-25 12:12:11, on `e6a608c`)
- **The venv `python.exe` is a shim.** `Popen(...).pid` is the shim; kill the PID a process reports itself.
- **dotenv:** `load_dotenv()` with no arguments finds nothing when the script lives outside the project, e.g. in a worktree, an export or the scratchpad. Pass `dotenv_path=r"...\backend\.env"`.
- **Log encodings:**
  - Logs piped through PowerShell (`>`, `Tee-Object`) are UTF-16LE with a BOM, and their box-drawing characters are garbled (`ΓòÉ`).
  - **`backend/logs/` captures are UTF-8 without a BOM.**
  - Detect the BOM before decoding. Trying `utf-16` first can "succeed" on UTF-8 bytes and return garbage.
  - Never print decoded non-ASCII to the console (cp1252). Write to a UTF-8 file and read that.
  - Read the live capture quickly and close it. Don't hold it open.
- **Git and Firebase:**
  - Push works with `GIT_TERMINAL_PROMPT=0 GCM_INTERACTIVE=never git push origin claude/repo-review-r1fviz`.
  - Firebase CLI is authenticated, project `skye-3fa05`. Deploys need an explicit go-ahead.
  - Firestore composite indexes are direction-specific.
- **No test suite** in the repo. Validation is ad hoc (in-process scripts, the fake-Firebase harness, real capture logs), which is established practice.
- **Identities:**
  - Real hardware: `guard-001`, `worker-001` (`reporter_mac == person_id`). Beacon docs also include `random-001`.
  - Synthetic: `sim-*`, `test-*`. The `test-128-*` ones exist only in the in-memory harness, never in real Firebase.
- **Real APs:** `40:AE:30:9D:34:5A` and `40:AE:30:9D:34:5C` (EAP660 HD), `A8:29:48:C3:88:A0` (EAP770). On 2026-09-24 they posted from `192.168.0.4/.5/.6`; earlier they were `.102/.103/.104`, among others.
- **Floors:** "TPLink" `fc6e663e…` is the active floor, with 3 APs. "Level 2" `abf7e4a2…` is inactive, with 0 APs. Both are in building `53c3872f…`.

## Suggested first message in the new chat

"Continue from HANDOFF.md v4. First: (1) when the APs next post, confirm that the live capture has `[MEMBERSHIP-128]` lines and no `[OMADA] AP REPORT` lines (dump off since 2026-09-25). (2) for Prompt 127: which source log, and what ground truth (beacon, position, placed/moved times)? Remember Open #0: build the pending OSError-only console rule together with the next change that needs a reload. Leave `man_down_minutes` and `backend/encode.py` alone; they're the user's. Then plan the field session and Prompt 129."
