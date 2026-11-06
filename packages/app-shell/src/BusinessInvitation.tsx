import {
  Button,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  Dialog,
  FormField,
  Input,
} from "@followup/ui";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { errorMessages } from "./errors";

const message = errorMessages({});

export interface CreatedBusiness {
  id: string;
  owner_email: string | null;
  temporary_password?: string | null;
}

export interface BusinessCreateInput {
  business_name: string;
  business_type: string;
  owner_email: string;
}

/** The temporary password, shown once with "Copiar". */
function TemporaryPassword({ email, password }: { email: string; password: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <div className="flex flex-col gap-2 rounded-xl border border-emerald-200 bg-success-soft p-4">
      <p className="text-sm">
        Clave temporal de <span className="font-medium">{email}</span>:
      </p>
      <div className="flex items-center gap-2">
        <code className="flex-1 rounded-lg bg-card px-3 py-2 font-mono text-base tracking-wider">
          {password}
        </code>
        <Button
          type="button"
          variant="outline"
          onClick={() => {
            void navigator.clipboard?.writeText(password).then(() => setCopied(true));
          }}
        >
          {copied ? "Copiada" : "Copiar"}
        </Button>
      </div>
      <p className="text-xs text-muted-foreground">
        Se muestra una sola vez. Pasásela por otro canal (WhatsApp, teléfono): la cambia la primera
        vez que entra.
      </p>
    </div>
  );
}

export interface CreateBusinessDialogProps {
  open: boolean;
  onClose: () => void;
  businessType: string;
  create: (input: BusinessCreateInput) => Promise<CreatedBusiness>;
  /** After "Listo": usually the business detail. */
  onCreated: (business: CreatedBusiness) => void;
}

/** "Dar de alta un negocio": the business, its owner's account and the invitation email. */
export function CreateBusinessDialog({
  open,
  onClose,
  businessType,
  create,
  onCreated,
}: CreateBusinessDialogProps) {
  const queryClient = useQueryClient();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const mutation = useMutation({
    mutationFn: () =>
      create({
        business_name: name.trim(),
        business_type: businessType,
        owner_email: email.trim(),
      }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["businesses"] }),
  });

  function close() {
    const created = mutation.data;
    setName("");
    setEmail("");
    mutation.reset();
    onClose();
    if (created) {
      onCreated(created);
    }
  }

  const created = mutation.data;
  return (
    <Dialog open={open} title="Dar de alta un negocio" onClose={close}>
      {created ? (
        <div className="flex flex-col gap-4">
          <p className="text-sm">
            Te enviamos la invitación a{" "}
            <span className="font-medium">{created.owner_email}</span>. El link vence en 7 días.
          </p>
          {created.temporary_password ? (
            <TemporaryPassword
              email={created.owner_email ?? ""}
              password={created.temporary_password}
            />
          ) : (
            <p className="text-sm text-muted-foreground">
              Ya tenía una cuenta en la plataforma: entra con su clave de siempre.
            </p>
          )}
          <div className="flex justify-end">
            <Button onClick={close}>Listo</Button>
          </div>
        </div>
      ) : (
        <form
          className="flex flex-col gap-4"
          onSubmit={(event) => {
            event.preventDefault();
            mutation.mutate();
          }}
        >
          <FormField label="Nombre del negocio" htmlFor="business-name">
            <Input
              id="business-name"
              value={name}
              maxLength={200}
              onChange={(event) => setName(event.target.value)}
            />
          </FormField>
          <FormField
            label="Email del dueño"
            htmlFor="owner-email"
            hint="Le creamos la cuenta con una clave temporal y le mandamos la invitación por email."
          >
            <Input
              id="owner-email"
              type="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
            />
          </FormField>
          {mutation.isError ? (
            <p className="text-sm text-destructive" role="alert">
              {message(mutation.error, "No pudimos dar de alta el negocio.")}
            </p>
          ) : null}
          <div className="flex justify-end gap-2">
            <Button type="button" variant="outline" onClick={close}>
              Cancelar
            </Button>
            <Button type="submit" disabled={!name.trim() || !email.trim() || mutation.isPending}>
              Dar de alta
            </Button>
          </div>
        </form>
      )}
    </Dialog>
  );
}

export interface OwnerInvitationCardProps {
  ownerEmail: string | null;
  resend: () => Promise<unknown>;
  resetPassword: () => Promise<{ temporary_password: string }>;
}

/** On a business whose owner has not come in yet: resend the email or a new temporary
 * password (for when they lost both). */
export function OwnerInvitationCard({
  ownerEmail,
  resend,
  resetPassword,
}: OwnerInvitationCardProps) {
  const queryClient = useQueryClient();
  const resendMutation = useMutation({
    mutationFn: resend,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["business"] }),
  });
  const resetMutation = useMutation({
    mutationFn: resetPassword,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["business"] }),
  });
  const error = resendMutation.error ?? resetMutation.error;

  return (
    <Card>
      <CardHeader>
        <CardTitle>Invitación</CardTitle>
        <CardDescription>
          {ownerEmail ?? "El dueño"} todavía no entró. Podés reenviarle el email o generarle una
          clave temporal nueva.
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <div className="flex flex-wrap gap-2">
          <Button
            variant="outline"
            disabled={resendMutation.isPending}
            onClick={() => resendMutation.mutate()}
          >
            Reenviar invitación
          </Button>
          <Button
            variant="outline"
            disabled={resetMutation.isPending}
            onClick={() => resetMutation.mutate()}
          >
            Generar clave temporal nueva
          </Button>
        </div>
        {resendMutation.isSuccess ? (
          <p className="text-sm text-success" aria-live="polite">
            Listo: le enviamos un link nuevo (el anterior dejó de funcionar).
          </p>
        ) : null}
        {resetMutation.data ? (
          <TemporaryPassword
            email={ownerEmail ?? ""}
            password={resetMutation.data.temporary_password}
          />
        ) : null}
        {error ? (
          <p className="text-sm text-destructive" role="alert">
            {message(error, "No pudimos hacerlo. Probá de nuevo.")}
          </p>
        ) : null}
      </CardContent>
    </Card>
  );
}
