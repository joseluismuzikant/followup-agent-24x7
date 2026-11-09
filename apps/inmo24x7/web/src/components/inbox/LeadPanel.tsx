import type { LeadDetail, LeadVisit, SimulatorMessage } from "@followup/api-client-inmo24x7";
import {
  Badge,
  Button,
  ChatTranscript,
  Dialog,
  FormField,
  Input,
  cn,
  KnownFactsPanel,
  LG_UP,
  type TranscriptMessage,
  useMediaQuery,
} from "@followup/ui";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useId, useState } from "react";

import {
  cancelVisit,
  confirmVisit,
  fetchLead,
  releaseLead,
  sendTeamMessage,
  takeOverLead,
} from "../../api/leads";
import { fetchMe } from "../../api/me";
import { apiErrorMessage } from "../../lib/api-errors";
import {
  channelLabel,
  contentTypeLabels,
  deliveryLabels,
  formatDateTime,
  formatTime,
  fromLocalInput,
  leadName,
  toLocalInput,
} from "../../lib/leads";
import { LeadStatusBadge } from "./LeadStatusBadge";

export const DETAIL_REFRESH_MS = 5_000;

function transcriptMessage(message: SimulatorMessage): TranscriptMessage {
  const media = message.content_type !== "text";
  return {
    id: message.id,
    author: message.author,
    text: media ? (
      <span className="italic">
        {contentTypeLabels[message.content_type] ?? "Archivo"}
        {message.text ? `: ${message.text}` : ""}
      </span>
    ) : (
      message.text
    ),
    authorName: message.author_name,
    footer: message.delivery_status ? deliveryLabels[message.delivery_status] : null,
    failed: message.delivery_status === "failed",
  };
}

