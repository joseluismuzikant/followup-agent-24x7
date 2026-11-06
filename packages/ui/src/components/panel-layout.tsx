import type * as React from "react";

import { cn } from "../lib/utils";
import { BrandMark } from "./brand-mark";
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
  const session = usePanelSession();
  return (
    <div className="min-h-screen lg:grid lg:grid-cols-[264px_1fr]">
      <aside className="sidebar-gradient flex flex-col gap-8 p-5 text-sidebar-foreground lg:sticky lg:top-0 lg:h-screen lg:p-6">
        <div className="flex items-center gap-3">
          <BrandMark name={productName} />
          <div className="min-w-0">
            <p className="font-semibold leading-tight">{productName}</p>
            <p className="text-xs uppercase tracking-wider text-sidebar-muted">{areaName}</p>
            {subtitle ? (
              <p className="mt-0.5 truncate text-xs font-medium text-white/90">{subtitle}</p>
            ) : null}
          </div>
        </div>

        <nav aria-label="Navegación principal" className="flex flex-wrap gap-1 lg:flex-col">
          {navItems.map((item) => (
            <a
              key={item.label}
              href={item.href}
              aria-current={item.active ? "page" : undefined}
              className={cn(
                "relative rounded-lg px-3 py-2 text-sm font-medium transition-colors",
                item.active
                  ? "bg-sidebar-active text-white before:absolute before:inset-y-2 before:left-0 before:w-1 before:rounded-full before:bg-[var(--highlight)]"
                  : "text-sidebar-muted hover:bg-white/10 hover:text-white",
              )}
            >
              {item.label}
            </a>
          ))}
        </nav>

        <div className="flex flex-col gap-4 lg:mt-auto">
          {session ? (
            <div className="flex items-center justify-between gap-3 border-t border-white/10 pt-4 lg:flex-col lg:items-stretch">
              <p className="min-w-0 truncate text-xs text-sidebar-muted" title={session.email}>
                {session.email}
              </p>
              <button
                type="button"
                onClick={session.onSignOut}
                className="shrink-0 rounded-lg border border-white/20 px-3 py-1.5 text-sm font-medium text-white transition-colors hover:bg-white/10"
              >
                Cerrar sesión
              </button>
            </div>
          ) : null}
          <p className="hidden text-xs leading-relaxed text-sidebar-muted lg:block">
            Un agente que sigue cada conversación hasta el resultado.
          </p>
        </div>
      </aside>

      <div className="flex min-w-0 flex-col">
        <header className="flex flex-col gap-4 border-b bg-card px-4 py-5 sm:flex-row sm:items-center sm:justify-between sm:px-6 lg:px-10 lg:py-6">
          <div>
            <h1 className="text-2xl font-semibold tracking-tight text-brand">{title}</h1>
            {description ? (
              <p className="mt-1 text-sm text-muted-foreground">{description}</p>
            ) : null}
          </div>
          {action}
        </header>

        <main className="flex-1 px-4 py-6 sm:px-6 lg:px-10 lg:py-8">{children}</main>
      </div>
    </div>
  );
}
