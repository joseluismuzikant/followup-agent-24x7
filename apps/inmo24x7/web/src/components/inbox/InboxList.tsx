import type { InboxTab, Lead } from "@followup/api-client-inmo24x7";
import { Badge, Button, Card, CardContent, Input, Pagination, cn } from "@followup/ui";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useEffect, useId, useState } from "react";

import { downloadLeadsCsv, fetchLeads } from "../../api/leads";
import { apiErrorMessage } from "../../lib/api-errors";
import { age, leadName } from "../../lib/leads";
import { LeadStatusBadge } from "./LeadStatusBadge";

export const LIST_REFRESH_MS = 15_000;

const emptyStates: Record<InboxTab, string> = {
  attention: "No hay consultas esperando a tu equipo. Cuando el agente derive una, aparece acá.",
  visits: "Todavía no hay visitas propuestas ni confirmadas.",
  all: "Todavía no hay consultas. Probá tu agente y las vas a ver acá.",
};

interface InboxListProps {
  tab: InboxTab;
  search: string;
  selected: string | null;
  onTabChange: (tab: InboxTab) => void;
  onSearchChange: (search: string) => void;
  onSelect: (id: string) => void;
}

export function InboxList({
  tab,
  search,
  selected,
  onTabChange,
  onSearchChange,
  onSelect,
}: InboxListProps) {
  const toggleId = useId();
  const [includeTest, setIncludeTest] = useState(true);
  const [page, setPage] = useState(1);
  const [draft, setDraft] = useState(search);
  const [exportError, setExportError] = useState<string | null>(null);

  // The URL follows the search box after a short pause.
  useEffect(() => {
    if (draft === search) {
      return;
    }
    const timer = setTimeout(() => {
      onSearchChange(draft.trim());
      setPage(1);
    }, 300);
    return () => clearTimeout(timer);
  }, [draft, search, onSearchChange]);

  const filters = { tab, q: search, includeTest, page };
  const listQuery = useQuery({
    queryKey: ["leads", filters],
    queryFn: () => fetchLeads(filters),
    placeholderData: keepPreviousData,
    // Paused while the browser tab is hidden (TanStack's default).
    refetchInterval: LIST_REFRESH_MS,
  });
  const list = listQuery.data;
  const counts = list?.counts;
  const tabs: { value: InboxTab; label: string }[] = [
    { value: "attention", label: counts ? `Para atender · ${counts.attention}` : "Para atender" },
    { value: "visits", label: "Visitas" },
    { value: "all", label: "Todas" },
  ];

  async function exportCsv() {
    setExportError(null);
    try {
      await downloadLeadsCsv({ tab, q: search, includeTest });
    } catch {
      setExportError("No pudimos generar el CSV. Probá de nuevo.");
    }
  }

  return (
    <Card className="self-start">
      <CardContent className="flex flex-col gap-3 pt-4">
        <div role="tablist" aria-label="Consultas" className="flex gap-1 border-b">
          {tabs.map((item) => (
            <button
              key={item.value}
              type="button"
              role="tab"
              aria-selected={item.value === tab}
              onClick={() => {
                onTabChange(item.value);
                setPage(1);
              }}
              className={cn(
                "-mb-px border-b-2 px-3 py-2 text-sm",
                item.value === tab
                  ? "border-primary font-semibold"
                  : "border-transparent text-muted-foreground",
              )}
            >
              {item.label}
            </button>
          ))}
        </div>
        <Input
          type="search"
          aria-label="Buscar por nombre, zona o teléfono"
          placeholder="Buscar por nombre, zona o teléfono"
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
        />
        <div className="flex flex-wrap items-center justify-between gap-2">
          <label htmlFor={toggleId} className="flex items-center gap-2 text-sm">
            <input
              id={toggleId}
              type="checkbox"
              checked={includeTest}
              onChange={(event) => {
                setIncludeTest(event.target.checked);
                setPage(1);
              }}
            />
            Mostrar pruebas del simulador
          </label>
          <Button variant="outline" size="sm" onClick={() => void exportCsv()}>
            Exportar CSV
          </Button>
        </div>
        {exportError ? (
          <p className="text-sm text-destructive" role="alert">
            {exportError}
          </p>
        ) : null}
        {listQuery.isError ? (
          <p className="text-sm text-destructive" role="alert">
            {apiErrorMessage(listQuery.error, "No pudimos cargar las consultas.")}
          </p>
        ) : null}
        {list && list.total === 0 ? (
          <p className="py-6 text-center text-sm text-muted-foreground">
            {search ? "Ninguna consulta coincide con la búsqueda." : emptyStates[tab]}
          </p>
        ) : null}
        {list && list.total > 0 ? (
          <>
            <ul aria-label="Lista de consultas" className="flex flex-col divide-y">
              {list.items.map((lead) => (
                <LeadItem
                  key={lead.id}
                  lead={lead}
                  selected={lead.id === selected}
                  onSelect={() => onSelect(lead.id)}
                />
              ))}
            </ul>
            <Pagination
              page={list.page}
              pageSize={list.page_size}
              total={list.total}
              onPageChange={setPage}
            />
          </>
        ) : null}
      </CardContent>
    </Card>
  );
}

function LeadItem({
  lead,
  selected,
  onSelect,
}: {
  lead: Lead;
  selected: boolean;
  onSelect: () => void;
}) {
  return (
    <li>
      <button
        type="button"
        aria-current={selected ? "true" : undefined}
        onClick={onSelect}
        className={cn(
          "flex w-full flex-col gap-1 rounded-md px-2 py-3 text-left hover:bg-muted",
          selected && "bg-muted",
        )}
      >
        <span className="flex items-center justify-between gap-2">
          <span className="flex min-w-0 items-center gap-2 font-medium">
            <span className="truncate">{leadName(lead)}</span>
            {lead.is_test ? <Badge>Prueba</Badge> : null}
          </span>
          <span className="shrink-0 text-xs text-muted-foreground">
            {age(lead.last_activity_at)}
          </span>
        </span>
        <span className="truncate text-sm text-muted-foreground">
          {lead.looking_for || "Todavía no contó qué busca"}
        </span>
        <span>
          <LeadStatusBadge status={lead.status} />
        </span>
      </button>
    </li>
  );
}
