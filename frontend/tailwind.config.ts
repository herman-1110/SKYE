import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        s: {
          base:       "var(--bg-base)",
          surface:    "var(--bg-surface)",
          elevated:   "var(--bg-elevated)",
          border:     "var(--border)",
          accent:     "var(--accent)",
          "accent-dim": "var(--accent-dim)",
          success:    "var(--success)",
          danger:     "var(--danger)",
          warning:    "var(--warning)",
          text:       "var(--text-primary)",
          muted:      "var(--text-secondary)",
          mono:       "var(--text-mono)",
        },
      },
      fontFamily: {
        sans: ["var(--font-sans)", "system-ui", "sans-serif"],
        mono: ["var(--font-mono)", "ui-monospace", "monospace"],
      },
      animation: {
        "alert-pulse":  "alert-pulse 2s ease-in-out infinite",
        "amber-pulse":  "amber-pulse 1.2s ease-in-out infinite",
      },
    },
  },
  plugins: [],
};

export default config;
