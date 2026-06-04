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
          base:         "var(--bg-base)",
          surface:      "var(--bg-surface)",
          // rgb() + <alpha-value> enables opacity modifiers: bg-s-elevated/60, border-s-danger/30, etc.
          elevated:     "rgb(var(--bg-elevated-rgb) / <alpha-value>)",
          border:       "rgb(var(--border-rgb) / <alpha-value>)",
          accent:       "rgb(var(--accent-rgb) / <alpha-value>)",
          "accent-dim": "var(--accent-dim)",
          success:      "rgb(var(--success-rgb) / <alpha-value>)",
          danger:       "rgb(var(--danger-rgb) / <alpha-value>)",
          info:         "rgb(var(--info-rgb) / <alpha-value>)",
          warning:      "var(--warning)",
          text:         "var(--text-primary)",
          muted:        "var(--text-secondary)",
          mono:         "var(--text-mono)",
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
