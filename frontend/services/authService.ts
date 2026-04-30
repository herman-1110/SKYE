import {
  onAuthStateChanged,
  signInWithEmailAndPassword,
  signOut as _signOut,
  type User,
} from "firebase/auth";
import { auth } from "@/config/firebase";

export async function signIn(email: string, password: string): Promise<User> {
  const cred = await signInWithEmailAndPassword(auth, email, password);
  return cred.user;
}

export async function signOut(): Promise<void> {
  await _signOut(auth);
}

export function onAuthChanged(callback: (user: User | null) => void): () => void {
  return onAuthStateChanged(auth, callback);
}
