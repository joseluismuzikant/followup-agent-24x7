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
}

function KnownFactsPanel({
  facts,
  title = "Lo que el agente ya sabe",
  className,
}: KnownFactsPanelProps) {
  return (
    <section
      data-slot="known-facts-panel"
      aria-label={title}
      className={cn("flex flex-col gap-3 rounded-lg border bg-card p-4", className)}
    >
      <h3 className="text-sm font-semibold">{title}</h3>
      <dl className="flex flex-col gap-2">
        {facts.map((fact) => (
          <div key={fact.key} className="flex flex-col">
            <dt className="text-xs text-muted-foreground">{fact.label}</dt>
            <dd
              className={cn("text-sm", fact.value === null && "italic text-muted-foreground")}
            >
              {fact.value ?? "Pendiente"}
            </dd>
          </div>
        ))}
      </dl>
    </section>
  );
}

export { KnownFactsPanel, type KnownFact };
