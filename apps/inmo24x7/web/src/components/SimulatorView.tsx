import { ApiRequestError } from "@followup/api-client-inmo24x7";
import type { SimulatorMessage, SimulatorState } from "@followup/api-client-inmo24x7";
import { Button, ChatSimulator, KnownFactsPanel } from "@followup/ui";
import type { ChatMessage } from "@followup/ui";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router";

import { fetchSimulator, resetSimulator, sendSimulatorMessage } from "../api/simulator";
import { apiErrorMessage } from "../lib/api-errors";

const SIMULATOR_KEY = ["simulator"];

interface PendingMessage {
  text: string;
  failed: boolean;
  retryable: boolean;
}

function toChatMessage(message: SimulatorMessage): ChatMessage {
  return { id: message.id, author: message.author, text: message.text, cards: message.cards };
}

/** The Probalo chat: used by wizard step 3 and the /probar page. */
export function SimulatorView() {
  const queryClient = useQueryClient();
  const simulatorQuery = useQuery({ queryKey: SIMULATOR_KEY, queryFn: fetchSimulator });
  const [pending, setPending] = useState<PendingMessage | null>(null);
  const [error, setError] = useState<string | null>(null);

  const send = useMutation({
    mutationFn: sendSimulatorMessage,
    onMutate: (text) => {
      setPending({ text, failed: false, retryable: false });
      setError(null);
    },
    onSuccess: async (reply, text) => {
      queryClient.setQueryData<SimulatorState>(SIMULATOR_KEY, (current) =>
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
      await queryClient.invalidateQueries({ queryKey: SIMULATOR_KEY });
      await queryClient.invalidateQueries({ queryKey: ["onboarding"] });
    },
    onError: (failure, text) => {
      const unavailable = failure instanceof ApiRequestError && failure.code === "agent_unavailable";
      setPending({ text, failed: true, retryable: unavailable });
      setError(
        unavailable
          ? "Tu agente no pudo responder ahora. Probá de nuevo."
          : apiErrorMessage(failure, "No pudimos enviar tu mensaje. Probá de nuevo."),
      );
    },
  });

  const reset = useMutation({
    mutationFn: resetSimulator,
    onSuccess: (state) => {
      queryClient.setQueryData(SIMULATOR_KEY, state);
      setPending(null);
      setError(null);
    },
    onError: (failure) =>
      setError(apiErrorMessage(failure, "No pudimos reiniciar la conversación. Probá de nuevo.")),
  });

  if (simulatorQuery.isPending) {
    return <p className="text-sm text-muted-foreground">Cargando el simulador…</p>;
  }
  if (simulatorQuery.isError) {
    return (
      <div className="flex flex-col items-start gap-2">
        <p className="text-sm text-destructive" role="alert">
          {apiErrorMessage(simulatorQuery.error, "No pudimos cargar el simulador.")}
        </p>
        <Button variant="outline" onClick={() => void simulatorQuery.refetch()}>
          Reintentar
        </Button>
      </div>
    );
  }

  const state = simulatorQuery.data;
  const messages = state.messages.map(toChatMessage);
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
          Cambiaste tu agente. Reiniciá la conversación para probar los cambios.
        </p>
      ) : null}
      {state.uses_sample_properties ? <SampleBanner /> : null}
      <div className="grid gap-4 md:grid-cols-[minmax(0,1fr)_16rem]">
        <ChatSimulator
          agentName={state.agent_name}
          businessName={state.business_name}
          messages={messages}
          typing={send.isPending}
          resetting={reset.isPending}
          onSend={(text) => send.mutate(text)}
          onReset={() => reset.mutate()}
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

function SampleBanner() {
  return (
    <div className="flex flex-wrap items-center justify-between gap-3 rounded-md border bg-muted px-4 py-3">
      <div>
        <p className="text-sm font-medium">Está usando propiedades de ejemplo</p>
        <p className="text-sm text-muted-foreground">
          Subí tu listado en CSV o Excel y el agente va a mostrar solo tus propiedades.
        </p>
      </div>
      <Button asChild variant="outline" size="sm">
        <Link to="/propiedades">Subir mis propiedades</Link>
      </Button>
    </div>
  );
}