/** The selected lead: refreshed every 5 s while the browser tab is visible. */
export function LeadPanel({ leadId, canAct }: { leadId: string; canAct: boolean }) {
  const queryClient = useQueryClient();
  const queryKey = ["lead", leadId];
  const leadQuery = useQuery({
    queryKey,
    queryFn: () => fetchLead(leadId),
    refetchInterval: DETAIL_REFRESH_MS,
  });
  const meQuery = useQuery({ queryKey: ["me"], queryFn: fetchMe });
  // Below `lg` the panel is the whole screen: facts fold up, the reply box sticks to the
  // bottom.
  const wide = useMediaQuery(LG_UP);
  const [error, setError] = useState<string | null>(null);
  const [dialog, setDialog] = useState<"confirm" | "cancel" | "takeover" | null>(null);

  function settled(detail?: LeadDetail) {
    if (detail) {
      queryClient.setQueryData(queryKey, detail);
    }
    setError(null);
    setDialog(null);
    void queryClient.invalidateQueries({ queryKey: ["leads"] });
  }
  function failed(failure: unknown) {
    setError(apiErrorMessage(failure, "No pudimos hacerlo. Probá de nuevo."));
    void queryClient.invalidateQueries({ queryKey });
  }

  const takeOver = useMutation({
    mutationFn: () => takeOverLead(leadId),
    onSuccess: settled,
    onError: failed,
  });
  const release = useMutation({
    mutationFn: () => releaseLead(leadId),
    onSuccess: settled,
    onError: failed,
  });
  const confirm = useMutation({
    mutationFn: ({ visit, startsAt }: { visit: string; startsAt?: string }) =>
      confirmVisit(leadId, visit, startsAt),
    onSuccess: settled,
    onError: failed,
  });
  const cancel = useMutation({
    mutationFn: ({ visit, message }: { visit: string; message?: string }) =>
      cancelVisit(leadId, visit, message),
    onSuccess: settled,
    onError: failed,
  });

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
  const lead = leadQuery.data;
  const myId = meQuery.data?.profile.id;
  const control = lead.control;
  const mine = control.mode === "human" && control.by?.id === myId;
  const visit = currentVisit(lead.visits);
  const busy = takeOver.isPending || release.isPending || confirm.isPending || cancel.isPending;

  function askTakeOver() {
    if (control.mode === "human" && !mine) {
      setDialog("takeover");
    } else {
      takeOver.mutate();
    }
  }

  return (
    <aside aria-label="Detalle de la consulta" className="flex min-w-0 flex-col gap-4">
      <header className="flex flex-wrap items-start justify-between gap-3 rounded-lg border bg-card p-4">
        <div className="flex min-w-0 flex-col gap-1">
          <h2 className="flex flex-wrap items-center gap-2 text-lg font-semibold">
            {leadName(lead)}
            <LeadStatusBadge status={lead.status} />
            {lead.is_test ? <Badge>Prueba</Badge> : null}
          </h2>
          <p className="text-sm text-muted-foreground">
            {lead.contact ?? "Sin contacto todavía"} ·{" "}
            {lead.channel === "whatsapp" ? "por WhatsApp" : "simulador"}
          </p>
          {control.mode === "human" ? (
            <p className="text-sm">
              {mine ? "Estás atendiendo esta conversación." : `${control.by?.name ?? "Alguien del equipo"} está atendiendo esta conversación.`}
            </p>
          ) : null}
        </div>
        {canAct ? (
          <div className="flex flex-wrap gap-2">
            {mine ? (
              <Button variant="outline" disabled={busy} onClick={() => release.mutate()}>
                Devolver al agente
              </Button>
            ) : (
              <Button variant="outline" disabled={busy} onClick={askTakeOver}>
                Tomar la conversación
              </Button>
            )}
            {visit?.status === "proposed" ? (
              <Button disabled={busy} onClick={() => setDialog("confirm")}>
                Confirmar visita
              </Button>
            ) : null}
          </div>
        ) : null}
      </header>

      {error ? (
        <p className="text-sm text-destructive" role="alert">
          {error}
        </p>
      ) : null}

      {visit ? (
        <VisitCard
          visit={visit}
          canAct={canAct}
          busy={busy}
          onCancel={() => setDialog("cancel")}
        />
      ) : null}

      <KnownFactsPanel title="Lo que contó" facts={lead.answers} collapsible={!wide} />

      <section aria-label="Conversación" className="flex flex-col gap-3 rounded-lg border bg-card p-4">
        <h3 className="text-sm font-semibold">Conversación</h3>
        <ChatTranscript messages={lead.transcript.map(transcriptMessage)} />
        {canAct ? (
          <Composer
            lead={lead}
            mine={mine}
            sticky={!wide}
            busy={busy}
            onTakeOver={askTakeOver}
            onSent={() => void leadQuery.refetch()}
          />
        ) : null}
      </section>

      {visit ? (
        <ConfirmVisitDialog
          open={dialog === "confirm"}
          visit={visit}
          saving={confirm.isPending}
          onClose={() => setDialog(null)}
          onConfirm={(startsAt) => confirm.mutate({ visit: visit.id, startsAt })}
        />
      ) : null}
      {visit ? (
        <CancelVisitDialog
          open={dialog === "cancel"}
          saving={cancel.isPending}
          windowOpen={lead.service_window?.open ?? true}
          onClose={() => setDialog(null)}
          onCancel={(message) => cancel.mutate({ visit: visit.id, message })}
        />
      ) : null}
      <Dialog open={dialog === "takeover"} title="Tomar la conversación" onClose={() => setDialog(null)}>
        <p className="text-sm">
          {control.by?.name ?? "Alguien del equipo"} está atendiendo esta consulta. ¿Querés
          tomarla vos?
        </p>
        <div className="mt-4 flex justify-end gap-2">
          <Button variant="outline" onClick={() => setDialog(null)}>
            No
          </Button>
          <Button disabled={busy} onClick={() => takeOver.mutate()}>
            Tomarla
          </Button>
        </div>
      </Dialog>
    </aside>
  );
}

