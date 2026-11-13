import type { Metadata } from "next";
import { IBM_Plex_Sans, IBM_Plex_Mono } from "next/font/google";
import "./globals.css";
import ThemeProvider from "@/components/layout/ThemeProvider";
import { AuthProvider } from "@/hooks/useAuth";

const ibmPlexSans = IBM_Plex_Sans({
  weight: ["400", "500", "600", "700"],
  subsets: ["latin"],
  variable: "--font-sans",
  display: "swap",
});

const ibmPlexMono = IBM_Plex_Mono({
  weight: ["400", "500"],
  subsets: ["latin"],
  variable: "--font-mono",
  display: "swap",
});

export const metadata: Metadata = {
  title: "SKYE — Sentinel-AI Safety Dashboard",
  description: "Autonomous Industrial Safety & Semantic Patrol Intelligence System",
};

// Runs before React hydration to prevent flash of wrong theme.
const themeScript = `(function(){try{var s=localStorage.getItem('skye-theme');var t=s?JSON.parse(s).state?.theme:null;if(t==='light'){document.documentElement.classList.add('light')}else{document.documentElement.classList.add('dark')}}catch(e){}})()`;

// Load watchdog. It runs from the server's HTML, so it works even when the
// page's JavaScript never starts: on 13 Nov the dev server rewrote a script
// while the browser was downloading it, and the page sat on AUTHENTICATING
// with nothing running. 20 s after the page arrives, if React still hasn't
// started (AuthProvider sets window.__skyeAppStarted) or the AUTHENTICATING
// loader ([data-skye-loader]) is still up, it reloads the page once. It
// skips a second reload within 2 minutes, so it can't loop; the loader then
// shows its "taking longer than it should" hint (.skye-slow-hint). It does
// nothing on Next's error page (html#__next_error__), so a crash on the
// first render stays on screen.
const loadWatchdogScript = `(function(){try{var k='skye-auto-reload-at';setTimeout(function(){try{if(document.documentElement.id==='__next_error__')return;if(window.__skyeAppStarted&&!document.querySelector('[data-skye-loader]'))return;var last=Number(sessionStorage.getItem(k))||0;if(Date.now()-last<120000)return;sessionStorage.setItem(k,String(Date.now()));location.reload()}catch(e){}},20000)}catch(e){}})()`;

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${ibmPlexSans.variable} ${ibmPlexMono.variable}`} suppressHydrationWarning>
      <head>
        {/* eslint-disable-next-line @next/next/no-sync-scripts */}
        <script dangerouslySetInnerHTML={{ __html: themeScript }} />
        <script dangerouslySetInnerHTML={{ __html: loadWatchdogScript }} />
      </head>
      <body className="font-sans antialiased bg-s-base text-s-text min-h-screen" suppressHydrationWarning>
        <ThemeProvider />
        <AuthProvider>{children}</AuthProvider>
      </body>
    </html>
  );
}
