import { cn } from "../lib/utils";

interface KnownFact {
  key: string;
  label: string;
  /** Already formatted for display; null when the agent does not know it yet. */
  value: string | null;
}

interface KnownFactsPanelProps {
  facts: readonly KnownFact[];
  title?: string;
  className?: string;
  /** Folded behind its title (with how many are known) until tapped: for phones, where a
   * side column does not fit. */
  collapsible?: boolean;
}

function KnownFactsPanel({
  facts,
  title = "Lo que el agente ya sabe",
  className,
  collapsible = false,
}: KnownFactsPanelProps) {
  const list = (
    <dl className="flex flex-col gap-2">
      {facts.map((fact) => (
        <div key={fact.key} className="flex flex-col">
          <dt className="text-xs text-muted-foreground">{fact.label}</dt>
          <dd className={cn("text-sm", fact.value === null && "italic text-muted-foreground")}>
            {fact.value ?? "Pendiente"}
          </dd>
        </div>
      ))}
    </dl>
  );
  if (collapsible) {
    const known = facts.filter((fact) => fact.value !== null).length;
    return (
      <details
        data-slot="known-facts-panel"
        aria-label={title}
        className={cn("group rounded-lg border bg-card", className)}
      >
        <summary className="flex min-h-11 cursor-pointer list-none items-center justify-between gap-3 px-4 py-2 text-sm font-semibold [&::-webkit-details-marker]:hidden">
          <span>{title}</span>
          <span className="flex items-center gap-2 text-xs font-normal text-muted-foreground">
            {known} de {facts.length}
            <span aria-hidden="true" className="transition-transform group-open:rotate-180">
              ▾
            </span>
          </span>
        </summary>
        <div className="border-t px-4 py-3">{list}</div>
      </details>
    );
  }
  return (
    <section
      data-slot="known-facts-panel"
      aria-label={title}
      className={cn("flex flex-col gap-3 rounded-lg border bg-card p-4", className)}
    >
      <h3 className="text-sm font-semibold">{title}</h3>
      {list}
    </section>
  );
}

export { KnownFactsPanel, type KnownFact };