/** The visit to act on: the proposed or confirmed one, else the latest. */
function currentVisit(visits: readonly LeadVisit[]): LeadVisit | undefined {
  const active = visits.filter((visit) => visit.status !== "cancelled");
  return active.at(-1) ?? visits.at(-1);
}

function VisitCard({
  visit,
  canAct,
  busy,
  onCancel,
}: {
  visit: LeadVisit;
  canAct: boolean;
  busy: boolean;
  onCancel: () => void;
}) {
  const address = visit.property_label.split(" · ").at(-1);
  const titles = {
    proposed: "Visita propuesta",
    confirmed: "Visita confirmada",
    cancelled: "Visita cancelada",
  };
  return (
    <section
      aria-label={titles[visit.status]}
      className="flex flex-wrap items-center justify-between gap-3 rounded-lg border bg-card p-4 text-sm"
    >
      <div className="flex flex-col gap-1">
        <p>
          <span className="font-semibold">{titles[visit.status]}</span> · {address} ·{" "}
          <span className="capitalize">{formatDateTime(visit.starts_at)}</span>
        </p>
        <p className="text-muted-foreground">
          {visit.status === "proposed"
            ? "Espera tu confirmación"
            : visit.status === "confirmed"
              ? "Le avisamos a la persona"
              : "El equipo la canceló"}
        </p>
      </div>
      {canAct && visit.status !== "cancelled" ? (
        <Button variant="ghost" size="sm" disabled={busy} onClick={onCancel}>
          Cancelar visita
        </Button>
      ) : null}
    </section>
  );
}

function ConfirmVisitDialog({
  open,
  visit,
  saving,
  onClose,
  onConfirm,
}: {
  open: boolean;
  visit: LeadVisit;
  saving: boolean;
  onClose: () => void;
  onConfirm: (startsAt?: string) => void;
}) {
  const inputId = useId();
  const proposed = toLocalInput(visit.starts_at);
  const [value, setValue] = useState(proposed);
  return (
    <Dialog open={open} title="Confirmar visita" onClose={onClose}>
      <form
        className="flex flex-col gap-4"
        onSubmit={(event) => {
          event.preventDefault();
          onConfirm(value && value !== proposed ? fromLocalInput(value) : undefined);
        }}
      >
        <p className="text-sm">
          {visit.property_label}. Le mandamos la confirmación a la persona.
        </p>
        <FormField label="Día y horario" htmlFor={inputId} hint="Podés cambiarlo si acordaron otro.">
          <Input
            id={inputId}
            type="datetime-local"
            value={value}
            onChange={(event) => setValue(event.target.value)}
          />
        </FormField>
        <div className="flex justify-end gap-2">
          <Button type="button" variant="outline" onClick={onClose}>
            Volver
          </Button>
          <Button type="submit" disabled={saving}>
            {saving ? "Confirmando…" : "Confirmar visita"}
          </Button>
        </div>
      </form>
    </Dialog>
  );
}

function CancelVisitDialog({
  open,
  saving,
  windowOpen,
  onClose,
  onCancel,
}: {
  open: boolean;
  saving: boolean;
  windowOpen: boolean;
  onClose: () => void;
  onCancel: (message?: string) => void;
}) {
  const inputId = useId();
  const [message, setMessage] = useState("");
  return (
    <Dialog open={open} title="Cancelar visita" onClose={onClose}>
      <form
        className="flex flex-col gap-4"
        onSubmit={(event) => {
          event.preventDefault();
          onCancel(message.trim() || undefined);
        }}
      >
        <FormField
          label="Mensaje para la persona (opcional)"
          htmlFor={inputId}
          hint={
            windowOpen
              ? "Si lo dejás vacío, la visita se cancela sin avisarle."
              : "Pasaron más de 24 horas desde su último mensaje: solo podés cancelar sin mensaje."
          }
        >
          <textarea
            id={inputId}
            rows={3}
            maxLength={4096}
            disabled={!windowOpen}
            value={message}
            onChange={(event) => setMessage(event.target.value)}
            className="rounded-md border bg-background px-3 py-2 text-sm"
          />
        </FormField>
        <div className="flex justify-end gap-2">
          <Button type="button" variant="outline" onClick={onClose}>
            Volver
          </Button>
          <Button type="submit" variant="destructive" disabled={saving}>
            {saving ? "Cancelando…" : "Cancelar visita"}
          </Button>
        </div>
      </form>
    </Dialog>
  );
}

