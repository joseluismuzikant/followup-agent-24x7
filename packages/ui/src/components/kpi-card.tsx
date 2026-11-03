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
      className={cn("flex flex-col gap-1 rounded-lg border bg-card p-4", className)}
    >
      <h3 className="text-sm text-muted-foreground">{label}</h3>
      <p className="text-3xl font-semibold tabular-nums">{value}</p>
      {hint ? <p className="text-xs text-muted-foreground">{hint}</p> : null}
    </section>
  );
}

export { KpiCard };
