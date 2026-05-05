import { getApps, initializeApp, type FirebaseApp } from "firebase/app";
import { type Auth, getAuth } from "firebase/auth";
import { type Database, getDatabase } from "firebase/database";
import { type Firestore, getFirestore } from "firebase/firestore";
import { type FirebaseStorage, getStorage } from "firebase/storage";

const firebaseConfig = {
  apiKey:            process.env.NEXT_PUBLIC_FIREBASE_API_KEY!,
  authDomain:        process.env.NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN!,
  databaseURL:       process.env.NEXT_PUBLIC_FIREBASE_RTDB_URL!,   // Realtime DB
  projectId:         process.env.NEXT_PUBLIC_FIREBASE_PROJECT_ID!,
  storageBucket:     process.env.NEXT_PUBLIC_FIREBASE_STORAGE_BUCKET!,
  messagingSenderId: process.env.NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID!,
  appId:             process.env.NEXT_PUBLIC_FIREBASE_APP_ID!,
};

// initializeApp() is called ONCE here — never in any other file
const app: FirebaseApp =
  getApps().length === 0 ? initializeApp(firebaseConfig) : getApps()[0];

export const db: Database = getDatabase(app);           // Realtime Database — /positions, /alerts
export const fsdb: Firestore = getFirestore(app);       // Firestore — patrol_logs, audit_reports, feedback
export const storage: FirebaseStorage = getStorage(app); // Storage — floor plan images
export const auth: Auth = getAuth(app);
