"use client";
import { useEffect } from "react";
import { useThemeStore } from "@/store/themeStore";

export default function ThemeProvider() {
  const theme = useThemeStore((s) => s.theme);

  useEffect(() => {
    const html = document.documentElement;
    // Enable smooth transition for this toggle only
    html.classList.add("theme-transitioning");
    if (theme === "light") {
      html.classList.add("light");
      html.classList.remove("dark");
    } else {
      html.classList.remove("light");
      html.classList.add("dark");
    }
    const t = setTimeout(() => html.classList.remove("theme-transitioning"), 250);
    return () => clearTimeout(t);
  }, [theme]);

  return null;
}
