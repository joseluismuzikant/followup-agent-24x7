import { useEffect, useId, useRef } from "react";
import type * as React from "react";

import { cn } from "../lib/utils";
import { Button } from "./button";

interface DialogProps {
  open: boolean;
  title: string;
  onClose: () => void;
  children: React.ReactNode;
  className?: string;
  /** "drawer": a full-height panel on the right (details next to a list). */
  variant?: "modal" | "drawer";
}

/** A modal panel. Escape and the close button call `onClose`; focus moves into it. */
function Dialog({ open, title, onClose, children, className, variant = "modal" }: DialogProps) {
  const titleId = useId();
  const panelRef = useRef<HTMLDivElement>(null);

  // The latest onClose, so a parent's new function each render never re-runs the effect
  // below (it would move focus out of the field being typed in).
  const onCloseRef = useRef(onClose);
  useEffect(() => {
    onCloseRef.current = onClose;
  });

  useEffect(() => {
    if (!open) {
      return;
    }
    panelRef.current?.focus();
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") {
        onCloseRef.current();
      }
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open]);

  if (!open) {
    return null;
  }
  return (
    <div
      className={cn(
        "fixed inset-0 z-50 flex bg-black/40",
        variant === "drawer"
          ? "justify-end"
          : "items-start justify-center overflow-y-auto px-4 py-10",
      )}
    >
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        tabIndex={-1}
        className={cn(
          variant === "drawer"
            ? "h-full w-full max-w-md overflow-y-auto border-l bg-card p-5 shadow-lg outline-none"
            : "w-full max-w-lg rounded-lg border bg-card p-5 shadow-lg outline-none",
          className,
        )}
      >
        <div className="mb-4 flex items-start justify-between gap-4">
          <h2 id={titleId} className="text-lg font-semibold">
            {title}
          </h2>
          <Button variant="ghost" size="sm" aria-label="Cerrar" onClick={onClose}>
            ✕
          </Button>
        </div>
        {children}
      </div>
    </div>
  );
}

export { Dialog };
