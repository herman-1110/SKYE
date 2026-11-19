# SKYE Sentinel-AI — Handoff (v11, after the combined live checks and the merge into `main`; updated 2026-11-19)

Paste this into a new chat to resume. Project: FastAPI + Firebase (Firestore/RTDB/Storage) backend, Next.js/TypeScript frontend. Indoor BLE positioning → safety alerting (man-down, collision, patrol compliance) → real-time patrol tracking and reporting. Plus a VIGI camera integration: alarm events, health, discovery and live video. **Next up:** Prompt 147, the fix for the stillness clock that single noisy positions keep restarting (Open #31): a move will count only after three fixes in a row. It decides whether the red man-down works at long timers. Then Prompt 148, the dashboard and editor fixes: remembering the chosen floor (Open #34) and the calibration rounding (Open #35). After those come the backup floor's clean-up (Open #32) and Open #33 and #36, in the order Herman picks, then 133 (Ghost Patrol).

**This replaces v10** (18 Nov), which is in git history: `git show a6ee040:HANDOFF.md`. v9 is `git show a1121ea:HANDOFF.md`, v8 is `git show 5bb495f:HANDOFF.md`, v7 `git show 2975863:HANDOFF.md`, v6 `git show 2f00309:HANDOFF.md` and v5 `git show 56882ff:HANDOFF.md`. **v8 to v11 were written on a different PC from v7** (see "This PC" under "Environment quirks"); the parts marked "Intern laptop" describe the old machine. **Since v10 this file holds no device addresses, MACs, key IDs, device UUIDs, the project ID or real floor and building names** (Herman, 18 Nov): read them live, from the Firestore records, the heartbeats and `ipconfig`. **Check every claim here against the current code, git history and data before relying on it.**

## Where things stand (19 Nov)

- **`main` now holds all the work.** Herman merged it on 19 Nov with fast-forward pushes, which took GitHub's `main` to `a6ee040`, 40 commits ahead of the old `2975863` with no merge commits. So 136, 142, 145 and 143 are all on it. At about 04:09 Herman reset the local `main` to `origin/main`, and the live tree is on it. The code didn't change in that switch, so the running backend wasn't affected.
- **The hardware is live every day** (Herman, 18 Nov), so the "dock day" of earlier versions no longer applies.
- **The combined live checks ran on 19 Nov, from about 00:00 to 03:17.** Herman ran them and wrote the results in `D:\DOWNLOAD\Y3S2\FYP\skye-scratch\live-checks\combined.md`, which stays out of the repo because it names devices and floors. Claude checked the results against the backend logs and Firebase.
  - **136's V6 passed.** L1: with the Omada IoT Transport Stream off from 01:23:55 to 01:33:02, one POSITIONING OFFLINE came at 01:25:02, both beacons' "holding the signal-loss alert" lines at 01:26:03, and no false man-down. L2: with two APs off, an amber at the third AP's spot, then a red 37 s after the last AP returned. L3.1: a signal-loss red 2 min 51 s after the beacon went off. L3.2: the real worker's two collisions with the simulated forklift came while its beacon was really on. None named it after the beacon went off, while the simulated pair kept colliding.
  - **142's V5 passed.** L1, L3, L5 and L6 passed on 19 Nov, and L2 apart from L2.2. L2.2 and L4.1 passed on an earlier run of Herman's; the 19 Nov logs don't show them. L3.2 showed that zones don't keep their shape (Open #33), and L5.2 that the dashboard forgets the chosen floor (Open #34).
  - **143's L6:** L6.1 to L6.3 passed, and the backup floor's three placements from the online list were named by their IPs. L6.4 (optional) didn't run. The third AP had already been placed by hand at 00:02, so L6.5's name check was done on the backup floor and cancelled. Herman chose not to wait for L6.6's 60-minute reds, and none came (Open #31).
  - **The red man-down's restart test passed** (Open #1).
  - **At the end (04:23):** Safety Settings back at 60, no test firewall rule, three APs, the camera and both beacons live, one active floor, and the night's last 8 test alerts resolved (04:17–04:18). 42 older alerts, from 6 Oct to 18 Nov, stay unresolved.
- **The Intern laptop is gone** (Herman, 19 Oct). Work continues on a second clone at `D:\DOWNLOAD\Y3S2\FYP\SKYE` (Windows user `User`). How it differs is under "This PC" in "Environment quirks".
- **The Prompt 134 review is lost.** It lived only on the Intern laptop's local branch `review/134` and was never pushed. What survives: the fix plan below, the non-security findings this handoff describes, and the IDs of fixed findings in commit messages. The unfixed `SEC-xx` findings are gone, so Prompt 137 needs a fresh security pass, kept out of the public repo.
- **Prompt 136 (man-down and collision correctness) is on `main`.** 7 commits (`73f131a`..`3ab8adc`): COR-02, COR-04, COR-03, CON-03, REL-01, COR-06 and the frontend's amber alerts. V1–V5 passed on 20 Oct, and **V6, the live check, passed on 19 Nov.** Report: `D:\DOWNLOAD\Y3S2\FYP\skye-scratch\136\report.md`.
- **Prompt 142 (floors and APs) is on `main`:** 8 commits (`4bcf64c`..`e9d824a`). Several active floors, AP status colours, calibration memory, AP removal, and a dashboard-map fix (`e9d824a`, confirmed live on 3 Nov: markers on 14 of 14 loads). **V5, the live check, passed on 19 Nov,** with L2.2 and L4.1 from an earlier run of Herman's. Report: `D:\DOWNLOAD\Y3S2\FYP\skye-scratch\142\report.md`, with `live-check-findings.md` next to it.
- **Prompt 145 (alerts that stay dismissed) is on `main`:** 5 commits (`d070aa7`..`1c5f206`), then the v9 commit (`a1121ea`). An admin's ✕ or Dismiss all closes a critical pop-up for everyone, and a restarted backend doesn't repeat a stillness alert for someone who hasn't moved. **V5, the live check, passed on 17 Nov** (L1 and L2; Herman skipped L3). See "Prompt 145" below. Report: `D:\DOWNLOAD\Y3S2\FYP\skye-scratch\145\report.md`.
- **Prompt 143 (the Floor Plans tab) is on `main`:** 13 commits (`57ba273`..`102e60e`), then the v10 commit (`ffd6a7d`). Placement guides measured from the room's walls, which way each camera faces, a red Deactivate, devices named by their IP, and Safety Settings that won't save numbers it didn't load (Open #29). **V5, the live check, passed on 17–18 Nov, and L6 (names from the IP) on 19 Nov,** apart from its optional L6.4. See "Prompt 143" below. Report: `D:\DOWNLOAD\Y3S2\FYP\skye-scratch\143\report.md`.
- **13–14 Nov, the stuck AUTHENTICATING screen.** On 13 Nov a freshly compiled `/dashboard` sat on AUTHENTICATING. React's first commit came 120 s late (high confidence); the likely cause is that `next dev` rewrote `app/layout.js` while the browser was downloading it, so webpack waited out its 120 s chunk timeout (inferred). The fix is **`5f70fb7`**, committed by Herman on `fix/142-floors-aps` (message "stuck AUTHENTICATING screen"): a one-time reload at 20 s, a "taking longer than it should" hint, and an error screen with Retry when the account check fails. See Open #24.
- **Pushed on 14 Nov:** Herman pushed `fix/142-floors-aps` (`5f70fb7`) to GitHub. It contains 136's commits, so all 16 are public; the `.env` scan of the range found none of the real values.
- **Pushed on 17 Nov,** at Herman's word: `fix/145-alerts-stay-dismissed` with `-u`, then the v9 commit. It carries 142's `9f28798`, so that commit is public too, and GitHub's `fix/142-floors-aps` has since moved to it. The `.env` scan of the range found none of the real values.
- **Pushed on 18 Nov,** at Herman's word: `fix/143-floor-plans-tab` with `-u` (`102e60e`), then the v10 commit. The `.env` scans of the range found none of the real values, and no commit in it adds a real floor or building name.
- **The camera status colours are committed** as `9f28798` (16 Nov, at Herman's word), the newest commit on `fix/142-floors-aps`, in 7 frontend files (`DeviceStatusPanel.tsx`, `APCCTVEditor.tsx`, `ApIcon.tsx`, `CameraPanel.tsx`, `CctvIcon.tsx`, `FloorMap.tsx` and `useCCTVHeartbeats.ts`). Camera icons go green, red or grey like the APs. Green means port 554 answers at the registered IP; the login state stays in the panel's Health check row.
- **The camera on this PC** isn't the one measured on 5 Oct (see "Hardware and network"). Live view works since go2rtc and ffmpeg were installed on 14 Nov. It runs firmware 3.4.0 Build 260910 (Herman, 18 Nov). Its alarms and OpenAPI now work: on 19 Nov, 107 alarm requests between 00:04 and 02:03 all answered 200, and its health check logs in (Open #22, #23).
- **The floor set-up changed on 13–14 Nov and again on 19 Nov** (backend logs). At 19:44 on 13 Nov the old floor's three APs and its camera were removed through the dashboard, and that floor was deactivated. Since 00:30 on 14 Nov the active floor is another floor of the same building. **Since 00:02 on 19 Nov all three APs are placed on it** (two EAP660 HD and the EAP770), with the camera, so a beacon heard by all three gets exact fixes. The simulators need an active floor with at least three APs placed.
- **Last full check at 04:23 on 19 Nov:** the backend on :8000 (this process since 03:04) was taking AP posts, and all three APs, the camera and both beacons were live. `next dev` (:3000) and go2rtc (:1984) served the dashboard and live video that night. **The PC is on Wi-Fi only, with Ethernet unplugged. That link runs through the third AP and also carries Firebase.** So don't power that AP off in a test. To stop every AP's reports, use the IoT Transport Stream switch in the Omada controller. The camera's Alarm Server target, the APs' push URL and go2rtc's WebRTC address all name this PC's address, so check the address before anything else.
- **The 134 fix plan, in order** (the review's own titles):
  1. 135: credentials and quick safety stops (**done**, on `main`).
  2. 136: man-down and collision correctness (**done**, on `main`; live check passed 19 Nov).
  3. 133: Ghost Patrol, plus its prerequisites.
  4. 137: Firebase rules and account controls (FE-02 moved to 145).
  5. 138: reports and the simulator.
  6. 139: positioning robustness and observability (with 127 and 129).
  7. 140: reliability and housekeeping.
  8. 141: documentation pass.

  142 (floors and APs, from Herman's 20 Oct list) came after 136 and is stacked on it. 145 (alerts that stay dismissed) is stacked on 142, and 143 (the Floor Plans tab) on 145. All four are on `main` now.

  **Next: Prompt 147,** the fix for the stillness-timer bug (Open #31): a move counts only after three fixes in a row. **Then Prompt 148,** the dashboard and editor fixes, which cover remembering the chosen floor (Open #34) and the calibration rounding (Open #35). Herman set this order on 19 Nov.

## Git

- **Branches:**
  - `main` = `origin/main` = the v11 commit, on top of **`a6ee040`** (19 Nov), which is 40 commits ahead of `2975863` (16 Oct, the v7 docs commit) with no merge commits. Herman fast-forwarded `main` to `a6ee040` with pushes on 19 Nov and reset the local `main` to `origin/main` at about 04:09. The live tree is on `main`.
  - `fix/136-man-down-collision` (`3ab8adc`): local only, fully contained in `main`. Its upstream is `origin/main`, so git reports it as behind.
  - `fix/142-floors-aps` (`9f28798`), `fix/145-alerts-stay-dismissed` (`a1121ea`) and `fix/143-floor-plans-tab` (`a6ee040`): each level with its GitHub branch and contained in `main`.
  - **The merges are done.** Treat the merge steps at the end of 136's, 142's, 145's and 143's reports as history. New work starts from `main`.
  - Gone: `review/134` (with the Intern laptop) and `fix/135-credentials-safety-stops` (locally and on GitHub). Someone deleted `claude/repo-review-r1fviz` on GitHub on 7 Oct, after its merge (`ef1a1d3`); all its commits are on `main`. This clone's `origin/claude/repo-review-r1fviz` (from a 22 Sep fetch) is the last ref with that name: **keep it** (Herman, 18 Nov). Never run `git fetch --prune` or `git remote prune origin`; a plain fetch keeps it.
- **Fetching and pushing:** use `GIT_TERMINAL_PROMPT=0 GCM_INTERACTIVE=never git fetch|push origin …`. A plain fetch can hang on a credential prompt.
- **Commits since v7** (all on `main` since 19 Nov):

  | Commit | What |
  |---|---|
  | `73f131a` | **136**, COR-02: the Kalman filter can no longer lock onto an old position |
  | `ce2e719` | **136**, COR-04: collisions only between fresh records on the same floor |
  | `ef8ffcb` | **136**, COR-03: an amber `possible_man_down` for stillness seen by only one or two APs |
  | `bcff733` | **136**, CON-03: the signal-loss sweep decides under `pipeline_lock` |
  | `d64c72d` | **136**, REL-01: an AP outage no longer raises signal-loss man-downs for everyone |
  | `a971584` | **136**, COR-06: a restart doesn't repeat an alert already raised for the same episode |
  | `3ab8adc` | **136**, frontend: amber alerts for `possible_man_down` and `positioning_offline` |
  | `4bcf64c` | **142** D1: several floors can be active at once, each AP on only one of them |
  | `1672cdb` | **142**, frontend: several active floors on the dashboard and the Floor Plans tab |
  | `337ea17` | **142**, frontend: AP icons coloured by status |
  | `2cd4b54` | **142** D3: a calibration's points are kept, and zones stay where they're drawn |
  | `b0ff930` | **142**, frontend: Recalibrate starts from the last calibration |
  | `258a47f` | **142** D4: removing an AP doesn't answer 500 once the AP is gone |
  | `0f64f00` | **142**, frontend: a failed remove checks whether the item is gone |
  | `e9d824a` | **142**, frontend: the dashboard map measures itself once a floor arrives |
  | `5f70fb7` (Herman, 14 Nov, "stuck AUTHENTICATING screen") | Frontend: a stuck AUTHENTICATING screen reloads once, then says why (7 files, including the new `frontend/utils/authCheck.ts`) |
  | `5bb495f` (Herman, 14 Nov, "Handoff file") | HANDOFF v8 |
  | `9f28798` (16 Nov) | **142**, frontend: camera icons coloured by status, like the APs |
  | `d070aa7` | **145** D1: an admin can acknowledge an alert, closing its pop-up for everyone |
  | `80f5703` | **145** D3: a restart doesn't repeat a stillness alert for someone who hasn't moved |
  | `794261a` | **145**, frontend: critical pop-ups stay dismissed once an admin closes them |
  | `a886862` | **145** D3: a change of strongest AP counts only once it has held 30 s, and the restart check looks back 12 hours |
  | `1c5f206` | **145** D3: the AP-change hold defaults to 120 s, and a third AP no longer restarts it |
  | `a1121ea` | HANDOFF v9 |
  | `57ba273` | **143** D2: cameras store which way they face, `facing_deg` and `fov_deg` |
  | `e862380` | **143** D4: an AP's heartbeat carries its IP |
  | `a7243ad` | **143**, frontend D1: placement guides in Manage Devices |
  | `90fba67` | **143**, frontend D2: each camera shows which way it faces |
  | `e0b16fd` | **143**, frontend D3: Deactivate is red |
  | `941b6d8` | **143**, frontend D4: a device placed from the online list is named by its IP |
  | `97863ba` | **143**, frontend D5: Safety Settings never saves numbers it didn't load |
  | `915f170` | **143**, frontend: Add AP and Add CCTV start from an empty form |
  | `a8486e8` | **143**, frontend: the walls' room shows its size in metres (superseded by `4380058`) |
  | `d1da85c` | **143**, frontend: a dragged device's name and status are hidden |
  | `e0d5fec` | **143**, frontend: a default cone for a camera with no facing |
  | `4380058` | **143**, frontend: the room's outline can have any number of corners |
  | `102e60e` | **143**, frontend: the default camera cone is clearly visible |
  | `ffd6a7d` | HANDOFF v10 |
  | `f12b968` | `SYSTEM_OVERVIEW.md` brought up to date with the code |
  | `a6ee040` | HANDOFF.md names floors and APs in plain words |
  | the v11 commit | HANDOFF v11 (this file), committed straight onto `main` at Herman's word, as the v7 docs were |

## Prompt 143: the Floor Plans tab (17–18 Nov)

- **What it does** (in Manage Devices, unless it says otherwise):
  - **D1, placement guides:** **Walls** draws the room's outline and picks two of its walls. While an AP or camera is placed or dragged, two guides show its distances to them ("X … m", "Y … m"), and the place dialog takes typed X and Y. The walls are kept per floor in the browser (`localStorage`, `skye-wall-guides:<floorId>`), not in Firestore.
  - **D2, camera direction:** cameras store `facing_deg` (0 to under 360, clockwise from the top of the plan) and `fov_deg` (10–360; 90 when a facing is saved without one), both null until set. Both maps draw a cone under each camera with a facing; its handle in Manage Devices turns it.
  - **D3:** Deactivate is red, like Delete Floor.
  - **D4:** the Omada ingest writes each AP's IPv4 into its `/ap_heartbeats` node as `ip`, and a device placed from the "online but not placed" list is named by its IP.
  - **D5:** Safety Settings stays empty and can't save until the real values load, with Retry (Open #29).
  - **Follow-ups:** Add AP and Add CCTV start from an empty form; a dragged device's name and status are hidden while the button is held, and Esc cancels the drag.
- **Herman's decisions (18 Nov), amending 143's DECISIONS:**
  - **The walls (D1):** the room is an outline with any number of corners, drawn the way a zone is drawn: a click per corner, a right-click to close, Esc to clear the corners. For the walls only, Shift makes the wall being drawn level or upright. Every wall shows its length. Zones and walls share the drawing code (`PolygonDraft.tsx`).
    - X and Y are measured square to two of its walls more than 30° from parallel (a Y wall within 30° of parallel to the X wall is refused), to a wall's line extended when needed, drawn faint.
    - Typed X and Y land on the clicked point's side of each wall. A rectangle gives exactly the earlier results.
    - Walls saved in the earlier rectangle format read as none, to be drawn again.
  - **The default cone (D2.1):** a camera with no facing gets a dashed cone towards the map's middle, in Manage Devices only. It's saved only when its handle is released (a plain click counts) or Facing is saved in Edit camera. The dashboard draws no cone for it (`FloorMap.tsx`), and the panel says "Not set".
  - **Dragging:** the whole tooltip is hidden during any drag, with or without walls.
- **Tests:** `f143_camera_direction_inprocess.py` 14/14, `f143_ap_heartbeat_ip_inprocess.py` 9/9, and the Node check `f143_wall_guides_check.ts` 22 passed (see the harness table).
- **The live check (V5):** L0–L5 and L7 passed on 17–18 Nov, and the rewritten L0–L4 again after the outline and cone commits, with a zone drawn as before. **L6 (names from the IP) ran on 19 Nov** (see "Where things stand"). Herman removed the test camera afterwards.

## Prompt 145: alerts that stay dismissed (16–17 Nov)

- **What it does:**
  - **D1:** `POST /alerts/{id}/acknowledge` (admin or owner, else 403; 404 "Alert not found") writes `acknowledged_at` (UTC), `acknowledged_by` (the display name, or "admin") and `acknowledged_by_uid`, and nothing else. A second call keeps the first one's values. Acknowledged isn't resolved: only feedback resolves an alert.
  - **D2 (frontend; the review's FE-02):** the pop-ups are worked out from the live alerts: critical (`man_down`, `possible_man_down`, `collision`, `positioning_offline`), unresolved, not acknowledged, oldest first. An admin's ✕ acknowledges the alert for everyone; if that fails, the pop-up stays, with a toast. Anyone else's ✕ hides it in that tab until a reload. With two or more showing, admins get "Dismiss all (N)" at the top. Alert cards say "Acknowledged by <name> · <local time>".
  - **D3:** stillness `man_down` and `possible_man_down` alerts carry `floor_id` and their anchor. Before raising one for someone it hasn't seen move, a restarted backend reads `/alerts` once and doesn't raise a repeat (Open #1).
- **Herman's decisions** (also in the decisions table):
  - **16 Nov, option (c):** with one or two APs, a change of strongest AP counts, as a new approximate run and as "seen moving", only after a hold. Kept with it:
    - E1: the change counts as movement only if the old run had itself lasted the hold;
    - E2: the restart check matches any AP the run had as the strongest;
    - the setting `MAN_DOWN_AP_CHANGE_HOLD_S`.
  - **16 Nov:** the restart check counts only alerts from the last `MAN_DOWN_RESTART_MATCH_H` = 12 hours.
  - **17 Nov, the hold defaults to 120 s.** In a replay of 16 Nov, a beacon left on a desk was counted as moving up to once an hour at 30 s, and never at 120 s.
    - The hold is timed from the first reading away from the run's AP, whichever other APs are the strongest meanwhile, so a third AP doesn't restart it.
    - Only a reading back at the run's AP cancels it.
  - Neither setting is in the live `.env`, so the defaults apply. A change needs a backend restart (Open #8).
- **Tests:** `f145_acknowledge_inprocess.py` 7/7, `f145_stillness_restart_inprocess.py` 19/19, and `cor03_coverage_edge_inprocess.py` 12/12 (see the harness table).
- **The live check (V5, 17 Nov):**
  - **Overnight:** Herman restarted the backend at 02:45. At 03:45, guard-001's and worker-001's runs came due at the live 60 minutes. The restart check found their 23:34 alerts (unresolved, acknowledged) and raised nothing: "already raised for this spot", in 40 and 34 ms, with 58 alerts in `/alerts`. No alert was raised between 02:26 and the live check.
  - **L1 passed.** The backlog didn't pop up again in two tabs, after a reload, after a sign-out and in, or after the restarts. Herman had dismissed it himself: 52 alerts on 16 Nov at 21:10, and the two 23:34 ambers at 01:53.
  - **L2 passed,** with man-down set to 1 minute, then back to 60:
    - After a restart, both beacons got one amber each at 14:37:32: "nothing earlier for this spot in the last 12 h", in 40 and 36 ms. Dismiss all (2) closed both in both tabs.
    - After a second restart, both matched ("already raised", 71 and 64 ms, 60 alerts), and nothing popped up.
    - Once moved next to the EAP770, `guard-001` got a new amber with no restart-check line, which means a counted move. It came 4.7 minutes after the move rather than 2 (Open #27). ✕ closed it in both tabs.
  - **L3** (a non-admin's ✕) was skipped by Herman.
  - **Only the amber path ran live here:** with two APs placed, every reading was approximate. The red path's restart check passed live on 19 Nov (Open #1).

## Working methodology

- **Prompts:** work comes as numbered "Prompt N" specs (CONTEXT → DIAGNOSE → TASK → VALIDATION, with STOP conditions).
  - If DIAGNOSE contradicts the prompt or a STOP fires, stop and report; don't work around it.
  - A precondition that fails gets reported, not assumed.
  - Smaller requests also come as plain bullet lists (like the 7 Oct follow-ups).
- **Evidence:** use real measurements over assumptions. Cite `file:line`. Never fabricate a measurement or a "yes, it's live". If you said something wrong, correct it plainly.
- **Git:**
  - Commit only when asked, and split commits logically (frontend in its own commit).
  - Run `git diff --cached --stat` right before every commit.
  - **Push only when Herman says so.**
  - Work goes on **fix branches** cut from `main`. A prompt that needs a branch says so.
  - **HANDOFF.md and README.md are tracked.** Commit changes to them only when asked. Never modify `frontend/package*.json` (Herman's own lockfile update is `13491a9`) or `backend/encode.py`.
  - **The repo is public.** Never put the 134 review's text, or any description of a **security** finding (`SEC-xx`) that isn't fixed yet, into a tracked file, a commit message or a push. Correctness, reliability and documentation items can be described (the open threads below do), and so can fixed findings, whose IDs the commit messages already carry.
  - **Herman runs git commands himself from these messages**, including steps labelled as Claude's: on 16 Oct he ran the post-merge switch before anything was merged. Give him copy-paste commands in the order he should run them, with any precondition (such as "merged on GitHub") stated before the command. On 17 Nov he had Claude run the 145 push and the v9 commit and push, and on 18 Nov the 143 push and the v10 commit and push.
- **Secrets:**
  - Never print, log, write to a fixture, or commit:
    - `VIGI_CAMERA_PASSWORD`;
    - A1 (the camera digest's first hash, which is equivalent to the password);
    - any OpenAPI `stok`;
    - `VIGI_ALARM_PATH_SECRET`.
  - The password **is** on ffmpeg's command line while live view runs. Herman accepted that. Never print an ffmpeg command line.
  - Read `.env` with `dotenv_values`, checking only shape (length, character class), never the value.
  - Before every commit and push, scan the staged diff (or the push range) for the **real** `.env` values and print only key names. A small script does this; see "Environment quirks". Also search it for the real floor and building names, read from Firestore, printing counts only. Keep device addresses, MACs and key IDs out of tracked files.
    - `ANTHROPIC_API_KEY` and `OPENAI_API_KEY` in `backend/.env` are the `.env.example` placeholders, so they always "match" `.env.example`.
- **Other actors:**
  - Herman, and the **Codex agent in VS Code** (`codex.exe`, `node_repl`). Snapshot (byte-compare) the live files before work, and re-check before copying in.
  - Someone deleted the GitHub branch on 7 Oct.
- **Browser data:** don't open Chrome's profile files (History, Sessions, IndexedDB, Cookies) unless Herman asks.
- **Herman's Chrome:** don't use it (Claude in Chrome) without asking him first (Herman, 18 Nov). A browser test touches only test devices on an inactive floor.
- **Live system:**
  - Herman's dev backend is `uvicorn main:app --reload --host 0.0.0.0 --port 8000` (backend venv). `next dev` is on :3000.
  - The live tree is on `main`, so a backend started now runs 136, 142, 145 and 143 together.
  - Saving any `.py` under `backend/` reloads the backend. Each reload costs one new camera OpenAPI login, and produces a short burst of "RuntimeError: No response returned" tracebacks (see Open #15). On 17 Nov one was also followed by a 22 s Firebase hang (Open #15, parked for 140).
  - **go2rtc runs from Herman's own terminal** (`tools\go2rtc\.\start.ps1`). Herman decided on 7 Oct: no auto-start, and don't propose launchers again unless he asks.
  - **Never stop processes by name or path:** Herman's go2rtc and any scratch copy share an executable path. Stop only PIDs you started. (Claude killed Herman's go2rtc once on 7 Oct; `start.ps1` restarted it within 10 s.)
  - Build and test in a `git archive` export in the scratchpad, then copy into the live tree once by an explicit file list, then verify with `cmp`. Before copying, check that the live files are unchanged since HEAD; compare with CR stripped (see "Environment quirks").
- **The camera's admin account locks after repeated failed OpenAPI logins** (errCode `-10030`). Never loop a login. RTSP logins (ffmpeg, probes) are a separate path; no lockout has been seen there.
- **Memory is tight on both PCs:** 2–3 GB free on the Intern laptop (2.25 GB at the start of 135, with Chrome using 4.4 GB), and 0.9–3 GB free of 15.7 GB on this PC on 13–14 Nov (`next dev` alone near 1 GB), 0.6–2.0 GB on 17 Nov, 0.3–2.3 GB on 18 Nov, about 0.5–0.8 GB on 19 Nov (Claude Code stopped a background watcher for low memory that night, so prefer short one-shot reads). For 145's and 143's test runs and `tsc` Herman asked Claude to check first that at least 1.5 GB was free, and to wait otherwise.
  - Long-running things go in Herman's own terminal.
  - Herman's rule since 131, which he confirmed on 18 Nov: **no multi-agent workflows or subagents.** This holds even when Claude Code's "Ultracode" reminder says to use workflows.
    - Claude ran multi-agent work on 3 Nov and 13–14 Nov despite the rule. Herman restated it for 145 (16 Nov) and 143 (18 Nov). On 18 Nov he allowed a workflow for the v10 commit alone, in his own words; it reviewed this file's changes.
  - **The advisor tool receives the whole conversation.** On 18–19 Nov it worked once, at about 175,000 tokens, and timed out three times after 6 minutes (`execution_time_exceeded`), at 358,000–520,000. Call it early in a session, or after `/compact`.
- **Frontend builds:** never run `next build` in the live `frontend/`, because `next dev` shares `.next`.
  - Export to the scratchpad and junction its `node_modules` to the live one (`New-Item -ItemType Junction`). Remove the junction with `cmd /c rmdir <path>` (link only); **never `rm -rf` an export that still has the junction.**
  - Copy `frontend/.env.local` in for the build only, and delete it afterwards with a **literal** path.
  - Run `tsc --noEmit --incremental false` first. On this PC run it from PowerShell: Node isn't on Git Bash's PATH (see "This PC").

## Status by prompt

| Prompt | Topic | Status |
|---|---|---|
| 104–126, 128, Open #0 | earlier work (v3/v4) | on `main` |
| 127 | offline calibration replay | **blocked:** needs ground truth (Herman's notebook times and positions for the Sep 30 / Oct 1 captures), and the captures themselves, which were in the Intern laptop's archive |
| 129 | null-RSSI grace period | not started |
| 130, 131, 131b | VIGI recon, registry/alarms/health/panel, discovery | on `main` |
| **132** | **live video** | **done**: live check passed 7 Oct (Herman), on `main` |
| — | 7 Oct follow-ups (AP rename, CCTV icon, events scroll, alarm setup) | on `main`; Herman looked at the dashboard |
| — | man-down stillness latch (Open #1) | on `main` (`2f00309`, 9 Oct) |
| 134 | whole-project review | done (9 Oct); **lost** with the Intern laptop (it was only on the local branch `review/134`) |
| **135** | **credentials and quick safety stops** | **done**: live check passed (L1 16 Oct, on Herman's word; L3 14 Oct); on `main` (`13491a9`, 16 Oct) |
| **136** | **man-down and collision correctness** | **on `main`** (7 commits); V1–V5 passed 20 Oct; **live check V6 passed 19 Nov** |
| **142** | **floors and APs** (several active floors, AP colours, calibration memory, AP removal) | **on `main`** (8 commits); map fix confirmed live 3 Nov; **live check V5 passed 19 Nov** (L2.2 and L4.1 on an earlier run of Herman's) |
| — | stuck AUTHENTICATING screen (13 Nov) | fixed in `5f70fb7` (14 Nov), on `main`; see Open #24 |
| — | camera status colours (3 Nov) | committed 16 Nov as `9f28798`; on `main` |
| **145** | **alerts that stay dismissed** (acknowledge for everyone, the pop-up banner, no stillness repeat after a restart; the review's FE-02) | **on `main`** (5 commits); V1–V4 passed; **live check V5 passed 17 Nov** (L1, L2; L3 skipped) |
| **143** | **the Floor Plans tab** (placement guides from the room's walls, camera direction, red Deactivate, names from the IP; its D5 fixes Open #29) | **on `main`** (13 commits); V1–V4 passed; **live check V5 passed 17–18 Nov, and L6 on 19 Nov** (its optional L6.4 didn't run) |
| **147** | **the stillness-timer fix:** a move counts only after three fixes in a row (Open #31) | **next** |
| **148** | **dashboard and editor fixes:** remembering the chosen floor and the calibration rounding (Open #34, #35) | after 147 |
| 133 | Ghost Patrol (evaluator, verdicts, `departed_at`, patrol enabled), plus the review's prerequisites | after 147 and 148; 136 and 142 are on `main` |
| 137–141 | rules and account controls (FE-02 moved to 145); reports and simulator; positioning; reliability; docs | planned, in that order |

## VIGI camera

### Hardware and network (verify before relying on it)
- **This PC (checked 14 Nov, updated 19 Nov):**
  - **Camera:** an InSight S245, found by discovery on 14 Nov at a lab address (its MAC and IP are in its Firestore record). It was registered again on 18 Nov at 04:01, with no checkpoint. **It isn't the InSight S445 measured on 5 Oct**, so the 5 Oct measurements below may not hold for it. Firmware 3.4.0 Build 260910 (Herman, 18 Nov).
  - **The PC:** on 19 Nov it used Wi-Fi only, with Ethernet unplugged, and that link runs through the third AP. Ethernet has a static lab address with no gateway, which is listed even with the cable out.
  - **APs:** all three post to `/telemetry/omada`. Every post on 19 Nov answered 200. Since 143 each AP's heartbeat carries the IP it posts from.
  - **OpenAPI:** on since 18 Nov, and its login works (Open #23). Port 20443 had refused the connection on 14 Nov.
  - **Password:** Herman changed the camera's admin password on 14 Nov, and `start.ps1` accepts the new one.
  - **Alarms:** `VIGI_ALARM_PATH_SECRET` is set, and alarms get through (Open #22).

The rest of this section is the Intern laptop and the 5 Oct camera, up to 16 Oct:
- **Camera:** InSight S445 v1.0, firmware 3.3.2 Build 260708.
  - A DHCP reservation for it was asked for, never verified.
  - Time zone UTC+08:00. Its clock runs about 0.7 s behind the laptop.
- **Laptop:** Ethernet gets its address from DHCP, and it kept moving: a different one on 6, 7 and 9 Oct, though the first was supposedly reserved in Omada, so **the reservation wasn't holding**.
  - **From 12 to 16 Oct the Ethernet link was down**, and only Wi-Fi was up, with a different address on each of 12, 15 and 16 Oct (go2rtc's WebRTC used the 15 Oct one).
  - While Ethernet was down, no AP report reached the backend: the 14 Oct and 15–16 Oct captures hold none. Check the link first if no markers move.
  - Live view follows the address automatically (see below).
- **Alarms:** they were arriving on 7 Oct (last checked 09:21; the camera panel shows "Working").
  - The camera's Alarm Server entry wasn't re-read; the OpenAPI can't read it.
  - Path: `/vigi/alarm/<VIGI_ALARM_PATH_SECRET>` on port 8000. Enhanced Alarm Message Service is ON and human detection is on.
- **APs** posted from one set of addresses on 7 Oct and another on 9 and 13 Oct. They have no reservations either.

### What the camera sends (130 captures, archived)
- **The push:** JSON only, with **no auth header**, so the path segment is the credential. A new connection per event.
- **Legacy format:** `event_list: [{dateTime, event_type: [...]}]`.
- **Enhanced format:** `camera: "1"`, `dateTime: "YYYY-MM-DD HH:MM:SS"`, `event_type` is a string, `extra_text` is a list of objects (`obj_num`, `region_id[]`, `obj_rect_info[]`).
- **Event types:** `MOTION` can arrive alone; only `PEOPLE` means a person. An empty scene sends nothing.

### Streams and APIs
- **Streams:**
  - `stream1`: H.264 High, 2688×1520, 25 fps;
  - `stream2`: H.264 High@3.0, 848×480, 25 fps, about 520 kbit/s with movement;
  - `stream6`: JPEG, 1 fps.
- **RTSP:** port 554, Digest MD5, user `admin`. Audio is PCMA.
- **Measured 6 Oct (stream2):**
  - An IDR every 2.0 s, starting with the first frame after PLAY.
  - **Every frame ends with a 61–97 byte SEI NAL that carries the RTP marker bit.** That's what breaks go2rtc's RTSP reader.
  - The SDP advertises `a=smart_encoder:virtualIFrame=1`. The camera's web UI has no Smart Coding setting.
- **ONVIF:** port 2020. **OpenAPI:** HTTPS on 20443, self-signed. It has no method that reads the Alarm Server settings, so `alarm_config` is only ever `mismatch` or `unknown`.
- **Discovery:** answers one ONVIF WS-Discovery probe, with its MAC in a scope.

### Backend as built (131/131b; see the commit messages)
- **Settings:**
  - `VIGI_ALARM_PATH_SECRET`, `VIGI_CAMERA_PASSWORD`, both hidden from repr.
  - `VIGI_RAW_DUMP_ENABLED` (false).
  - `VIGI_LIVENESS_INTERVAL_S` 5, `VIGI_OPENAPI_INTERVAL_S` 300, `VIGI_OPENAPI_START_DELAY_S` 60, `VIGI_DISCOVERY_INTERVAL_S` 60.
  - For 132's settings, see "Live view".
- **Registry:** `buildings/{b}/floors/{f}/cctvs`, with `source_type`, `device_mac`, `channel`, `ip`, `checkpoint_ap_id` and `timezone`.
  - `camera_key` is `ipc:<MAC, no colons>:<channel>`.
  - `(device_mac, channel)` is unique.
  - On the Intern laptop the camera was on the old floor with **no checkpoint yet**. On this PC it's on the active floor, with no checkpoint since 18 Nov.
- **`POST /vigi/alarm/{secret}`:**
  - The secret is compared in constant time; a wrong one gets a 404.
  - Only a registered MAC from its registered IP is buffered and sets `last_event_at`.
  - Every logged path under `/vigi/alarm/` reads `/vigi/alarm/***`.
- **`GET …/cctvs/{id}/detections`:** last 15 minutes, in memory; `require_auth_strict`.
- **`POST /cctvs/discover`:** admin only.
- **Heartbeat** `/cctv_heartbeats/<MAC, with underscores>`:

  | Field | Meaning |
  |---|---|
  | `last_seen` | last TCP connect to port 554 that succeeded |
  | `last_event_at` | last accepted alarm |
  | `probe`, `probe_ok_at` | OpenAPI health |
  | `alarm_config` | `mismatch` or `unknown` |
  | `discovered_at`, `discovered_via`, `ip`, `ip_mismatch` | from discovery |

- **OpenAPI lockout guard:** `backend/logs/vigi-openapi-lockout-<camera_key>.json`.
- **`PATCH /buildings/{b}/floors/{f}/aps/{ap_id}`** (7 Oct, admin): renames an AP, name only.
  - The name is trimmed, at most 64 characters; blank or too long is a 422, an unknown AP a 404.
  - New patrol logs pick the new name up within the 30 s AP caches.

### Live view (Prompt 132, as built)
- **Flow:**
  1. An admin opens the camera panel (`CameraLiveView.tsx`).
  2. The browser makes a recvonly video-only offer, with no ICE servers, gathering for up to 2 s.
  3. It posts to `POST /buildings/{b}/floors/{f}/cctvs/{id}/webrtc`: `require_admin_strict` (401 without auth), 30/minute.
  4. The backend (`services/live_view_service.py`) checks:
     - the camera exists (404);
     - the offer only receives video (422; go2rtc would treat a sending offer as a publisher);
     - it isn't an NVR camera and has a MAC and an IP (409);
     - it was seen in the last 10 s (409 "offline").
  5. The backend then rewrites the go2rtc config if needed and checks that ffmpeg exists (503).
  6. It forwards the offer to go2rtc: `POST http://127.0.0.1:1984/api/webrtc?src=ipc_<MAC>_<channel>_sub` (or `_main` for HD).
  7. It returns **only the SDP answer**. Each opened stream logs `[LIVE] … answer candidates: <ip>:8555 tcp, <ip>:8555 udp`.
- **Errors are fixed sentences; go2rtc's error text is never passed on or logged.**
  - 503 "Live view isn't running on the server" (go2rtc down).
  - 503 "Live view hasn't picked up this camera yet…" (go2rtc returned 404).
  - 503 "isn't fully installed" (no ffmpeg).
  - 502 (stream failed) and 504 (too slow).
- **Binaries** (gitignored, in `tools/go2rtc/bin/`):
  - **go2rtc 1.9.14**, from the official GitHub release `go2rtc_win64.zip`: zip SHA-256 `dd4167d7…c939907`, exe `923d5725…7d68f8c`.
  - **ffmpeg 9.0.2**, gyan.dev essentials `ffmpeg-9.0.2-essentials_build.zip`: zip SHA-256 `60f46726…3fa2047ba`, exe `3256173f…1ed8edec`.
  - Both are unsigned; Defender scans were clean.
- **The config** is generated by the backend at `GO2RTC_CONFIG_PATH` (default `tools/go2rtc/go2rtc.yaml`, gitignored). It's written at startup, after every camera create, edit or delete, and before every viewing, but **only when its content changes**, and atomically.
  - `app.modules: [api, webrtc, exec]`. No RTSP module (so no RTSP server) and no HomeKit SRTP.
  - API on `127.0.0.1:1984` with `allow_paths: ["/api", "/api/webrtc"]` (no web UI, no streams/config/log API). go2rtc also refuses `exec` sources from its API.
  - `exec.allow_paths`: only the ffmpeg path.
  - WebRTC `listen` and `candidates` on `<LAN address>:8555`, `ice_servers: []`, filters `networks: [udp4, tcp4]`.
    - The address is `GO2RTC_WEBRTC_HOST`, else the local address on the route to the registered camera, else 127.0.0.1.
    - On the Intern laptop it followed the laptop: its Ethernet address on 7 Oct, its Wi-Fi one on 15 Oct.
  - `log.output: file:go2rtc.log`, at info level. go2rtc masks `${VAR}` values as `***` in its log.
  - Streams `ipc_<MAC>_<ch>_sub|main` are each `exec:<ffmpeg> -hide_banner -loglevel quiet -nostdin -fflags nobuffer -rtsp_transport tcp -i rtsp://admin:${VIGI_CAMERA_PASSWORD}@<ip>:554/stream2|stream1 -map 0:v:0 -c:v copy -bsf:v filter_units=remove_types=6 -an -f mpegts -muxdelay 0 -muxpreload 0 -`.
    - The pipe bypasses go2rtc's RTP depacketizer, and the bitstream filter strips the SEI.
    - `-loglevel quiet` keeps ffmpeg's error text, which would contain the address, out of every log and API response.
    - The file holds `${VIGI_CAMERA_PASSWORD}`, never the value.
- **Settings:**
  - `GO2RTC_API_URL` (`http://127.0.0.1:1984`).
  - `GO2RTC_CONFIG_PATH`.
  - `GO2RTC_WEBRTC_HOST` (empty means auto).
  - `GO2RTC_FFMPEG_PATH` (default `tools/go2rtc/bin/ffmpeg.exe`).
  - A relative path is taken from `backend/`.
- **`tools/go2rtc/start.ps1`**, run by Herman in its own terminal:
  - It reads `VIGI_CAMERA_PASSWORD` from `backend/.env` on every launch, rejects characters other than letters, digits and `- _ . ~`, and passes the password only through go2rtc's process environment.
  - It relaunches go2rtc when:
    - the config changes (a camera, or the laptop's address);
    - the password changes;
    - go2rtc dies.
  - Other `.env` edits don't relaunch it.
  - It stops go2rtc **with its process tree** (`taskkill /T`), so no ffmpeg is left on the camera.
  - It warns if ffmpeg is missing, and rotates `go2rtc.log` past 10 MB.
  - It prints only its own lines, such as "go2rtc running on 127.0.0.1:1984" and the restarts.
- **Why not the original plan:**
  - **Loopback:** a socket bound to the LAN address can't send to 127.0.0.1 on Windows (WSAEADDRNOTAVAIL, reproduced). A browser's WebRTC sockets are bound to the LAN address, so go2rtc can't be on loopback only. That's option A.
    - The laptop's own browser reaches its LAN address without leaving the machine. Windows Firewall's inbound **Block** rules for go2rtc (Public profile, created when the prompt was refused) keep other devices out; local traffic isn't subject to them (tested).
  - **The SEI bug:** go2rtc 1.9.14's `pkg/h264/rtp.go:45-48` drops a marked SEI under 128 bytes without flushing the access unit. With this camera, no frame is ever emitted: ICE and DTLS connect, but there's zero RTP. It's unchanged on master. That's option 2, ffmpeg. The upstream report is drafted in `docs/go2rtc-sei-issue.md`.
  - **Restart:** go2rtc's `POST /api/restart` does nothing on Windows (it uses `syscall.Exec`). Hence `start.ps1` watches the config.
- **Measured on 7 Oct, one HD viewer:**
  - go2rtc 0.64% CPU (5% of one core), 29 MB; ffmpeg 0.15% CPU, 19 MB. go2rtc idle is about 14 MB.
  - ffmpeg exits as soon as the viewer leaves.
  - Switching HD replaces the ffmpeg.
- **Listening:** `127.0.0.1:1984` (TCP), and `<LAN>:8555` TCP and UDP.
  - Per session, pion's mDNS also opens `0.0.0.0:5353` and an `0.0.0.0`/`[::]` pair on random ports. Herman accepted these (go2rtc can't turn them off).
  - Anything else listening off loopback would be a STOP.
- **Viewing from other devices:** not built. It would need an inbound Allow rule for TCP and UDP 8555, which Herman adds himself, plus dashboard access.

### Frontend as built (camera parts)
- **`CameraPanel`:** opened by clicking a camera marker.
  - Live video for admins; others see "Live view: admins only".
  - An HD toggle, which opens a new connection.
  - States: connecting, live, the backend's sentence, camera offline, failed, with Try again.
  - Status, health and checkpoint rows.
  - **"Alarm setup"** from `last_event_at`:
    - green "Working: the camera's alarms are reaching SKYE (last one … ago)" within 24 h;
    - an older or missing alarm points to Settings > Event > Alarm Server;
    - human detection off still warns.
  - **The recent events list** scrolls in a box about 10 rows tall, with a sticky header and up to 200 rows.
- **`CctvIcon` / `CctvMarker`** (`components/map/CctvIcon.tsx`):
  - One glyph, a camera tilted down on a wall bracket, used in every place a camera is drawn.
  - On the maps it sits in a round chip. Since `9f28798` (16 Nov) the icon and its ring follow the status, like the APs, and the dashboard's status dot is gone.
- **Device editor:**
  - Camera add and edit, with the "online but not placed" list and Scan now.
  - **AP rename** (pencil on each AP row; the MAC is shown read-only).

### Herman's decisions
| # | Decision | Status |
|---|---|---|
| 2 | Patrol stays off until Ghost Patrol (both floors: `patrol_enabled=false`, empty route) | applies in 133 |
| 3, 4 | The verdict is stored on the patrol log; the window pads are ±10 s | 133 |
| 6, 7 | Live view over WebRTC with backend signalling; audio off | done (132) |
| A2 | `alarm_config` (mismatch/unknown) feeds the verdicts somehow | 133 |
| A3 | Herman draws the camera's detection area | 133 |
| 7 Oct | Option A (WebRTC on the LAN address); option 2 (ffmpeg in front); mDNS sockets accepted; password on ffmpeg's command line accepted; API hardening; go2rtc started by hand (no auto-start); work on `main` (superseded: fix branches since 136) | done |
| 9 Oct | Man-down: latch one stillness alert per episode (Open #1) | done (`2f00309`) |
| 14 Oct | Remove the stray root `package-lock.json` and root `node_modules` (Herman ran the deletes; Claude Code's auto mode blocks them) | done (`73b0e3f`) |
| 15 Oct | The 134 review stays on the local branch `review/134` and is never pushed | moot: the review was lost with the Intern laptop |
| 15–16 Oct | `OMADA_INGEST_ALLOWED_IPS` stays unset until the APs have DHCP reservations; CIDR support was offered as a follow-up | standing |
| 16 Oct | 135 merged by fast-forward from Herman's terminal, without a PR | done |
| 19 Oct | The Intern laptop is gone, so the 134 review is lost | standing |
| 20 and 22 Oct | Reading `review/134` waived: for 136 (precondition 3 and DIAGNOSE 1, 20 Oct) and for 142 (P4, 22 Oct) | done |
| 21 Oct | 136 keeps both D1 behaviours (judgement calls 1 and 2 in its report) | done |
| 3 Nov | The three placeholder APs on the old floor were Herman's to handle (gone by 22:20) | done |
| 14 Nov | The AUTHENTICATING self-recovery fix: approved, then committed by Herman (`5f70fb7`) | done |
| 14 Nov | go2rtc 1.9.14 and ffmpeg 9.0.2 installed on this PC; `fix/142-floors-aps` pushed, not `main` | done |
| 16 Nov | The camera status colours committed (`9f28798`), not pushed | done |
| 16 Nov | 145: option (c), a change of strongest AP counts only after a hold, with E1, E2 and `MAN_DOWN_AP_CHANGE_HOLD_S` kept; the restart check looks back 12 h (`MAN_DOWN_RESTART_MATCH_H`); no multi-agent review | done (`a886862`) |
| 17 Nov | 145: the hold defaults to 120 s, timed from the first reading away from the run's AP (a third AP doesn't restart it) | done (`1c5f206`) |
| 17 Nov | Parked: restart repeats that only show at the 1-minute test setting (option (b), alerts storing every AP); one missed report restarting the 120 s hold; the 22 s Firebase hang after a reload (for 140); the camera's `ClientDisconnect` alarms | standing (Open #28, #27, #15, #22) |
| 17 Nov | 145's live check passed, L3 skipped; 145 pushed with `-u` (Claude ran it), not merged; HANDOFF v9 committed and pushed on 145 | done |
| 17 Nov | Safety Settings showing 5 min and 2 m when the backend is down: to be fixed in 143 (D5) | fixed (`97863ba`), on `main` |
| 18 Nov | 143: the dashed default cone in Manage Devices only (D2.1), saved by its handle's release (a plain click too); a dragged device's name and status hidden during any drag, and Esc cancels a held drag | done (`e0d5fec`, `d1da85c`, `102e60e`) |
| 18 Nov | 143, the walls (D1): an outline with any number of corners, drawn like a zone; X and Y square to two walls more than 30° from parallel; typed X and Y on the clicked point's side; old rectangle saves dropped | done (`4380058`) |
| 18 Nov | 143's live check passed except L6 (a dock day); 143 pushed with `-u` (Claude ran it), not merged; HANDOFF v10 committed and pushed on 143 | done |
| 18 Nov | Parked for 140: a position update for a device that doesn't exist answers 500, not 404 | standing (Open #30) |
| 18 Nov | Keep `origin/claude/repo-review-r1fviz` (no prune); no use of Herman's Chrome without asking, and browser tests only on test devices on an inactive floor; the no-multi-agent rule stands | standing |
| 19 Nov | 136-L1 cut the AP reports with the Omada IoT Transport Stream switch, not a cable or a firewall rule, because the PC's only link runs through the APs | done |
| 19 Nov | No waiting for the 60-minute reds in 143's L6.6: the restart test proves the red path at 1 minute | done |
| 19 Nov | Zones should keep their drawn shape, and the dashboard should remember the chosen floor | requested (Open #33, #34) |
| 19 Nov | 136, 142, 145 and 143 merged into `main` with fast-forward pushes, and the local `main` reset to `origin/main` at about 04:09 (Herman ran both); HANDOFF v11 committed straight onto `main`, as the v7 docs were, and pushed (Claude ran it) | done |
| 19 Nov | 142-L2.2 and L4.1 passed on an earlier run, so only the backup floor's clean-up stays open from the live checks | standing (Open #32) |
| 19 Nov | Next: Prompt 147, the stillness-timer fix (a move counts only after three fixes in a row), then Prompt 148, the dashboard and editor fixes (the chosen floor remembered, the calibration rounding) | planned (Open #31, #34, #35) |

The design notes are in `docs/vigi-integration-design.md`: section 7 (Ghost Patrol) and section 8 (live view; **section 8 is partly superseded**, see Open #10).

## Field captures and archive
- **Archive (Intern laptop; not on this PC):** `C:\Users\Intern\Downloads\Omada\Project\skye-log-archive\`. Out of git, and `MANIFEST.csv` lists every file with its SHA-256. It holds:
  - every `skye*.log` recovered from the Recycle Bin (7 to 22 Sep, including the 10 Sep calibration run 2);
  - the field captures from **30 Sep** (`skye-20260930-052440.log`, AP data 13:24–13:48) and **1 Oct** (`skye-20261001-012430.log`, AP data 09:24–09:56), both with the dump on;
  - `vigi-2026-10-05\`: the alarm captures (redacted) and Prompt 130's retired `secret_path.txt`;
  - the old handoffs (7 and 8 Sep, and v4).
- **The dump-on logs contain the old Omada ingest token**, which was rotated on 13 Oct and is now worthless. Keep them out of git anyway. Since 135 (SEC-04), new dumps print `***` in its place.
- **The 10 Sep stationary evidence** is in `docs/evidence/`.
- **`OMADA_RAW_DUMP_ENABLED=false`** in `backend/.env`. The dump goes on only for captures, and each change needs a restart.

## Null-RSSI (unchanged since v4)
- No null-RSSI buffer or grace period exists. Nulls arrive as `"rssi": {}`, and the APs report about once a second.
- On the Sep 7 replay, a 2 s grace would lift 3-AP decisions from 73% to 95.5%. That's input for Prompt 129.

## Open threads — ask Herman, don't assume
1. **Man-down stillness alert flood: fixed and committed** (`2f00309`, 9 Oct). Herman chose latch once per stillness episode.
   - `_still_alerted` in `safety_service.py`: one stillness alert per episode, cleared wherever the anchor is (re)seeded (cold start, approximate→exact upgrade, movement past the epsilon). The 30 s gate stays.
   - A beacon that goes dark and comes back still within epsilon of the same anchor is the same episode, so there's no second stillness alert. A resolved alert doesn't re-fire until the person moves.
   - Test: `tools/harness/man_down_latch_inprocess.py` (6/6; the code before the fix fails 4, with 116 extra alerts in an hour).
   - **Since 145 (D3) the latch holds across a restart** for someone who hasn't moved since. Before raising a stillness `man_down` or `possible_man_down`, a restarted backend reads `/alerts` once. An unresolved alert (acknowledged or not) of the same type, for the same person, floor and spot (any AP the run had as the strongest), raised in the last 12 hours, isn't raised again, and the latch is set. Once the person has moved, alerting is as before. If the read fails, the alert is raised.
   - It logs one line per check: `[SAFETY] restart check for <person>'s <type>: read /alerts (N alerts) in M ms; already raised for this spot, not raised again`, or `…; nothing earlier for this spot in the last 12 h`. The read holds `pipeline_lock`: 34–71 ms live on 17 Nov, with 58–60 alerts.
   - **Live-checked on both paths:** the amber on 17 Nov (see "Prompt 145"), and the red on 19 Nov with three APs placed, man-down at 1 minute, on `guard-001`:
     - After a restart, one red came at 03:00:49: "nothing earlier for this spot", 47 ms, 85 alerts. An earlier red at that spot didn't count, because it had been resolved at 03:00:14.
     - With that alert unresolved and acknowledged, two more restarts raised nothing: "already raised for this spot", in 75 ms and 51 ms, 86 alerts, with new anchors 1.5 m and 1.1 m from the alert's.
     - After the beacon was carried around, a new red came at 03:12:30 with no restart-check line. It ended about 1 m from the old alert, which didn't block it, because the person had been seen moving.
     - Single noisy fixes also count as moving, so read this with #31.
2. **`/alerts` was cleared before 5 Oct 11:13:** Herman did it (answered 9 Oct). Resolved.
3. **Prompt 127** needs ground truth for the Sep 30 and Oct 1 captures. The captures themselves were in the Intern laptop's archive and aren't on this PC.
4. **Prompt 129,** the null-RSSI grace period, is not started.
5. **The simulator's Ghost Patrol bug: fixed in 135** (`a0a081d`). Each scripted event now raises only its own alert. The per-cycle limit on `ghost_patrol` inside `verify_multimodal()` is still 133's job (COR-12, second half).
6. **Kalman lock-up** (`kalman_service.py`; COR-02 in the review): solves more than 8 m away are rejected and still refresh `_last_seen`. Recalibration also triggers it. **Fixed in 136** (`73f131a`), on `main` since 19 Nov.
7. **Sep 23 ingest latency** (median 322 ms, p99 2.3 s) is unexplained.
8. **`.env` changes need a backend restart.** `--reload` only watches `.py` files. (`start.ps1` re-reads the camera password by itself.)
9. **`GET /health/tracker`** has no frontend consumer.
10. **Stale docs.** README.md was rewritten in v7. The rest belongs to Prompt 141 (DOC-01, DOC-03, DOC-04 in the review), or to whichever prompt touches the code first:
    - **`docs/vigi-integration-design.md`:**
      - its header still says "nothing here is built";
      - **§8** describes the route as `/api/cameras/{id}/webrtc`, pins a fixed LAN candidate address, and has go2rtc reading RTSP itself. As built: the cctv-shaped route, an auto-detected LAN address, ffmpeg in front, and `start.ps1` restarts.
    - **`SYSTEM_OVERVIEW.md`** was brought up to date with the code on 18 Nov (`f12b968`).
    - **`backend/.env.example`:**
      - `MAN_DOWN_MINUTES` says "in a high-risk zone", but man-down ignores zones;
      - `COLLISION_DISTANCE_M` is described as a man-down movement distance.
    - **Docstrings:**
      - `kalman_service.py:15` still says "~2 s" cadence;
      - `patrol_tracker_service.py:15` still describes the 10 Sep set-up (three APs placed and online);
      - `check_collision` in `safety_service.py` says 30 s, but the code suppresses repeats for 10 s (fixed on the fix branches by 136).
    - The `TEMP-MEASURE-119` prints are still live (`patrol_tracker_service.py`).
11. **Radius settings:** `PATROL_PROXIMITY_RADIUS_M` is 1.0. The per-floor field is ignored, and a newly created floor would store 0.0.
12. **Unchanged since v3:**
    - the unidentified "Mystery Man" beacon;
    - whether 117's hysteresis is live is inconclusive;
    - an untracked Firestore composite index;
    - `eac8b38`'s beacon-delete cleanup ignores simulated beacons.
13. **User-owned:**
    - `backend/encode.py` (gitignored; a plaintext camera password): don't touch it. It isn't on this PC.
    - Firestore `man_down_minutes`: don't touch it.
    - `frontend/package*.json`: don't modify them. Herman updated the lockfile himself in `13491a9`. The root `package-lock.json` is gone (`73b0e3f`).
14. **DHCP:** on the Intern laptop the laptop's reservation didn't hold, the APs had no reservations, and the camera's reservation was never verified (see "Hardware and network"). Live view adapts by itself; check the camera's Alarm Server target if alarms stop, because it names the laptop's address. On this PC the target is one of this PC's lab addresses (alarms arrive with the right secret); none is known to be reserved, and on 14 Nov the PC left the lab network (see "Where things stand").
15. **Reload noise:** right after every backend reload there's a 1–2 s burst of 3–15 "RuntimeError: No response returned" tracebacks. These are requests queued during the reload, in Starlette's BaseHTTPMiddleware. It's pre-existing (also seen 5 Oct) and harmless, but noisy.
    - **17 Nov, 02:26: a 22 s Firebase hang after a reload.** Right after one reload, an RTDB heartbeat write on a fresh connection was reset and retried. About 20 s of AP posts have no log line; every one logged answered 200. **Parked for 140** (Herman, 17 Nov).
16. **`docs/go2rtc-sei-issue.md`: not posting** (Herman, 9 Oct). The ffmpeg workaround is enough for SKYE; don't raise it again unless he asks. The draft is kept: it cites `master` `c245815` (bug still there on 9 Oct) and links #2277 ("VIGI no video"). Its `/api/streams` figures come from the MP4 consumer, not WebRTC.
17. **Signal-loss man-downs after a backend restart or an AP outage** (REL-01, COR-06): restarts and AP outages can raise man-downs for everyone who is still present. **Fixed in 136** (`d64c72d`, `a971584`), on `main` since 19 Nov, and passed live (136-L1).
18. **Collisions against stale positions** (COR-04): collision checks don't look at a record's age or floor. In L3, 17 of the 30 collision alerts were the simulated forklift against the real worker's old position. **Fixed in 136** (`ce2e719`), on `main` since 19 Nov, and passed live (136-L3.2).
19. **L1's evidence:** Herman reported the AP posts answered 200 after the token rotation, but no capture on disk shows them. The next time Ethernet is up, confirm that `/telemetry/omada` answers 200 (a 401 means the controller's token doesn't match `.env`). **Confirmed on 14 Nov** on this PC: posts from the EAP660 HD and the EAP770 answered 200.
20. **Simulator limits, for 138:**
    - the `events` scenario's man-down segment can't raise an alert (COR-13);
    - its missed-checkpoint event isn't guaranteed in every cycle;
    - simulations write heartbeats for the real APs, so offline APs look online (REL-07).
21. **`backend/payload.json`** is untracked since 135, but the file stays in history. No history rewrite: that's Herman's call, and the token in it was rotated on 13 Oct.
22. **The camera's alarms: getting through on 19 Nov, after failing on 14–17 Nov.**
    - **19 Nov:** 107 alarm requests between 00:04 and 02:03, all answered 200, with no traceback, after Herman set up the camera's alarm settings on 18 Nov. The notes below are kept in case the failure returns.
    - **16–17 Nov:** alarms now arrive often in the daytime and still fail the same way. On 17 Nov, 164 requests failed between 07:27 and 14:09, with two `ClientDisconnect` lines each; the traceback opened was at `routes/vigi_routes.py:35`. There were similar bursts on 16 Nov. **Parked** (Herman, 17 Nov). The notes below are from 14 Nov.
    - Only two alarm POSTs arrived, at 02:25:00 and 02:26:24: the first about 2 min 10 s after the 02:22:44 backend start, the second about 18 s after the 02:26:02 start. Each came 7–15 s after a live-view open (02:24:53 and 02:26:10). Both carried the right secret (the 404 check at `routes/vigi_routes.py:32-33` comes first), and both failed with `starlette.requests.ClientDisconnect` at `routes/vigi_routes.py:35` (`await request.body()`). Each is logged twice, by SKYE's error handler and by uvicorn: about 475 lines per alarm.
    - **Mechanism:** once the client has hung up, uvicorn 0.30.1 (`uvicorn/protocols/http/httptools_impl.py`, `receive()`) returns `http.disconnect` and drops a body it has already buffered. So SKYE only gets alarms from a camera that waits for the reply. The 5 Oct camera did (it reset about 0.5 s after the reply); this camera is a different one.
    - **Not known yet:** whether those two were Test-button presses (the 5 Oct camera's Test sent no HTTP request at all) or real detections, whether the live-view opens just before them matter, and why only two arrived (a person in view should give an event every 1–7 s).
    - **Next:** start the backend, have Herman walk in view for 30 s with human detection on, and count the POSTs and how each ends. If real alarms fail the same way, capture one with `tools/vigi-listener/listener.py` (on another port; it refuses 8000–8003) before changing how SKYE receives alarms. Either way, `vigi_alarm` should log one line instead of the traceback on `ClientDisconnect` (offered, not done).
23. **This camera's OpenAPI: on, closed 19 Nov.** Port 20443 refused the connection on 14 Nov. Herman set it up on 18 Nov, and on 19 Nov the panel's health check read "Camera API reachable and the login works" (142-L6.3).
24. **The AUTHENTICATING fix (`5f70fb7`): what wasn't checked.**
    - `tsc --noEmit` wasn't run (0.9 GB free at the time). It has since exited 0 on two trees that contain the fix, both on 16 Nov: `9f28798`'s (the camera colours) and 145's frontend commit `794261a`'s. A `next build` in an export before the demo is still worth doing.
    - The error screen and the login-page changes were tested only in a harness (32 cases) driving the real `useAuth.ts`, not live. Live: a normal load (no console errors, no reload in 37 s) and a copy of `/dashboard` with its scripts stripped (reloaded once at 20.04 s, then the hint, no loop).
    - If the `users/{uid}` read hangs (a network that doesn't answer), the error screen comes at about 40 s or later: the loader is still up at 20 s, so the page reloads once, and the reloaded page waits for Firebase Auth's start-up and then the 15 s read limit. The 25 s hint can only show on the reloaded page (about 45 s), so it may never appear. With no network at all, Firestore fails at once and the error screen comes within seconds, with no reload. Both come from reading the SDK source in the 14 Nov review, not from live tests.
    - The scratch copies and tests were in the 13 Nov session's scratchpad (`authfix2`), which is temporary.
25. **The camera panel's header sits under the Navbar** (142's report, L6): close the panel with Escape or a click on the map, and don't click the top-right corner, where Sign out is. Whether to fix it is Herman's call.
26. **Docs left stale by 136, 142 and the camera colours** (each report lists them under its stale docs): `README.md:467` (the simulators and several active floors), `skye-presentation.html:1266-1267` ("8 s AP, 15 s CCTV", but both hooks use 10 s; examiners read it, so it's Herman's call), and the `probe_ok_at` notes in `backend/services/camera_health_service.py:11-12` and `docs/vigi-integration-design.md:122`. v8 to v11 cover the HANDOFF lines.
27. **One missed report restarts the 120 s hold (17 Nov; parked).**
    - With one or two APs, a change of strongest AP counts only once the run's AP has gone 120 s without being the strongest. Any single reading where it wins again restarts the 120 s.
    - In L2, `guard-001` sat right next to the EAP770 (median -46 dBm). The EAP660 HD still heard it (median -62 dBm) and won the few readings, about 2%, where the EAP770 missed the beacon. So the move took 4.7 minutes to count instead of 2.
    - With more misses, a real move might not count for a long time, and the run, already alerted, raises nothing new at the new spot.
    - Options are in 145's report: cancel a change only after two or more readings back in a row, or don't let a reading cancel it when the new AP is absent from that reading.
28. **Restart repeats at the 1-minute test setting (17 Nov; parked).**
    - In a replay of the night of 16–17 Nov at man-down 1 minute (89% of readings from one AP), 4 of 213 simulated restarts repeated an amber within 3 minutes. In the daytime it was 0 of 286.
    - In each, the old alert was at the AP heard least, and the new run hadn't had that AP before it came due.
    - Herman: they only show at the 1-minute test setting, so no fix now. **Option (b), alerts storing every AP their run had, is parked for later.**
29. **Safety Settings showed 5 min and 2 m when the backend was down (17 Nov). Fixed** by 143's D5 (`97863ba`), on `main` since 19 Nov.
    - With 143 the boxes stay empty and Save stays off until the real values load, with Retry. It passed 143's live check (L7).
30. **A position update for a device that doesn't exist answers 500, not 404 (18 Nov; parked for 140).**
    - `PATCH …/aps/{ap_id}/position` (`routes/floor_routes.py:251`) and `PATCH …/cctvs/{cctv_id}/position` (`:388`) update the Firestore document without checking that it exists, so a drag of a device removed meanwhile gets a 500. Seen on 18 Nov for an AP. **Parked for 140** (Herman, 18 Nov).
31. **Single noisy positions restart the stillness clock (found 19 Nov; not fixed yet; the most important open bug; Prompt 147 is its fix).**
    - `check_man_down()` treats one exact fix 2 m or more from the anchor as movement. It moves the anchor, restarts the clock and clears the one-alert latch.
    - Both beacons sat still from 00:02 to 01:23 on 19 Nov. `guard-001`: 2,299 exact fixes, 95% of them within 0.41 m of its usual spot, yet the clock restarted 32 times and its longest unbroken stillness was 13.5 minutes. `worker-001`: 2,274 fixes, 177 restarts, longest 17.7 minutes.
    - So the 60-minute setting raised nothing, and the red expected at about 01:02 never came. The 1-minute live tests can't show this.
    - A 5-minute timer would still have fired, at about 00:07. But the same jumps can repeat a still person's alert at short timers, and they count as "seen moving", which skips the restart check (#1). In 136-L2.6 a 4.3 m jump at 02:17:14 ended `guard-001`'s upgrade from amber to red.
    - **Replay:** if a move needed 3 fixes in a row (about 6 s), the clocks would have restarted 0 and 2 times, and the 60-minute reds would have come at 01:02:14 and 01:05:47. Two in a row is enough for `guard-001` only (`worker-001` still restarts 71 times).
    - **Method:** the `[MEMBERSHIP-128]` log lines hold the x and y that `run_all_checks()` receives. The replay reproduced every stillness alert and restart check of 19 Nov, with the same anchors.
    - **Decided** (Herman, 19 Nov): a move counts only after three fixes in a row. Prompt 147, next, makes that change.
32. **The backup floor's clean-up (19 Nov; still to do).** The backup floor still has the three test APs and its zone `Test`: remove them. The floor is inactive, so they do no harm meanwhile. The floor names are in `combined.md`.
33. **Zones lose their drawn shape (Herman's request, 19 Nov).** Herman wants a zone to keep the shape drawn, as the walls do. A zone record stores only `x_min`, `x_max`, `y_min` and `y_max`, and `handleRightClick` in `ZoneEditor.tsx` saves the rectangle around the clicked corners. No version has stored the corners: it has worked this way since May (`9f98dc9`), and 143 only moved the drawing code. It's a new feature touching `models/zone.py`, `schemas/zone_schema.py`, `utils/zone_utils.py` (which zone a position is in), `FloorMap.tsx`, `ZoneEditor.tsx` and AI Detect, which returns rectangles. Search for `x_min` before planning it.
34. **The dashboard forgets the chosen floor (Herman's request, 19 Nov).** With two active floors, leaving the dashboard and coming back shows the first active floor again. `FloorMapArea.tsx` keeps `selectedFloorId` in component state, so it's lost when the page unmounts. Herman wants the choice remembered. It's a small frontend change, in Prompt 148.
35. **Recalibrate moves the scale slightly when the distance isn't edited (19 Nov).** `CalibrationTool.tsx` rounds the suggested distance to 1 cm and recalculates the scale from it, so a short line shifts the scale: on the backup floor 37.11 became 37.18 with 1.79 m, then 37.09 with 1.81 m. Points far apart make it tiny. A small fix could keep the current scale when the suggested distance is saved unedited. Herman asked why it happens. Prompt 148 covers it.
36. **Test feedback is in the AI reports' context (19 Nov).** All 45 documents in Firestore `feedback` come from the live checks: 43 `fixed` and 2 `confirmed`, none `false_alarm`. `rag_service.py` offers them to the reports as "Similar past incidents". Removing them before a real report is Herman's call.

## Test harness (`tools/harness/`; `tools/harness/README.md` has the commands)
- **Point it at a `git archive` export, never the live `backend/`:**
  ```bash
  git archive HEAD backend tools | tar -x -C "$exp"
  ```
  Run with `py=backend/venv/Scripts/python.exe`, as `"$py" -B …`. It refuses port 8000.
- **The suites and expected results:**

  | Suite | Expect |
  |---|---|
  | `selftest.py` | PASS |
  | `run_smoke.py` | 46/46 requests answered 200 |
  | `vigi_131_test.py --port 8003` | 34/34 |
  | `vigi_131_inprocess.py` | 5/5 |
  | `vigi_131b_inprocess.py` | 9/9 |
  | `vigi_132_inprocess.py` | **29/29** (fake go2rtc; a `ConnectionAbortedError` traceback from the fake's slow reply is expected) |
  | `ap_rename_inprocess.py` | **4/4** |
  | `man_down_latch_inprocess.py` | 6/6 |
  | `sec04_dump_redaction_inprocess.py` | 5/5 |
  | `sec01_ingest_fence_inprocess.py` | 9/9 |
  | `cor05_sim_cleanup_inprocess.py` | 8/8 |
  | `cor12_sim_events_inprocess.py` | 7/7 |
  | `cor01_timestamps_inprocess.py` | 7/7 |
  | `cor08_ap_delete_inprocess.py` | 6/6 |
  | `rel01_ap_outage_inprocess.py` (136) | 7/7 |
  | `cor03_coverage_edge_inprocess.py` (136, 145) | **12/12** since 145 (it sets the AP-change hold to 30 s) |
  | `cor06_restart_dedup_inprocess.py` (136) | 6/6 |
  | `cor04_collision_age_floor_inprocess.py` (136) | 6/6 |
  | `con03_sweep_lock_inprocess.py` (136) | 5/5 |
  | `cor02_kalman_lockup_inprocess.py` (136) | 5/5 |
  | `f142_active_floors_inprocess.py` (142) | 11/11 |
  | `f142_ap_resolution_inprocess.py` (142) | 11/11 |
  | `f142_sweep_inactive_inprocess.py` (142) | 7/7 |
  | `f142_calibration_inprocess.py` (142) | 8/8 |
  | `f142_ap_delete_inprocess.py` (142) | 7/7 |
  | `f145_acknowledge_inprocess.py` (145) | 7/7 |
  | `f145_stillness_restart_inprocess.py` (145) | 19/19 (it sets the AP-change hold to 30 s) |
  | `f143_camera_direction_inprocess.py` (143) | 14/14 |
  | `f143_ap_heartbeat_ip_inprocess.py` (143) | 9/9 |

  - **143's maths check is Node, not Python:** from PowerShell, `node --disable-warning=MODULE_TYPELESS_PACKAGE_JSON tools\harness\f143_wall_guides_check.ts`. Expect `22 passed`. It needs `frontend/utils` beside `tools/`.
  - The 135 tests are `sec04`, `sec01`, `cor05`, `cor12`, `cor01` and `cor08`. All six fail or crash on `2f00309`, the code before 135.
  - COR-05 and COR-12 fake the simulators' HTTP client and send them to a dead port. The harness tripwire doesn't cover `localhost`, and `localhost:8000` is the live backend.
  - The review's fix plan asks every later prompt to add an in-process test for each finding it closes.
  - The 136, 142, 145 and 143 suites are on `main` since 19 Nov. Their reports have each suite's result on the code before the change.
  - Since 136, `run_smoke.py`'s sweeper also raises `positioning_offline` for the seeded stale worker.
  - **Never pass `--backend-dir` to `selftest.py`:** its first argument is a scratch folder, and a runner once wrote a `--backend-dir/` folder into the repo root.

- **Run `run_smoke.py` with the repo's own harness against the export.** The export's copy of the driver reads `<export>/backend/.env`, which `vigi_131_test.py` leaves holding fake values, so the result is 46 × 401.
- **The launcher** sets `VIGI_DISCOVERY_INTERVAL_S=0`, `GO2RTC_CONFIG_PATH=<run_dir>/go2rtc.yaml` and `GO2RTC_API_URL` to a dead port unless the caller sets them. So no harness server multicasts on the LAN or touches the live go2rtc.
- **Opt-in switches:**
  - `HARNESS_FAKE_AUTH=1` (`harness-token:<uid>`);
  - `HARNESS_ENV_PATH` (a test `.env`).

## Environment quirks
- **This PC** (`D:\DOWNLOAD\Y3S2\FYP\SKYE`, since 19 Oct). Where it differs from the Intern-laptop notes below:
  - **Backend venv:** python.org Python 3.13.9, not uv 3.12. Brought up to `backend/requirements.txt` on 21 Oct (`google-genai` 2.22.0, pydantic 2.13.5; `pip check` clean). `google-generativeai` 0.7.2 is still installed.
  - **Node:** `D:\DOWNLOAD\node.exe` (v24.19.0). It's on PowerShell's PATH but not Git Bash's, so run `node`, `npx` and `tsc` from PowerShell.
  - **Firebase key:** `backend\serviceAccountKey.json` holds the key in use since 22 Oct (checked 3 Nov). An older, revoked key made `create_app()` retry Firestore for 300 s and then fail.
  - **go2rtc:** `tools/go2rtc/bin/` holds go2rtc 1.9.14 and ffmpeg 9.0.2, installed on 14 Nov from the official releases. The zip and exe SHA-256 match the values under "Live view".
  - **Outside the repo:** `D:\DOWNLOAD\Y3S2\FYP\skye-scratch\` holds `136\report.md`, `136\scan_env.py`, `136\venv-freeze-before.txt`, `142\report.md`, `142\live-check-findings.md`, `142\floormap-harness-results.md`, `142\camera-status\` (`stage.patch`, `msg.txt` and the 3 Nov reviews, for the camera-colour commit), `142\auth-fix\msg.txt`, `145\report.md`, `145\stages\` (145's stage patches and commit messages, and scratch scripts that print counts only), `143\report.md`, `143\branch-check.md`, `143\stages\` (143's patches, commit messages and copy scripts), `143\name_search.py` (the real floor and building names, read from Firestore; counts only) and `143\leak_scan.py` (addresses, MACs and key IDs; counts only). `live-checks\combined.md` is the 19 Nov list with its results. There's no `skye-log-archive` here.
  - **The `.env` scan** (PowerShell): `git diff origin/main...<branch> | backend\venv\Scripts\python.exe -I D:\DOWNLOAD\Y3S2\FYP\skye-scratch\136\scan_env.py .` prints key names only. In Git Bash, use forward slashes.
  - **Line endings:** `HANDOFF.md` is CRLF here (the Intern-laptop note below says LF). Check with `git ls-files --eol`.
  - **Logs:** backend logs split into 50 MB `.partNNN.log` files (about 75 minutes each on 16–17 Nov). The names are in UTC (`skye-YYYYMMDD-HHMMSS`), one file per process start or reload; local time is UTC+8. A directory listing can show a stale size for the file being written, so open the file to check it. Each position decision logs one `[MEMBERSHIP-128]` line (person, fresh APs, outcome, x, y), so man-down can be replayed offline (Open #31).
  - **Claude in Chrome:** only with Herman's go-ahead (see "Working methodology"). The extension can open a new window, and a tab behind another window throttles timers, which spoils load timings.
- **Intern laptop (to 16 Oct):** the rest of this section, except where it says otherwise.
- **Shells:** PowerShell is primary; the Bash tool is Git Bash.
- **Python:**
  - **A plain `python` on this laptop is 3.14.7** (also `py`'s default). It can't install the backend's pinned `numpy` 2.1.3 or `scipy` 1.14.1, which have no 3.14 wheels: pip stops at numpy with `Unknown compiler(s)` (tested 16 Oct).
  - **`py` is the Python install manager** (26.4 on 16 Oct). `py -3.12` means `-V:PythonCore\3.12`, so it never selects uv's Pythons, registered or not, and there's no python.org 3.12 here. `py install 3.12` would add one (3.12.10); that's Herman's call.
  - **The backend venv is 3.12.13,** built on uv's own Python, and it has pip. Both ways to recreate it were tested on 16 Oct:
    - `& "$env:APPDATA\uv\python\cpython-3.12.13-windows-x86_64-none\python.exe" -m venv venv`, then `venv\Scripts\python.exe -m pip install -r requirements.txt`;
    - or `uv venv --python 3.12 venv`, then `uv pip install -r requirements.txt --python venv\Scripts\python.exe` (that venv has no pip).
  - On 16 Oct, 3.11.15 and 3.13.15 also installed everything and passed all 13 harness suites (`check_capture.py` needs 3.12+). They were scratch installs and have been removed.
  - `backend\venv\Scripts\python.exe` is a **uv trampoline**, so kill the PID a process reports for itself. The real interpreter is `%APPDATA%\uv\python\cpython-3.12-…`, and the firewall Allow rules are for it. The network profile is Public.
- **Line endings:**
  - `core.autocrlf=true` (system-wide). The working tree is mixed: on 16 Oct, 220 tracked files were CRLF and 40 were LF (HANDOFF.md among them; README.md is CRLF). `git archive` output is CRLF.
  - Keep each file's existing endings, and check with `git ls-files --eol <file>`.
  - **Git Bash `sed -i` strips the CRs** (re-add them with `sed -i 's/$/\r/'` or use the Edit tool).
  - Python's `read_text`/`write_text` also convert; use bytes.
- **Hashing in Git Bash:** `sha256sum` prefixes its output with `\` for paths containing backslashes. Compare with `cmp`, or cut carefully.
- **Bash tool:** a `\\` inside a heredoc can reach Python as `\`. For text containing escapes, use the Edit tool.
- **Claude Code safety checks:**
  - `rm -rf "$VAR/…"` and `Remove-Item "$X\…"` with variable paths are blocked. Use `"${VAR:?}"` or literal absolute paths.
  - A blocked command doesn't run at all.
  - Auto mode also blocks `git rm` of tracked files and deleting folders such as `node_modules` (14 Oct). Herman runs those himself.
- **Logs:**
  - `backend/logs/` captures are UTF-8; one file per backend process start. Nothing prunes `backend/logs`.
  - `tools/go2rtc/go2rtc.log` rotates at 10 MB.
- **Tools:**
  - `openssl` and `pdftotext` are in Git Bash.
  - Chrome 154 and Edge 154 are installed; headless Chrome is good for WebRTC checks (getStats) and for rendering previews to PNG.
  - `gh`, `gcloud` and `ffprobe` aren't installed (`gh` re-checked 16 Oct). The repo is public, so `curl https://api.github.com/repos/herman-1110/SKYE/pulls?state=all` reads PR state without a login.
- **Firebase:** the CLI is authenticated to the project; deploys need an explicit go-ahead. The laptop's backend used its own service-account key; an old leaked key is revoked. On this PC the key is the one under "This PC", and the CLI wasn't checked.
- **Identities:**
  - real beacons: `guard-001`, `worker-001`;
  - simulated: `sim-*`, `test-*`; the simulators also write a fake camera's heartbeat (`backend/services/simulation_*.py`).
- **Hardware:** three APs, two EAP660 HD and an EAP770 (their MACs are in Firestore and the heartbeats). Since 00:02 on 19 Nov all three are placed on the active floor, another floor of the same building as the old one, which was emptied and deactivated on 13 Nov. Since 142 several floors can be active.
- **Diagnostic scripts from 6–7 Oct** live in that session's scratchpad (`webrtc-diag/`, `e2e/`). They're useful as patterns:
  - a minimal RTSP client that logs NAL types and marker bits;
  - a headless-Chrome WebRTC stats page;
  - a scratch go2rtc on other ports.

  The scratchpad is temporary.

## Suggested first message in the new chat
"Continue from HANDOFF.md v11. Before anything else:
1. Run `git status`, `git log --oneline -20` and `git ls-remote --heads origin` fresh. The live tree is on `main` (the v11 commit, on top of `a6ee040`), which holds 136, 142, 145 and 143. Ask me before committing or pushing anything, don't merge, and don't prune (keep `origin/claude/repo-review-r1fviz`).
2. Read `D:\DOWNLOAD\Y3S2\FYP\skye-scratch\live-checks\combined.md`, and Open #1, #22 and #31–#36 here.
3. Check what's running (backend on :8000, `next dev` on :3000, go2rtc on :1984), this PC's network address and the free memory, and don't start, stop or restart my servers.

Then I'll give you Prompt 147, the stillness-timer fix (Open #31); change nothing before it. After it come Prompt 148 (Open #34 and #35), the backup floor's clean-up (Open #32), Open #33 and #36, and then Prompt 133. Leave `man_down_minutes` and `backend/encode.py` alone, keep secrets out of all output and addresses, MACs, key IDs and real names out of tracked files, no multi-agent workflows or subagents, and don't use my Chrome without asking; a browser test touches only test devices on an inactive floor."
