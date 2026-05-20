"use client";
import { useRef } from "react";

interface Props {
  value: string;
  onChange: (mac: string) => void;
  error?: string;
}

export default function MacAddressInput({ value, onChange, error }: Props) {
  const segments = value ? value.split(":") : ["", "", "", "", "", ""];
  const refs = useRef<(HTMLInputElement | null)[]>([]);

  const updateSegment = (index: number, raw: string) => {
    const clean = raw.replace(/[^0-9A-Fa-f]/g, "").toUpperCase().slice(0, 2);
    const next = [...segments];
    next[index] = clean;
    onChange(next.join(":"));
    if (clean.length === 2 && index < 5) {
      refs.current[index + 1]?.focus();
    }
  };

  const handleKeyDown = (index: number, e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Backspace" && segments[index] === "" && index > 0) {
      refs.current[index - 1]?.focus();
    }
    if (e.key === "ArrowRight" && index < 5) refs.current[index + 1]?.focus();
    if (e.key === "ArrowLeft" && index > 0) refs.current[index - 1]?.focus();
  };

  const handlePaste = (e: React.ClipboardEvent) => {
    e.preventDefault();
    const hex = e.clipboardData.getData("text")
      .replace(/[^0-9A-Fa-f]/g, "").toUpperCase();
    if (hex.length === 12) {
      onChange((hex.match(/.{2}/g) as string[]).join(":"));
      refs.current[5]?.focus();
    }
  };

  const borderColor = error ? "var(--danger, #ef4444)" : "var(--border)";

  return (
    <div>
      <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
        {[0, 1, 2, 3, 4, 5].map((i) => (
          <div key={i} style={{ display: "flex", alignItems: "center", gap: 4 }}>
            <input
              ref={(el) => { refs.current[i] = el; }}
              value={segments[i] ?? ""}
              maxLength={2}
              placeholder="FF"
              onChange={(e) => updateSegment(i, e.target.value)}
              onKeyDown={(e) => handleKeyDown(i, e)}
              onPaste={handlePaste}
              onFocus={(e) => {
                e.currentTarget.style.borderColor = error
                  ? "var(--danger, #ef4444)"
                  : "var(--accent, #f59e0b)";
              }}
              onBlur={(e) => {
                e.currentTarget.style.borderColor = borderColor;
              }}
              style={{
                width: 32,
                height: 36,
                textAlign: "center",
                fontFamily: "var(--font-mono, monospace)",
                fontSize: 13,
                fontWeight: 600,
                letterSpacing: "0.05em",
                color: "var(--text-primary)",
                background: "var(--bg-surface)",
                border: `1.5px solid ${borderColor}`,
                borderRadius: 8,
                outline: "none",
                caretColor: "var(--accent, #f59e0b)",
                transition: "border-color 0.15s",
              }}
            />
            {i < 5 && (
              <span style={{
                color: "var(--text-secondary)",
                fontSize: 14,
                fontFamily: "var(--font-mono, monospace)",
                userSelect: "none",
                lineHeight: 1,
              }}>:</span>
            )}
          </div>
        ))}
      </div>
      {error && (
        <p style={{ color: "var(--danger, #ef4444)", fontSize: 11, marginTop: 4 }}>
          {error}
        </p>
      )}
    </div>
  );
}
