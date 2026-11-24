import type { ListingDraft, Property } from "@followup/api-client-inmo24x7";
import { Button, Dialog, FormField, Input, SegmentedControl } from "@followup/ui";
import { useMutation } from "@tanstack/react-query";
import { useId, useState } from "react";

import { readListingLink, readListingText } from "../../api/properties";
import { apiErrorMessage } from "../../lib/api-errors";

type Tab = "link" | "text";

const tabs = [
  { value: "link", label: "Pegar link" },
  { value: "text", label: "Pegar texto de la publicación" },
] as const;

interface LinkImportDialogProps {
  open: boolean;
  onClose: () => void;
  /** The publication was read: open the form pre-filled with it. */
  onDraft: (draft: ListingDraft) => void;
  /** The agency already has a property with this link: open it. */
  onOpenExisting: (property: Property) => void;
}

/** "Cargar desde un link": paste the link of an own publication (or its text, when the portal
 * does not let us read it) and the property form opens pre-filled. Nothing is saved here. */
export function LinkImportDialog({ open, onClose, onDraft, onOpenExisting }: LinkImportDialogProps) {
  return (
    <Dialog open={open} title="Cargar desde un link" onClose={onClose}>
      {open ? (
        <LinkImportForm onDraft={onDraft} onOpenExisting={onOpenExisting} onCancel={onClose} />
      ) : null}
    </Dialog>
  );
}

function LinkImportForm({
  onDraft,
  onOpenExisting,
  onCancel,
}: {
  onDraft: (draft: ListingDraft) => void;
  onOpenExisting: (property: Property) => void;
  onCancel: () => void;
}) {
  const ids = { link: useId(), text: useId() };
  const [tab, setTab] = useState<Tab>("link");
  const [link, setLink] = useState("");
  const [text, setText] = useState("");
  const [blocked, setBlocked] = useState<string | null>(null);
  const [duplicate, setDuplicate] = useState<Property | null>(null);
  const [linkError, setLinkError] = useState<string | undefined>();

  function handle(draft: ListingDraft) {
    if (draft.duplicate) {
      setDuplicate(draft.duplicate);
      return;
    }
    if (draft.problem === "blocked") {
      // Bot protection (Zonaprop does it): the agent copies the page instead.
      setBlocked(draft.message);
      setTab("text");
      return;
    }
    onDraft(draft);
  }

  const read = useMutation({
    mutationFn: () => (tab === "link" ? readListingLink(link.trim()) : readListingText(text, link.trim())),
    onMutate: () => setDuplicate(null),
    onSuccess: handle,
  });

  function submit() {
    if (!link.trim()) {
      setLinkError("Pegá el link de la publicación.");
      return;
    }
    setLinkError(undefined);
    read.mutate();
  }

  const busy = read.isPending;
  return (
    <form
      className="flex flex-col gap-4"
      noValidate
      onSubmit={(event) => {
        event.preventDefault();
        submit();
      }}
    >
      <SegmentedControl
        ariaLabel="Cómo cargarla"
        options={tabs}
        value={tab}
        className="flex w-full flex-wrap [&>button]:flex-1"
        onChange={(value) => {
          setTab(value);
          read.reset();
        }}
      />
      <p className="text-sm text-muted-foreground">Usá links de tus propias publicaciones.</p>
      <FormField
        label="Link de la publicación"
        htmlFor={ids.link}
        error={linkError}
        hint={tab === "text" ? "Queda guardado como el link de la propiedad." : undefined}
      >
        <Input
          id={ids.link}
          type="url"
          inputMode="url"
          autoComplete="off"
          value={link}
          placeholder="https://www.zonaprop.com.ar/propiedades/..."
          onChange={(event) => setLink(event.target.value)}
        />
      </FormField>
      {tab === "text" ? (
        <>
          {blocked ? (
            <p className="rounded-md border border-amber-300 bg-amber-50 p-3 text-sm" role="status">
              {blocked}
            </p>
          ) : (
            <p className="text-sm text-muted-foreground">
              Abrí tu publicación, seleccioná todo (Ctrl+A), copiá (Ctrl+C) y pegalo acá. En el
              celular: mantené apretado el texto, «Seleccionar todo» y «Copiar».
            </p>
          )}
          <FormField label="Texto de la publicación" htmlFor={ids.text}>
            <textarea
              id={ids.text}
              value={text}
              rows={8}
              placeholder="Alquiler · $ 780.000 · 2 ambientes · Palermo…"
              className="min-h-40 rounded-md border bg-card p-3 text-sm outline-none focus:ring-2 focus:ring-ring"
              onChange={(event) => setText(event.target.value)}
            />
          </FormField>
        </>
      ) : null}

      {duplicate ? (
        <div className="flex flex-col gap-2 rounded-md border bg-muted p-3 text-sm" role="status">
          <p>
            Ya cargaste esta propiedad: <span className="font-medium">{duplicate.title}</span>.
          </p>
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="self-start"
            onClick={() => onOpenExisting(duplicate)}
          >
            Abrirla
          </Button>
        </div>
      ) : null}
      {read.isError ? (
        <p className="text-sm text-destructive" role="alert">
          {apiErrorMessage(read.error, "No pudimos leer la publicación. Probá de nuevo.")}
        </p>
      ) : null}

      <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
        <Button type="button" variant="ghost" onClick={onCancel}>
          Cancelar
        </Button>
        <Button type="submit" disabled={busy}>
          {busy
            ? "Leyendo la publicación..."
            : tab === "link"
              ? "Leer publicación"
              : "Leer texto"}
        </Button>
      </div>
    </form>
  );
}
