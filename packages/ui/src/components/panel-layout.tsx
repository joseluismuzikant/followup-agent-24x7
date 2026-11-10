import { useEffect, useId, useRef, useState } from "react";
import type * as React from "react";

import { MD_UP, useMediaQuery } from "../lib/use-media-query";
import { cn } from "../lib/utils";
import { BrandMark } from "./brand-mark";
import { useLinkComponent } from "./link-provider";
import { usePanelSession } from "./panel-session";

export interface PanelNavItem {
  label: string;
  href: string;
  active?: boolean;
}

interface PanelLayoutProps {
  productName: string;
  areaName: string;
  title: string;
  description?: string;
  navItems: PanelNavItem[];
  action?: React.ReactNode;
  subtitle?: React.ReactNode;
  children: React.ReactNode;
}

const FOCUSABLE = 'a[href], button:not([disabled]), input:not([disabled]), [tabindex="0"]';

/** The panel's frame. From `md` up, a sidebar; below it, a top bar whose menu button opens
 * the same navigation and session controls in a drawer (focus kept inside; Escape, the
 * backdrop or picking a page closes it). */
export function PanelLayout({
  productName,
  areaName,
  title,
  description,
  navItems,
  action,
  subtitle,
  children,
}: PanelLayoutProps) {
  const [menuOpen, setMenuOpen] = useState(false);
  // One frame or the other in the DOM (not both hidden with CSS): screen readers and tests
  // see one navigation, one brand.
  const desktop = useMediaQuery(MD_UP);

  return (
    <div className="min-h-screen md:grid md:grid-cols-[232px_1fr] lg:grid-cols-[264px_1fr]">
      <aside className="sidebar-gradient hidden flex-col gap-8 p-5 text-sidebar-foreground md:sticky md:top-0 md:flex md:h-screen lg:p-6">
        <Brand productName={productName} areaName={areaName} subtitle={subtitle} />
        <PanelNav items={navItems} />
        <SidebarFooter />
      </aside>

      {desktop ? null : (
        <MobileBar
          productName={productName}
          areaName={areaName}
          subtitle={subtitle}
          navItems={navItems}
          open={menuOpen}
          onOpenChange={setMenuOpen}
        />
      )}

      <div className="flex min-w-0 flex-col">
        <header className="flex flex-row flex-wrap items-center justify-between gap-3 border-b bg-card px-4 py-4 sm:px-6 lg:px-10 lg:py-6">
          <div className="min-w-0">
            <h1 className="text-xl font-semibold tracking-tight text-brand sm:text-2xl">
              {title}
            </h1>
            {description ? (
              <p className="mt-1 hidden text-sm text-muted-foreground sm:block">{description}</p>
            ) : null}
          </div>
          {action}
        </header>

        <main className="min-w-0 flex-1 px-4 py-5 sm:px-6 lg:px-10 lg:py-8">{children}</main>
      </div>
    </div>
  );
}

function Brand({
  productName,
  areaName,
  subtitle,
}: {
  productName: string;
  areaName: string;
  subtitle?: React.ReactNode;
}) {
  return (
    <div className="flex min-w-0 items-center gap-3">
      <BrandMark name={productName} />
      <div className="min-w-0">
        <p className="font-semibold leading-tight">{productName}</p>
        <p className="text-xs uppercase tracking-wider text-sidebar-muted">{areaName}</p>
        {subtitle ? (
          <p className="mt-0.5 truncate text-xs font-medium text-white/90">{subtitle}</p>
        ) : null}
      </div>
    </div>
  );
}

function PanelNav({ items, onNavigate }: { items: PanelNavItem[]; onNavigate?: () => void }) {
  const Link = useLinkComponent();
  return (
    <nav aria-label="Navegación principal" className="flex flex-col gap-1">
      {items.map((item) => (
        <Link
          key={item.label}
          href={item.href}
          aria-current={item.active ? "page" : undefined}
          onClick={onNavigate}
          className={cn(
            "relative flex min-h-11 items-center rounded-lg px-3 py-2 text-sm font-medium transition-colors md:min-h-0",
            item.active
              ? "bg-sidebar-active text-white before:absolute before:inset-y-2 before:left-0 before:w-1 before:rounded-full before:bg-[var(--highlight)]"
              : "text-sidebar-muted hover:bg-white/10 hover:text-white",
          )}
        >
          {item.label}
        </Link>
      ))}
    </nav>
  );
}

