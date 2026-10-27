import { Button, Card, CardContent, CardHeader, CardTitle } from "@followup/ui";
import { useState } from "react";
import type { FormEvent } from "react";

import { supabase } from "../lib/supabase";

export function IngresoPage() {
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function signInWithGoogle() {
    setError(null);
    const { error: signInError } = await supabase.auth.signInWithOAuth({
      provider: "google",
      options: { redirectTo: window.location.origin },
    });
    if (signInError) {
      setError("No pudimos iniciar sesión con Google. Probá de nuevo.");
    }
  }

  async function sendMagicLink(event: FormEvent) {
    event.preventDefault();
    if (!email.trim()) {
      setError("Ingresá tu email.");
      return;
    }
    setLoading(true);
    setError(null);
    const { error: signInError } = await supabase.auth.signInWithOtp({
      email: email.trim(),
      options: { emailRedirectTo: window.location.origin },
    });
    setLoading(false);
    if (signInError) {
      setError("No pudimos enviar el link. Probá de nuevo.");
    } else {
      setSent(true);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-muted/40 px-4">
      <Card className="w-full max-w-md">
        <CardHeader>
          <CardTitle className="text-xl">Entrá a inmo24x7</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          <Button type="button" onClick={() => void signInWithGoogle()}>
            Continuar con Google
          </Button>

          {sent ? (
            <p className="text-sm text-muted-foreground" aria-live="polite">
              Te enviamos un link a {email}. Revisá tu casilla.
            </p>
          ) : (
            <form onSubmit={(event) => void sendMagicLink(event)} className="flex flex-col gap-2">
              <label htmlFor="email" className="text-sm font-medium">
                Email
              </label>
              <input
                id="email"
                type="email"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                placeholder="tu@email.com"
                className="h-10 rounded-md border bg-card px-3 text-sm outline-none focus:ring-2 focus:ring-ring"
              />
              <Button type="submit" variant="outline" disabled={loading}>
                {loading ? "Enviando..." : "Enviarme un link para entrar"}
              </Button>
            </form>
          )}

          {error ? (
            <p className="text-sm text-destructive" aria-live="polite">
              {error}
            </p>
          ) : null}

          <p className="text-xs text-muted-foreground">
            <a href="#" className="underline">
              Términos
            </a>{" "}
            ·{" "}
            <a href="#" className="underline">
              Política de privacidad
            </a>
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
