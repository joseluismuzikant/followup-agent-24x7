import type * as React from "react";

import { cn } from "../lib/utils";

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
  return (
    <div className="min-h-screen lg:grid lg:grid-cols-[260px_1fr]">
      <aside className="flex flex-col gap-8 border-b bg-card p-6 lg:min-h-screen lg:border-b-0 lg:border-r">
        <div className="flex items-center gap-3">
          <div className="grid size-10 place-items-center rounded-xl bg-primary font-semibold text-primary-foreground">
            {productName.slice(0, 1).toUpperCase()}
          </div>
          <div>
            <p className="font-semibold leading-tight">{productName}</p>
            <p className="text-xs uppercase tracking-wider text-muted-foreground">
              {areaName}
            </p>
            {subtitle ? (
              <p className="mt-0.5 text-xs font-medium text-foreground">{subtitle}</p>
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
                "rounded-md px-3 py-2 text-sm font-medium transition-colors",
                item.active
                  ? "bg-primary/10 text-primary"
                  : "text-muted-foreground hover:bg-muted hover:text-foreground",
              )}
            >
              {item.label}
            </a>
          ))}
        </nav>

        <p className="mt-auto hidden text-xs leading-relaxed text-muted-foreground lg:block">
          Un agente que sigue cada conversación hasta el resultado.
        </p>
      </aside>

      <div className="flex min-w-0 flex-col">
        <header className="flex flex-col gap-4 border-b bg-background/80 px-6 py-6 sm:flex-row sm:items-center sm:justify-between lg:px-10">
          <div>
            <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
            {description ? (
              <p className="mt-1 text-sm text-muted-foreground">{description}</p>
            ) : null}
          </div>
          {action}
        </header>

        <main className="flex-1 px-6 py-8 lg:px-10">{children}</main>
      </div>
    </div>
  );
}
