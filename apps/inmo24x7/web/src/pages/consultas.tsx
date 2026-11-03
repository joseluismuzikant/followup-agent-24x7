import type { Lead, LeadDetail } from "@followup/api-client-inmo24x7";
import {
  Badge,
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  KnownFactsPanel,
  Pagination,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
  cn,
} from "@followup/ui";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useId, useState } from "react";
import { useSearchParams } from "react-router";

import { fetchLead, fetchLeads } from "../api/leads";
import { apiErrorMessage } from "../lib/api-errors";
import {
  channelLabel,
  contentTypeLabels,
  deliveryLabels,
  formatDateTime,
  leadStatusLabels,
  leadStatusTones,
  timeAgo,
} from "../lib/leads";

/** Consultas, minimal until the Day 6 inbox: list, statuses and a read-only detail. */
export function ConsultasPage() {
  const toggleId = useId();
  const [includeTest, setIncludeTest] = useState(true);
  const [page, setPage] = useState(1);
  // The new-lead email links to /consultas?lead=<id>.
  const [searchParams] = useSearchParams();
  const [selected, setSelected] = useState<string | null>(searchParams.get("lead"));
  const listQuery = useQuery({
    queryKey: ["leads", { includeTest, page }],
    queryFn: () => fetchLeads({ includeTest, page }),
    placeholderData: keepPreviousData,
  });
  const list = listQuery.data;

  return (
    <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_24rem]">
      <Card>
        <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-3">
          <CardTitle>Consultas</CardTitle>
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
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          {listQuery.isError ? (
            <p className="text-sm text-destructive" role="alert">
              {apiErrorMessage(listQuery.error, "No pudimos cargar las consultas.")}
            </p>
          ) : null}
          {list && list.total === 0 ? (
            <p className="text-sm text-muted-foreground">
              Todavía no hay consultas. Probá tu agente y las vas a ver acá.
            </p>
          ) : null}
          {list && list.total > 0 ? (
            <>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Nombre o contacto</TableHead>
                    <TableHead>Qué busca</TableHead>
                    <TableHead>Estado</TableHead>
                    <TableHead>Última actividad</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {list.items.map((lead) => (
                    <LeadRow
                      key={lead.id}
                      lead={lead}
                      selected={lead.id === selected}
                      onSelect={() => setSelected(lead.id)}
                    />
                  ))}
                </TableBody>
              </Table>
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
      {selected ? <LeadPanel leadId={selected} /> : null}
    </div>
  );
}

export function LeadStatusBadge({ status }: { status: Lead["status"] }) {
  return <Badge tone={leadStatusTones[status]}>{leadStatusLabels[status]}</Badge>;
}

function leadName(lead: Lead): string {
  return lead.visitor_name ?? lead.contact ?? "Sin nombre todavía";
}

function LeadRow({
  lead,
  selected,
  onSelect,
}: {
  lead: Lead;
  selected: boolean;
  onSelect: () => void;
}) {
  return (
    <TableRow className={cn(selected && "bg-muted")}>
      <TableCell>
        <div className="flex flex-col">
        <button
          type="button"
          className="flex items-center gap-2 text-left font-medium underline-offset-4 hover:underline"
          onClick={onSelect}
        >
          {leadName(lead)}
          {lead.is_test ? <Badge>Prueba</Badge> : null}
        </button>
        <span className="text-xs text-muted-foreground">{channelLabel(lead.channel)}</span>
        </div>
      </TableCell>
      <TableCell className="text-muted-foreground">{lead.looking_for || "—"}</TableCell>
      <TableCell>
        <LeadStatusBadge status={lead.status} />
      </TableCell>
      <TableCell className="whitespace-nowrap text-muted-foreground">
        {timeAgo(lead.last_activity_at)}
      </TableCell>
    </TableRow>
  );
}

function LeadPanel({ leadId }: { leadId: string }) {
  const leadQuery = useQuery({ queryKey: ["lead", leadId], queryFn: () => fetchLead(leadId) });
  if (leadQuery.isPending) {
    return <p className="text-sm text-muted-foreground">Cargando la consulta…</p>;
  }
  if (leadQuery.isError) {
    return (
      <p className="text-sm text-destructive" role="alert">
        {apiErrorMessage(leadQuery.error, "No pudimos cargar la consulta.")}
      </p>
    );
  }
  return <LeadDetailView lead={leadQuery.data} />;
}

export function LeadDetailView({ lead }: { lead: LeadDetail }) {
  const visit = lead.visits.at(-1);
  return (
    <aside aria-label="Detalle de la consulta" className="flex flex-col gap-4">
      <Card>
        <CardHeader>
          <CardTitle className="flex flex-wrap items-center gap-2 text-base">
            {leadName(lead)}
            <LeadStatusBadge status={lead.status} />
            {lead.is_test ? <Badge>Prueba</Badge> : null}
          </CardTitle>
          <p className="text-sm text-muted-foreground">
            {lead.contact ?? "Sin contacto todavía"} · {channelLabel(lead.channel)}
          </p>
        </CardHeader>
      </Card>

      {visit ? (
        <section
          aria-label="Visita propuesta"
          className="flex flex-col gap-1 rounded-lg border bg-card p-4 text-sm"
        >
          <h3 className="font-semibold">Visita propuesta</h3>
          <p>{visit.property_label}</p>
          <p className="capitalize">{formatDateTime(visit.starts_at)}</p>
          <p className="text-muted-foreground">
            {visit.status === "proposed" ? "Esperando la confirmación del equipo" : "Confirmada"}
          </p>
        </section>
      ) : null}

      <KnownFactsPanel title="Lo que contó" facts={lead.answers} />

      <section aria-label="Conversación" className="flex flex-col gap-2 rounded-lg border bg-card p-4">
        <h3 className="text-sm font-semibold">Conversación</h3>
        {lead.transcript.map((message) => (
          <div
            key={message.id}
            className={cn(
              "flex max-w-[85%] flex-col gap-0.5",
              message.author === "visitor" && "self-end items-end",
              (message.author === "agent" || message.author === "human") && "self-start",
              message.author === "system" && "self-center",
            )}
          >
            <p
              className={cn(
                "whitespace-pre-line rounded-2xl px-3 py-2 text-sm",
                message.author === "visitor" && "bg-primary text-primary-foreground",
                (message.author === "agent" || message.author === "human") && "bg-muted",
                message.author === "system" &&
                  "rounded-full border px-3 py-1 text-xs text-muted-foreground",
              )}
            >
              {message.content_type !== "text" ? (
                <span className="italic">
                  {contentTypeLabels[message.content_type] ?? "Archivo"}
                  {message.text ? `: ${message.text}` : ""}
                </span>
              ) : (
                message.text
              )}
            </p>
            {message.delivery_status ? (
              <span
                className={cn(
                  "text-[11px] text-muted-foreground",
                  message.delivery_status === "failed" && "text-destructive",
                )}
              >
                {deliveryLabels[message.delivery_status]}
              </span>
            ) : null}
          </div>
        ))}
      </section>
    </aside>
  );
}
