import type { PatrolLogRecord } from "@/types/patrolLog";
import type { APRecord } from "@/services/floorService";

// Deterministic ordering for one patrol cycle's logs (Prompt 121). A skip
// record legitimately shares its expected_arrival with the real visit that
// triggered it — patrol_tracker_service.py's _close_visit skip-backfill fires
// when the guard's detected checkpoint jumps past one or more route entries,
// and both the skip and the real visit inherit the same last_departed_at
// (v20 §10). Sorting by expected_arrival alone leaves that tie to whatever
// arbitrary order Firestore/JS happens to return — which must never vary
// between loads for a compliance artefact.
//
// This breaks the tie by the checkpoint's position in the CURRENT
// patrol_route, joined by mac (never by zipping logs to route by array
// index — v20 §10). A genuine out-of-order traversal always produces
// distinct expected_arrival values, so this tiebreaker never fires on real
// data — it only resolves exact ties, it does not normalise real sequences
// into route order.
//
// Unmatched checkpoints (an AP removed from patrol_route after logs were
// written) sort after every matched one, ordered deterministically by
// checkpoint_id string — never left to resolve arbitrarily.
//
// Does not handle a patrol_route containing the same AP twice (v20 §8) — the
// mac-keyed log maps built from this ordering already collapse that case,
// and this tiebreaker inherits that assumption rather than fixing it here.
export function sortPatrolLogsDeterministically(
  logs: PatrolLogRecord[],
  routeAps: APRecord[],
): PatrolLogRecord[] {
  const routeIndexByMac = new Map(routeAps.map((ap, idx) => [ap.mac.toUpperCase(), idx]));

  return [...logs].sort((a, b) => {
    if (a.expected_arrival !== b.expected_arrival) {
      return a.expected_arrival < b.expected_arrival ? -1 : 1;
    }
    const ia = routeIndexByMac.get(a.checkpoint_id.toUpperCase());
    const ib = routeIndexByMac.get(b.checkpoint_id.toUpperCase());
    if (ia !== undefined && ib !== undefined) return ia - ib;
    if (ia !== undefined) return -1;
    if (ib !== undefined) return 1;
    return a.checkpoint_id < b.checkpoint_id ? -1 : a.checkpoint_id > b.checkpoint_id ? 1 : 0;
  });
}
