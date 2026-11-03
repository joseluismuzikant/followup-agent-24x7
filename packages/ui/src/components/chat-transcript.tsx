import type * as React from "react";

import { cn } from "../lib/utils";

type TranscriptAuthor = "visitor" | "agent" | "human" | "system";

interface TranscriptMessage {
  id: string;
  author: TranscriptAuthor;
  /** What the bubble shows (already including "Audio: …" style labels). */
  text: React.ReactNode;
  /** Shown above team bubbles: who on the team wrote it. */
  authorName?: string | null;
  /** A small line under the bubble (delivery status, time). */
  footer?: React.ReactNode;
  /** Highlights the footer as a problem ("No se pudo enviar"). */
  failed?: boolean;
}

interface ChatTranscriptProps {
  messages: readonly TranscriptMessage[];
  /** How the agent is named over its bubbles ("Sofía"). */
  agentName?: string;
  className?: string;
}

const bubbleStyles: Record<Exclude<TranscriptAuthor, "system">, string> = {
  visitor: "bg-muted text-foreground",
  agent: "bg-primary text-primary-foreground",
  human: "bg-emerald-600 text-white",
};

/** A read-only conversation from the business's side: the lead on the left; the agent and
 * the team on the right (team bubbles say who wrote them); system events centered. */
function ChatTranscript({ messages, agentName = "Agente", className }: ChatTranscriptProps) {
  return (
    <ol data-slot="chat-transcript" className={cn("flex flex-col gap-2", className)}>
      {messages.map((message) => {
        if (message.author === "system") {
          return (
            <li
              key={message.id}
              className="self-center rounded-full border bg-background px-3 py-1 text-center text-xs text-muted-foreground"
            >
              {message.text}
            </li>
          );
        }
        const ours = message.author !== "visitor";
        const label = message.author === "human" ? (message.authorName ?? "Equipo") : agentName;
        return (
          <li
            key={message.id}
            className={cn(
              "flex max-w-[85%] flex-col gap-0.5",
              ours ? "items-end self-end" : "items-start self-start",
            )}
          >
            {ours ? <span className="text-[11px] text-muted-foreground">{label}</span> : null}
            <p
              className={cn(
                "whitespace-pre-line rounded-2xl px-3 py-2 text-sm",
                bubbleStyles[message.author],
              )}
            >
              {message.text}
            </p>
            {message.footer ? (
              <span
                className={cn(
                  "text-[11px] text-muted-foreground",
                  message.failed && "text-destructive",
                )}
              >
                {message.footer}
              </span>
            ) : null}
          </li>
        );
      })}
    </ol>
  );
}

export { ChatTranscript, type TranscriptAuthor, type TranscriptMessage };
