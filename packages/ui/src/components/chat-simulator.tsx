import { useEffect, useRef, useState } from "react";
import type * as React from "react";

import { cn } from "../lib/utils";
import { Button } from "./button";
import { PropertyCard, type PropertyCardData } from "./property-card";

type ChatAuthor = "visitor" | "agent" | "human" | "system";

interface ChatMessage {
  id: string;
  author: ChatAuthor;
  text: string;
  cards?: readonly PropertyCardData[] | null;
  /** A visitor message that has not been answered yet, or failed to send. */
  status?: "sending" | "failed";
  /** Link to the turn's trace (backoffice only). */
  traceUrl?: string | null;
}

interface ChatSimulatorProps {
  agentName: string;
  businessName: string;
  messages: readonly ChatMessage[];
  onSend: (text: string) => void;
  onReset: () => void;
  /** Shows the typing indicator and blocks sending. */
  typing?: boolean;
  resetting?: boolean;
  /** Shown above the input, e.g. an error with a retry button. */
  notice?: React.ReactNode;
  resolveLink?: (link: string) => string;
  className?: string;
}

const bubbleStyles: Record<ChatAuthor, string> = {
  visitor: "self-end bg-primary text-primary-foreground",
  agent: "self-start bg-muted text-foreground",
  human: "self-start bg-muted text-foreground",
  system: "self-center bg-transparent text-xs text-muted-foreground",
};

function ChatSimulator({
  agentName,
  businessName,
  messages,
  onSend,
  onReset,
  typing = false,
  resetting = false,
  notice,
  resolveLink,
  className,
}: ChatSimulatorProps) {
  const [draft, setDraft] = useState("");
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView?.({ block: "end" });
  }, [messages.length, typing]);

  function send() {
    const text = draft.trim();
    if (!text || typing) {
      return;
    }
    onSend(text);
    setDraft("");
  }

  return (
    <section
      data-slot="chat-simulator"
      aria-label={`Chat con ${agentName}`}
      className={cn("flex h-[32rem] flex-col overflow-hidden rounded-lg border bg-card", className)}
    >
      <header className="flex items-center gap-3 border-b px-4 py-3">
        <div
          aria-hidden="true"
          className="grid size-9 place-items-center rounded-full bg-primary font-semibold text-primary-foreground"
        >
          {agentName.slice(0, 1).toUpperCase()}
        </div>
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-semibold">
            {agentName} · {businessName}
          </p>
          <p className="text-xs text-muted-foreground">Responde al instante</p>
        </div>
        <Button variant="outline" size="sm" disabled={resetting} onClick={onReset}>
          Reiniciar
        </Button>
      </header>

      <div className="flex flex-1 flex-col gap-2 overflow-y-auto p-4" aria-live="polite">
        {messages.map((message) => (
          <div key={message.id} className="flex flex-col gap-2">
            <p
              className={cn(
                "max-w-[80%] whitespace-pre-line rounded-2xl px-3 py-2 text-sm",
                bubbleStyles[message.author],
                message.status === "sending" && "opacity-70",
                message.status === "failed" && "ring-2 ring-destructive",
              )}
            >
              {message.text}
            </p>
            {message.traceUrl ? (
              <a
                href={message.traceUrl}
                target="_blank"
                rel="noreferrer"
                className="self-start text-xs text-muted-foreground underline-offset-4 hover:underline"
              >
                Ver traza
              </a>
            ) : null}
            {message.cards && message.cards.length > 0 ? (
              <div className="flex gap-2 overflow-x-auto pb-1">
                {message.cards.map((card) => (
                  <PropertyCard key={card.id} property={card} resolveLink={resolveLink} />
                ))}
              </div>
            ) : null}
          </div>
        ))}
        {typing ? (
          <p
            role="status"
            className="self-start rounded-2xl bg-muted px-3 py-2 text-sm text-muted-foreground"
          >
            {agentName} está escribiendo…
          </p>
        ) : null}
        <div ref={endRef} />
      </div>

      {notice ? <div className="border-t px-4 py-2">{notice}</div> : null}

      <form
        className="flex items-end gap-2 border-t p-3"
        onSubmit={(event) => {
          event.preventDefault();
          send();
        }}
      >
        <textarea
          aria-label="Mensaje"
          placeholder="Escribí un mensaje…"
          rows={1}
          maxLength={1000}
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter" && !event.shiftKey) {
              event.preventDefault();
              send();
            }
          }}
          className="max-h-32 min-h-10 flex-1 resize-none rounded-md border bg-background px-3 py-2 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring"
        />
        <Button type="submit" disabled={typing || !draft.trim()}>
          Enviar
        </Button>
      </form>
    </section>
  );
}

export { ChatSimulator, type ChatAuthor, type ChatMessage };
