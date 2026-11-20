import type { ConditionStatus, InboxTab, Lead } from "@followup/api-client-inmo24x7";
import { Badge, Button, Card, CardContent, Input, Pagination, cn } from "@followup/ui";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useEffect, useId, useState } from "react";

import { downloadLeadsCsv, fetchLeads } from "../../api/leads";
import { apiErrorMessage } from "../../lib/api-errors";
import { STATUS_LABELS, STATUS_TONES } from "../../lib/conditions";
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
  const conditionsId = useId();
  const [includeTest, setIncludeTest] = useState(true);
  const [conditions, setConditions] = useState<ConditionStatus | "">("");
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

  const filters = { tab, q: search, includeTest, page, conditions: conditions || undefined };
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
        <div role="tablist" aria-label="Consultas" className="flex gap-1 overflow-x-auto border-b">
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
                "-mb-px min-h-11 shrink-0 border-b-2 px-3 py-2 text-sm md:min-h-0",
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
          <label htmlFor={toggleId} className="flex min-h-11 items-center gap-2 text-sm md:min-h-0">
            <input
              id={toggleId}
              type="checkbox"
              className="size-4"
              checked={includeTest}
              onChange={(event) => {
                setIncludeTest(event.target.checked);
                setPage(1);
              }}
            />
            Mostrar pruebas del simulador
          </label>
          <label htmlFor={conditionsId} className="sr-only">
            Condiciones
          </label>
          <select
            id={conditionsId}
            value={conditions}
            onChange={(event) => {
              setConditions(event.target.value as ConditionStatus | "");
              setPage(1);
            }}
            className="h-11 rounded-md border bg-card px-2 text-sm md:h-9"
          >
            <option value="">Todas las condiciones</option>
            <option value="cumple">Cumple</option>
            <option value="no_cumple">No cumple</option>
            <option value="sin_datos">Sin datos</option>
          </select>
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
        <span className="flex flex-wrap gap-1">
          <LeadStatusBadge status={lead.status} />
          {lead.do_not_contact ? <Badge tone="danger">Pidió no ser contactado</Badge> : null}
          {lead.source === "web_button" ? <Badge tone="info">Web — botón</Badge> : null}
          {lead.conditions_status && lead.conditions_status !== "sin_datos" ? (
            <Badge tone={STATUS_TONES[lead.conditions_status]}>
              {STATUS_LABELS[lead.conditions_status]}
            </Badge>
          ) : null}
        </span>
      </button>
    </li>
  );
}