function SidebarFooter() {
  const session = usePanelSession();
  return (
    <div className="mt-auto flex flex-col gap-4">
      {session ? (
        <div className="flex flex-col items-stretch gap-3 border-t border-white/10 pt-4">
          <p className="min-w-0 truncate text-xs text-sidebar-muted" title={session.email}>
            {session.email}
          </p>
          <button
            type="button"
            onClick={session.onSignOut}
            className="min-h-11 shrink-0 rounded-lg border border-white/20 px-3 py-1.5 text-sm font-medium text-white transition-colors hover:bg-white/10 md:min-h-0"
          >
            Cerrar sesión
          </button>
        </div>
      ) : null}
      <p className="text-xs leading-relaxed text-sidebar-muted">
        Un agente que sigue cada conversación hasta el resultado.
      </p>
    </div>
  );
}

function MobileBar({
  productName,
  areaName,
  subtitle,
  navItems,
  open,
  onOpenChange,
}: {
  productName: string;
  areaName: string;
  subtitle?: React.ReactNode;
  navItems: PanelNavItem[];
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const drawerId = useId();
  const buttonRef = useRef<HTMLButtonElement>(null);
  const drawerRef = useRef<HTMLDivElement>(null);
  const current = navItems.find((item) => item.active)?.label;

  useEffect(() => {
    if (!open) {
      return;
    }
    const drawer = drawerRef.current;
    const opener = buttonRef.current;
    drawer?.querySelector<HTMLElement>(FOCUSABLE)?.focus();
    const overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") {
        onOpenChange(false);
        return;
      }
      if (event.key !== "Tab" || !drawer) {
        return;
      }
      // Keep Tab inside the drawer.
      const focusable = Array.from(drawer.querySelectorAll<HTMLElement>(FOCUSABLE));
      const first = focusable[0];
      const last = focusable.at(-1);
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last?.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first?.focus();
      }
    }
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = overflow;
      opener?.focus();
    };
  }, [open, onOpenChange]);

  return (
    <div className="sidebar-gradient sticky top-0 z-30 flex items-center justify-between gap-3 px-4 py-2.5 text-sidebar-foreground md:hidden">
      <div className="flex min-w-0 items-center gap-3">
        <BrandMark name={productName} className="size-9" />
        <div className="min-w-0">
          <p className="truncate text-sm font-semibold leading-tight">{productName}</p>
          <p className="truncate text-xs text-sidebar-muted">{subtitle ?? areaName}</p>
        </div>
      </div>
      <button
        ref={buttonRef}
        type="button"
        aria-label={open ? "Cerrar el menú" : "Abrir el menú"}
        aria-expanded={open}
        aria-controls={drawerId}
        onClick={() => onOpenChange(!open)}
        className="grid size-11 shrink-0 place-items-center rounded-lg border border-white/20 text-white transition-colors hover:bg-white/10"
      >
        <MenuIcon />
      </button>

      {open ? (
        <div className="fixed inset-0 z-40 flex md:hidden">
          <div
            aria-hidden="true"
            className="absolute inset-0 bg-black/50"
            onClick={() => onOpenChange(false)}
          />
          <div
            ref={drawerRef}
            id={drawerId}
            role="dialog"
            aria-modal="true"
            aria-label={current ? `Menú (estás en ${current})` : "Menú"}
            className="sidebar-gradient relative flex h-full w-[min(20rem,85vw)] flex-col gap-6 overflow-y-auto p-5 text-sidebar-foreground shadow-xl"
          >
            <div className="flex items-start justify-between gap-3">
              <Brand productName={productName} areaName={areaName} subtitle={subtitle} />
              <button
                type="button"
                aria-label="Cerrar el menú"
                onClick={() => onOpenChange(false)}
                className="grid size-11 shrink-0 place-items-center rounded-lg text-white hover:bg-white/10"
              >
                <span aria-hidden="true">✕</span>
              </button>
            </div>
            <PanelNav items={navItems} onNavigate={() => onOpenChange(false)} />
            <SidebarFooter />
          </div>
        </div>
      ) : null}
    </div>
  );
}

function MenuIcon() {
  return (
    <svg aria-hidden="true" viewBox="0 0 24 24" className="size-5" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
      <path d="M4 7h16M4 12h16M4 17h16" />
    </svg>
  );
}
