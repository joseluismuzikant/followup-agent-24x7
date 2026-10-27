import { Button, Card, CardContent, CardDescription, CardHeader, CardTitle } from "@followup/ui";
import { useState } from "react";
import type { FormEvent } from "react";
import { useNavigate } from "react-router";

import { signUp } from "../api/me";
import { apiErrorMessage } from "../lib/api-errors";

export function OnboardingPage() {
  const navigate = useNavigate();
  const [businessName, setBusinessName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!businessName.trim()) {
      setError("Ingresá el nombre de tu negocio.");
      return;
    }
    setLoading(true);
    setError(null);
    try {
      await signUp(businessName.trim());
      navigate("/");
    } catch (signUpError) {
      setError(
        apiErrorMessage(signUpError, "No pudimos crear tu negocio. Probá de nuevo."),
      );
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-muted/40 px-4">
      <Card className="w-full max-w-md">
        <CardHeader>
          <CardTitle>Creá tu negocio</CardTitle>
          <CardDescription>
            Contanos el nombre de tu inmobiliaria para empezar.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={(event) => void submit(event)} className="flex flex-col gap-2">
            <label htmlFor="business-name" className="text-sm font-medium">
              Nombre del negocio
            </label>
            <input
              id="business-name"
              value={businessName}
              onChange={(event) => setBusinessName(event.target.value)}
              placeholder="Inmobiliaria Sur"
              className="h-10 rounded-md border bg-card px-3 text-sm outline-none focus:ring-2 focus:ring-ring"
            />
            {error ? (
              <p className="text-sm text-destructive" aria-live="polite">
                {error}
              </p>
            ) : null}
            <Button type="submit" disabled={loading}>
              {loading ? "Creando..." : "Guardar y continuar"}
            </Button>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
