import type * as React from "react";

import { cn } from "../lib/utils";

interface KpiCardProps {
  label: string;
  /** Already formatted ("12", "6 s"); "—" when there is no data. */
  value: React.ReactNode;
  /** One short line under the value ("3 fuera de horario"). */
  hint?: React.ReactNode;
  className?: string;
}

/** One number of a dashboard (Inicio KPIs). */
function KpiCard({ label, value, hint, className }: KpiCardProps) {
  return (
    <section
      data-slot="kpi-card"
      aria-label={label}
      className={cn(
        "flex min-w-0 flex-col gap-1 rounded-2xl border bg-card p-4 shadow-[0_8px_24px_-14px_rgba(30,58,138,0.18)] sm:p-5",
        className,
      )}
    >
      <h3 className="text-sm text-muted-foreground">{label}</h3>
      <p className="text-2xl font-semibold tabular-nums text-brand sm:text-3xl">{value}</p>
      {hint ? <p className="text-xs text-muted-foreground">{hint}</p> : null}
    </section>
  );
}

export { KpiCard };
