import { Button, Dialog, FormField, Input } from "@followup/ui";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate } from "react-router";

import { createBusiness } from "../api/backoffice";
import { apiErrorMessage } from "../lib/api-errors";

/** "Dar de alta un negocio": the owner joins it when they sign up with this email. */
export function CreateBusinessDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const create = useMutation({
    mutationFn: () => createBusiness({
        business_name: name.trim(),
        business_type: "inmobiliaria",
        owner_email: email.trim(),
      }),
    onSuccess: async (business) => {
      await queryClient.invalidateQueries({ queryKey: ["businesses"] });
      onClose();
      void navigate(`/negocios/${business.id}`);
    },
  });

  return (
    <Dialog open={open} title="Dar de alta un negocio" onClose={onClose}>
      <form
        className="flex flex-col gap-4"
        onSubmit={(event) => {
          event.preventDefault();
          create.mutate();
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
          hint="Cuando entre con este email (Google o link por email), queda como dueño de este negocio."
        >
          <Input
            id="owner-email"
            type="email"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
          />
        </FormField>
        {create.isError ? (
          <p className="text-sm text-destructive" role="alert">
            {apiErrorMessage(create.error, "No pudimos dar de alta el negocio.")}
          </p>
        ) : null}
        <div className="flex justify-end gap-2">
          <Button type="button" variant="outline" onClick={onClose}>
            Cancelar
          </Button>
          <Button type="submit" disabled={!name.trim() || !email.trim() || create.isPending}>
            Dar de alta
          </Button>
        </div>
      </form>
    </Dialog>
  );
}
