import {
  GoogleAuthProvider,
  createUserWithEmailAndPassword,
  onAuthStateChanged,
  sendEmailVerification,
  signInWithEmailAndPassword,
  signInWithPopup,
  signOut as _signOut,
  type User,
} from "firebase/auth";
import { auth } from "@/config/firebase";

export async function signIn(email: string, password: string): Promise<User> {
  const cred = await signInWithEmailAndPassword(auth, email, password);
  return cred.user;
}

export async function registerWithEmail(
  email: string,
  password: string,
): Promise<{ user: User; idToken: string }> {
  const userCredential = await createUserWithEmailAndPassword(auth, email, password);
  await sendEmailVerification(userCredential.user);
  const idToken = await userCredential.user.getIdToken();
  return { user: userCredential.user, idToken };
}

export async function resendVerificationEmail(): Promise<void> {
  const user = auth.currentUser;
  if (user) await sendEmailVerification(user);
}

export async function syncEmailVerified(): Promise<void> {
  const user = auth.currentUser;
  if (!user) throw new Error("No authenticated user");
  // Force-refresh so the token reflects the latest emailVerified claim
  const token = await user.getIdToken(true);
  console.log(`[verify-email] Token obtained: len=${token.length}, starts=${token.substring(0, 20)}`);
  const res = await fetch("/api/auth/verify-email", {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error((err as { detail?: string }).detail ?? "Sync failed");
  }
}

export async function signOut(): Promise<void> {
  await _signOut(auth);
}

export function onAuthChanged(callback: (user: User | null) => void): () => void {
  return onAuthStateChanged(auth, callback);
}

export async function signInWithGoogle(): Promise<{ uid: string; role: string; status: string }> {
  const provider = new GoogleAuthProvider();
  const result = await signInWithPopup(auth, provider);
  const idToken = await result.user.getIdToken();

  const res = await fetch("/api/auth/google", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ id_token: idToken }),
  });

  if (!res.ok) throw new Error("Google authentication failed");
  return res.json() as Promise<{ uid: string; role: string; status: string }>;
}
