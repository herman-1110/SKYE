"use client";
import { useState } from "react";

export default function SelectDropdown<T>({
  label,
  items,
  selectedId,
  getId,
  getLabel,
  onSelect,
  disabled = false,
  placeholder = "Select…",
}: {
  label?: string;
  items: T[];
  selectedId: string | null;
  getId: (item: T) => string;
  getLabel: (item: T) => string;
  onSelect: (id: string) => void;
  disabled?: boolean;
  placeholder?: string;
}) {
  const [open, setOpen] = useState(false);
  const selected = items.find((item) => getId(item) === selectedId);

  return (
    <>
      {label && (
        <span className="font-mono text-[10px] text-s-muted tracking-widest uppercase shrink-0">
          {label}
        </span>
      )}
      <div style={{ position: "relative", display: "inline-block" }}>
        <button
          type="button"
          className={`dropdown-trigger${disabled ? " opacity-50 cursor-not-allowed" : ""}`}
          onClick={() => { if (!disabled) setOpen((prev) => !prev); }}
          onBlur={() => setTimeout(() => setOpen(false), 150)}
        >
          <span>{selected ? getLabel(selected) : placeholder}</span>
          <svg
            width="12" height="12" viewBox="0 0 12 12" fill="none"
            style={{
              transform: open ? "rotate(180deg)" : "rotate(0deg)",
              transition: "transform 180ms ease",
              marginLeft: "6px",
              flexShrink: 0,
            }}
          >
            <path d="M2 4L6 8L10 4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </button>

        {open && (
          <ul className="dropdown-menu">
            {items.map((item) => {
              const id = getId(item);
              return (
                <li
                  key={id}
                  className={`dropdown-item${selectedId === id ? " active" : ""}`}
                  onMouseDown={() => { onSelect(id); setOpen(false); }}
                >
                  {getLabel(item)}
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </>
  );
}
