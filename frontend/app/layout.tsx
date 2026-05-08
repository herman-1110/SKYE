import type { Metadata } from "next";
import { IBM_Plex_Sans, IBM_Plex_Mono } from "next/font/google";
import "./globals.css";
import ThemeProvider from "@/components/layout/ThemeProvider";

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

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${ibmPlexSans.variable} ${ibmPlexMono.variable}`} suppressHydrationWarning>
      <head>
        {/* eslint-disable-next-line @next/next/no-sync-scripts */}
        <script dangerouslySetInnerHTML={{ __html: themeScript }} />
      </head>
      <body className="font-sans antialiased bg-s-base text-s-text min-h-screen" suppressHydrationWarning>
        <ThemeProvider />
        {children}
      </body>
    </html>
  );
}
