import { ApiRequestError } from "@followup/api-client-inmo24x7";
import type { SimulatorState } from "@followup/api-client-inmo24x7";
import { Button, ChatSimulator, KnownFactsPanel } from "@followup/ui";
import type { ChatMessage } from "@followup/ui";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import {
  fetchTenantSimulator,
  resetTenantSimulator,
  sendTenantSimulatorMessage,
} from "../api/simulator";
import { apiErrorMessage } from "../lib/api-errors";
import { panelLink } from "../lib/nav";

interface PendingMessage {
  text: string;
  failed: boolean;
  retryable: boolean;
}

/** "Probar su agente": the tenant's agent, in the admin's own thread. */
export function AdminSimulator({ tenantId }: { tenantId: string }) {
  const queryKey = ["admin-simulator", tenantId];
  const queryClient = useQueryClient();
  const simulatorQuery = useQuery({
    queryKey,
    queryFn: () => fetchTenantSimulator(tenantId),
  });
  const [pending, setPending] = useState<PendingMessage | null>(null);
  const [error, setError] = useState<string | null>(null);

  const send = useMutation({
    mutationFn: (text: string) => sendTenantSimulatorMessage(tenantId, text),
    onMutate: (text) => {
      setPending({ text, failed: false, retryable: false });
      setError(null);
    },
    onSuccess: async (reply, text) => {
      queryClient.setQueryData<SimulatorState>(queryKey, (current) =>
        current
          ? {
              ...current,
              messages: [
                ...current.messages,
                {
                  id: `sent-${Date.now()}`,
                  direction: "inbound",
                  author: "visitor",
                  text,
                  cards: null,
                  created_at: new Date().toISOString(),
                },
                ...reply.messages,
              ],
              known: reply.known,
            }
          : current,
      );
      setPending(null);
      await queryClient.invalidateQueries({ queryKey });
    },
    onError: (failure, text) => {
      const unavailable = failure instanceof ApiRequestError && failure.code === "agent_unavailable";
      setPending({ text, failed: true, retryable: unavailable });
      setError(apiErrorMessage(failure, "No pudimos enviar el mensaje. Probá de nuevo."));
    },
  });

  const reset = useMutation({
    mutationFn: () => resetTenantSimulator(tenantId),
    onSuccess: (state) => {
      queryClient.setQueryData(queryKey, state);
      setPending(null);
      setError(null);
    },
    onError: (failure) =>
      setError(apiErrorMessage(failure, "No pudimos reiniciar la conversación.")),
  });

  if (simulatorQuery.isPending) {
    return <p className="text-sm text-muted-foreground">Cargando el simulador…</p>;
  }
  if (simulatorQuery.isError) {
    return (
      <p className="text-sm text-destructive" role="alert">
        {apiErrorMessage(simulatorQuery.error, "No pudimos cargar el simulador de este negocio.")}
      </p>
    );
  }

  const state = simulatorQuery.data;
  const messages: ChatMessage[] = state.messages.map((message) => ({
    id: message.id,
    author: message.author,
    text: message.text,
    cards: message.cards,
    traceUrl: message.trace_url,
  }));
  if (pending) {
    messages.push({
      id: "pending",
      author: "visitor",
      text: pending.text,
      status: pending.failed ? "failed" : "sending",
    });
  }

  return (
    <div className="flex flex-col gap-4">
      {state.config_outdated ? (
        <p className="rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-sm" role="status">
          El negocio cambió su agente. Reiniciá la conversación para probar los cambios.
        </p>
      ) : null}
      {state.uses_sample_properties ? (
        <p className="text-sm text-muted-foreground">
          Este negocio todavía usa propiedades de ejemplo.
        </p>
      ) : null}
      <div className="grid gap-4 md:grid-cols-[minmax(0,1fr)_16rem]">
        <ChatSimulator
          agentName={state.agent_name}
          businessName={state.business_name}
          messages={messages}
          typing={send.isPending}
          resetting={reset.isPending}
          onSend={(text) => send.mutate(text)}
          onReset={() => reset.mutate()}
          resolveLink={panelLink}
          notice={
            error ? (
              <div className="flex flex-wrap items-center gap-2">
                <p className="text-sm text-destructive" role="alert">
                  {error}
                </p>
                {pending?.retryable ? (
                  <Button size="sm" variant="outline" onClick={() => send.mutate(pending.text)}>
                    Reintentar
                  </Button>
                ) : null}
              </div>
            ) : null
          }
        />
        <KnownFactsPanel facts={state.known} />
      </div>
    </div>
  );
}
