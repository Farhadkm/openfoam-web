"use client";

import { useCallback, useEffect, useId, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

export type ForgeSelectOption = {
  value: string;
  label: string;
};

type Props = {
  value: string;
  onChange: (value: string) => void;
  options: ForgeSelectOption[];
  disabled?: boolean;
  id?: string;
  className?: string;
  placeholder?: string;
  /** Render the dropdown on document.body (fixed position). Defaults true when className includes forge-select--toolbar. */
  portaledMenu?: boolean;
  "aria-label"?: string;
};

function shouldUsePortal(className: string, portaledMenu?: boolean) {
  return portaledMenu ?? className.includes("forge-select--toolbar");
}

export function ForgeSelect({
  value,
  onChange,
  options,
  disabled = false,
  id,
  className = "",
  placeholder = "Select…",
  portaledMenu,
  "aria-label": ariaLabel,
}: Props) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const menuRef = useRef<HTMLUListElement>(null);
  const listId = useId();

  const usePortal = shouldUsePortal(className, portaledMenu);
  const isToolbar = className.includes("forge-select--toolbar");

  const [menuPos, setMenuPos] = useState<{ top: number; left: number; minWidth: number } | null>(
    null,
  );

  const selected = options.find((o) => o.value === value);
  const display = selected?.label ?? placeholder;

  const updateMenuPosition = useCallback(() => {
    const trigger = triggerRef.current;
    if (!trigger) return;
    const rect = trigger.getBoundingClientRect();
    setMenuPos({ top: rect.bottom + 4, left: rect.left, minWidth: rect.width });
  }, []);

  useLayoutEffect(() => {
    if (!open || !usePortal) {
      setMenuPos(null);
      return;
    }
    updateMenuPosition();
  }, [open, usePortal, updateMenuPosition]);

  useEffect(() => {
    if (!open || !usePortal) return;
    const onScrollOrResize = () => updateMenuPosition();
    window.addEventListener("scroll", onScrollOrResize, true);
    window.addEventListener("resize", onScrollOrResize);
    return () => {
      window.removeEventListener("scroll", onScrollOrResize, true);
      window.removeEventListener("resize", onScrollOrResize);
    };
  }, [open, usePortal, updateMenuPosition]);

  useEffect(() => {
    if (!open) return;
    const onDocMouse = (e: MouseEvent) => {
      const target = e.target as Node;
      if (rootRef.current?.contains(target)) return;
      if (menuRef.current?.contains(target)) return;
      setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onDocMouse);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDocMouse);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const menuClassName = [
    "forge-select-menu",
    usePortal ? "forge-select-menu--portal" : "",
    isToolbar ? "forge-select-menu--toolbar" : "",
  ]
    .filter(Boolean)
    .join(" ");

  const menuStyle =
    usePortal && menuPos
      ? {
          top: menuPos.top,
          left: menuPos.left,
          minWidth: menuPos.minWidth,
        }
      : undefined;

  const menu = (
    <ul
      ref={menuRef}
      id={listId}
      className={menuClassName}
      role="listbox"
      style={menuStyle}
    >
      {options.map((opt) => {
        const isSelected = opt.value === value;
        return (
          <li key={opt.value} role="presentation">
            <button
              type="button"
              role="option"
              aria-selected={isSelected}
              className={`forge-select-option${isSelected ? " is-selected" : ""}`}
              onClick={() => {
                onChange(opt.value);
                setOpen(false);
              }}
            >
              <span className="forge-select-option-label">{opt.label}</span>
              {isSelected && (
                <span className="forge-select-option-check" aria-hidden>
                  <svg
                    width="14"
                    height="14"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2.5"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  >
                    <polyline points="20 6 9 17 4 12" />
                  </svg>
                </span>
              )}
            </button>
          </li>
        );
      })}
    </ul>
  );

  const portaledMenuNode =
    open &&
    usePortal &&
    menuPos &&
    typeof document !== "undefined" &&
    createPortal(menu, document.body);

  return (
    <div
      ref={rootRef}
      className={`forge-select ${open ? "forge-select--open" : ""} ${className}`.trim()}
    >
      <button
        ref={triggerRef}
        type="button"
        id={id}
        className="forge-select-trigger"
        disabled={disabled}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={listId}
        aria-label={ariaLabel ?? display}
        onClick={() => {
          if (!disabled) setOpen((o) => !o);
        }}
      >
        <span className="forge-select-value">{display}</span>
        <span className="forge-select-chevron" aria-hidden>
          <svg
            width="12"
            height="12"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <polyline points="6 9 12 15 18 9" />
          </svg>
        </span>
      </button>
      {open && !usePortal && menu}
      {portaledMenuNode}
    </div>
  );
}
