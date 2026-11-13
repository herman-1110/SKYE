// Pure helpers for the sign-in check in hooks/useAuth.ts: reading users/{uid}
// with a deadline, and the plain-words messages the dashboard's error screen
// and the login page show. No imports, so they can be tested on their own.

// The longest the users/{uid} read may take before the sign-in check counts
// as failed. Firestore itself rejects after about 10 s when it can't reach
// its backend ("client is offline"); this catches a read that never settles.
export const RECORD_TIMEOUT_MS = 15_000;

export const UNVERIFIED_MESSAGE =
  "Your email address isn't verified yet. Open the link we sent you, then sign in again.";
export const NO_RECORD_MESSAGE =
  "You're signed in, but there's no SKYE account for this email. Register first, or ask your Security Manager.";
export const SIGNED_OUT_MESSAGE = "You're not signed in any more. Please sign in again.";
export const SUPERSEDED_MESSAGE = "Your sign-in changed while SKYE was checking it. Please sign in again.";

// Settles like `promise`, but rejects with code "deadline-exceeded" if
// `promise` hasn't settled within `ms`.
export function withTimeout<T>(promise: Promise<T>, ms: number): Promise<T> {
  return new Promise<T>((resolve, reject) => {
    const timer = setTimeout(() => {
      reject(Object.assign(new Error(`No answer within ${ms} ms`), { code: "deadline-exceeded" }));
    }, ms);
    promise.then(
      (value) => {
        clearTimeout(timer);
        resolve(value);
      },
      (err: unknown) => {
        clearTimeout(timer);
        reject(err);
      },
    );
  });
}

// What went wrong reading users/{uid}, in plain words. Firestore errors carry
// a code such as "unavailable" (offline) or "permission-denied".
export function describeRecordError(err: unknown): string {
  const code =
    typeof err === "object" && err !== null && "code" in err ? String((err as { code: unknown }).code) : "";
  switch (code) {
    case "deadline-exceeded":
      return "The account database didn't answer in time, so SKYE couldn't check your account. Try again.";
    case "unavailable":
      return "SKYE couldn't reach the account database. Check the internet connection, then try again.";
    case "permission-denied":
      return "The account database refused to show your account. Ask your Security Manager to check your access.";
    default:
      return code
        ? `SKYE couldn't check your account (error: ${code}). Try again.`
        : "SKYE couldn't check your account. Try again.";
  }
}
