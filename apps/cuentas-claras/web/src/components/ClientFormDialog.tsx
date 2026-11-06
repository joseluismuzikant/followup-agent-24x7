import type { ClientDetail, ClientInput } from "@followup/api-client-cuentas-claras";
import { Button, Dialog, FormField, Input } from "@followup/ui";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import type { FormEvent } from "react";

import { createClient, updateClient } from "../api/clients";
import { apiErrorMessage } from "../lib/api-errors";
import { isValidCuit, looksLikePhone } from "../lib/cuit";

interface ClientFormDialogProps {
  open: boolean;
  /** Editing it; a new client when absent. */
  client?: ClientDetail;
  onClose: () => void;
  onSaved?: (client: ClientDetail) => void;
}

type Errors = Partial<Record<"name" | "cuit" | "whatsapp" | "email", string>>;

const fields = ["name", "subtitle", "cuit", "contact_name", "whatsapp", "email", "notes"] as const;

function initial(client?: ClientDetail): ClientInput {
  return Object.fromEntries(
    fields.map((field) => [field, field === "whatsapp" ? (client?.whatsapp_display ?? "") : (client?.[field] ?? "")]),
  ) as unknown as ClientInput;
}

export function validateClient(input: ClientInput): Errors {
  const errors: Errors = {};
  if (!input.name?.trim()) {
    errors.name = "Ingresá el nombre del cliente.";
  }
  if (input.cuit?.trim() && !isValidCuit(input.cuit)) {
    errors.cuit = "El CUIT no es válido: son 11 números y el último es el dígito verificador.";
  }
  if (input.whatsapp?.trim() && !looksLikePhone(input.whatsapp)) {
    errors.whatsapp = "Ingresá el número con código de área, por ejemplo 11 5555-1234.";
  }
  if (input.email?.trim() && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(input.email.trim())) {
    errors.email = "Ingresá un email válido.";
  }
  return errors;
}

export function ClientFormDialog({ open, client, onClose, onSaved }: ClientFormDialogProps) {
  return (
    <Dialog open={open} title={client ? "Editar cliente" : "Nuevo cliente"} onClose={onClose}>
      {open ? <ClientForm client={client} onClose={onClose} onSaved={onSaved} /> : null}
    </Dialog>
  );
}

function ClientForm({ client, onClose, onSaved }: Omit<ClientFormDialogProps, "open">) {
  const queryClient = useQueryClient();
  const [values, setValues] = useState<ClientInput>(() => initial(client));
  const [errors, setErrors] = useState<Errors>({});
  const mutation = useMutation({
    mutationFn: (input: ClientInput) => (client ? updateClient(client.id, input) : createClient(input)),
    onSuccess: async (saved) => {
      queryClient.setQueryData(["client", saved.id], saved);
      await queryClient.invalidateQueries({ queryKey: ["clients"] });
      await queryClient.invalidateQueries({ queryKey: ["invoices"] });
      onSaved?.(saved);
      onClose();
    },
  });

  function set(field: (typeof fields)[number], value: string) {
    setValues((current) => ({ ...current, [field]: value }));
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    const found = validateClient(values);
    setErrors(found);
    if (Object.keys(found).length === 0) {
      mutation.mutate(
        Object.fromEntries(
          Object.entries(values).map(([key, value]) => [key, String(value ?? "").trim()]),
        ) as unknown as ClientInput,
      );
    }
  }

  return (
    <form onSubmit={submit} className="flex flex-col gap-4" noValidate>
      <FormField label="Nombre o razón social" htmlFor="client-name" error={errors.name}>
        <Input id="client-name" value={values.name} onChange={(event) => set("name", event.target.value)} />
      </FormField>
      <FormField
        label="Aclaración (opcional)"
        htmlFor="client-subtitle"
        hint="Por ejemplo, el edificio o la sucursal: Av. Rivadavia 4500."
      >
        <Input
          id="client-subtitle"
          value={values.subtitle ?? ""}
          onChange={(event) => set("subtitle", event.target.value)}
        />
      </FormField>
      <FormField label="CUIT (opcional)" htmlFor="client-cuit" error={errors.cuit}>
        <Input
          id="client-cuit"
          inputMode="numeric"
          placeholder="30-12345678-9"
          value={values.cuit ?? ""}
          onChange={(event) => set("cuit", event.target.value)}
        />
      </FormField>
      <FormField label="Contacto (opcional)" htmlFor="client-contact">
        <Input
          id="client-contact"
          value={values.contact_name ?? ""}
          onChange={(event) => set("contact_name", event.target.value)}
        />
      </FormField>
      <FormField
        label="WhatsApp"
        htmlFor="client-whatsapp"
        hint="Ahí le van a llegar los recordatorios."
        error={errors.whatsapp}
      >
        <Input
          id="client-whatsapp"
          inputMode="tel"
          placeholder="11 5555-1234"
          value={values.whatsapp ?? ""}
          onChange={(event) => set("whatsapp", event.target.value)}
        />
      </FormField>
      <FormField label="Email (opcional)" htmlFor="client-email" error={errors.email}>
        <Input
          id="client-email"
          type="email"
          value={values.email ?? ""}
          onChange={(event) => set("email", event.target.value)}
        />
      </FormField>
      <FormField label="Notas (opcional)" htmlFor="client-notes">
        <Input id="client-notes" value={values.notes ?? ""} onChange={(event) => set("notes", event.target.value)} />
      </FormField>
      {mutation.isError ? (
        <p className="text-sm text-destructive" role="alert">
          {apiErrorMessage(mutation.error, "No pudimos guardar el cliente. Probá de nuevo.")}
        </p>
      ) : null}
      <div className="flex flex-wrap gap-2">
        <Button type="submit" disabled={mutation.isPending}>
          {mutation.isPending ? "Guardando..." : "Guardar"}
        </Button>
        <Button type="button" variant="outline" onClick={onClose}>
          Cancelar
        </Button>
      </div>
    </form>
  );
}