/** Enabled only for the person who took the conversation, inside WhatsApp's 24 hours. The
 * draft is local state: refreshes of the transcript never clear it. */
function Composer({
  lead,
  mine,
  sticky,
  busy,
  onTakeOver,
  onSent,
}: {
  lead: LeadDetail;
  mine: boolean;
  /** Phones: pinned to the bottom of the screen, with "Responder yo" when it is not yours. */
  sticky: boolean;
  busy: boolean;
  onTakeOver: () => void;
  onSent: () => void;
}) {
  const [draft, setDraft] = useState("");
  const [error, setError] = useState<string | null>(null);
  const send = useMutation({
    mutationFn: (text: string) => sendTeamMessage(lead.id, text),
    onSuccess: () => {
      setDraft("");
      setError(null);
      onSent();
    },
    onError: (failure) =>
      setError(apiErrorMessage(failure, "No pudimos enviar el mensaje. Probá de nuevo.")),
  });
  const window = lead.service_window;
  const closed = window !== null && window !== undefined && !window.open;
  const enabled = mine && !closed;

  let hint: string;
  if (!mine) {
    hint = "Tomá la conversación para responder";
  } else if (closed) {
    hint =
      "Pasaron más de 24 horas desde el último mensaje: WhatsApp solo permite responder con una plantilla. Podés confirmar la visita igual.";
  } else if (window?.expires_at) {
    hint = `Podés responder hasta las ${formatTime(window.expires_at)}`;
  } else {
    hint = `Respondés ${channelLabel(lead.channel)}`;
  }

  if (sticky && !mine) {
    return (
      <div className="sticky bottom-0 -mx-4 -mb-4 flex flex-col gap-2 rounded-b-lg border-t bg-card px-4 py-3 shadow-[0_-6px_16px_rgba(15,23,42,0.06)]">
        <Button disabled={busy} onClick={onTakeOver}>
          Responder yo
        </Button>
        <p className="text-center text-xs text-muted-foreground">
          El agente deja de responder mientras atendés vos.
        </p>
      </div>
    );
  }

  return (
    <form
      className={cn(
        "flex flex-col gap-2 border-t pt-3",
        sticky &&
          "sticky bottom-0 -mx-4 -mb-4 rounded-b-lg bg-card px-4 pb-3 shadow-[0_-6px_16px_rgba(15,23,42,0.06)]",
      )}
      onSubmit={(event) => {
        event.preventDefault();
        const text = draft.trim();
        if (text && enabled) {
          send.mutate(text);
        }
      }}
    >
      <textarea
        aria-label="Respuesta"
        placeholder={enabled ? "Escribí tu respuesta…" : undefined}
        rows={2}
        maxLength={4096}
        disabled={!enabled}
        value={draft}
        onChange={(event) => setDraft(event.target.value)}
        className="rounded-md border bg-background px-3 py-2 text-sm disabled:opacity-60"
      />
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-xs text-muted-foreground">{hint}</p>
        <Button type="submit" size="sm" disabled={!enabled || !draft.trim() || send.isPending}>
          {send.isPending ? "Enviando…" : "Enviar"}
        </Button>
      </div>
      {error ? (
        <p className="text-sm text-destructive" role="alert">
          {error}
        </p>
      ) : null}
    </form>
  );
}
