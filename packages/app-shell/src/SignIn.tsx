import { AuthScreen, Button, FormField, Input } from "@followup/ui";
import type { SupabaseClient } from "@supabase/supabase-js";
import { useState } from "react";
import type { FormEvent, ReactNode } from "react";

import type { AccountApi } from "./account";
import { ApiRequestError } from "./api";
import { storeDevToken } from "./auth/dev-session";
import type { AuthMode } from "./auth/mode";

export interface SignInProps {
  /** "inmo24x7", "Cuentas Claras": shown next to the logo. */
  productName: string;
  /** "Entrá a inmo24x7", "Entrá al backoffice". */
  title: string;
  /** Under the title: the product's tagline and pitch (optional). */
  description?: ReactNode;
  /** "Backoffice" under the product name. */
  areaName?: string;
  authMode: AuthMode;
  getSupabase: () => SupabaseClient;
  account: AccountApi;
  showLegal?: boolean;
  /** A seeded account, as the email's placeholder in dev mode. */
  devPlaceholder?: string;
}

const EMAIL = /^[^@\s:]+@[^@\s:]+\.[^@\s:]+$/;

/** Email and password. Accounts are created by an admin's invitation; nobody signs up here. */
export function SignIn({
  productName,
  title,
  description,
  areaName,
  authMode,
  getSupabase,
  account,
  showLegal = false,
  devPlaceholder,
}: SignInProps) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function signIn(event: FormEvent) {
    event.preventDefault();
    const address = email.trim().toLowerCase();
    setNotice(null);
    if (!EMAIL.test(address) || !password) {
      setError("Ingresá tu email y tu clave.");
      return;
    }
    setLoading(true);
    setError(null);
    try {
      if (authMode === "dev") {
        storeDevToken(await account.devSignIn(address, password));
      } else {
        const { error: signInError } = await getSupabase().auth.signInWithPassword({
          email: address,
          password,
        });
        if (signInError) {
          setError(
            signInError.status === 400
              ? "El email o la clave no son correctos."
              : "No pudimos iniciar sesión. Probá de nuevo.",
          );
        }
      }
    } catch (caught) {
      setError(
        caught instanceof ApiRequestError && caught.status === 401
          ? "El email o la clave no son correctos."
          : "No pudimos iniciar sesión. Probá de nuevo.",
      );
    } finally {
      setLoading(false);
    }
  }

  async function forgotPassword() {
    setError(null);
    const address = email.trim().toLowerCase();
    if (authMode === "dev") {
      setNotice("En modo desarrollo pedile a un admin una clave temporal nueva.");
      return;
    }
    if (!EMAIL.test(address)) {
      setError("Escribí tu email arriba y volvé a tocar “¿Olvidaste tu clave?”.");
      return;
    }
    const { error: resetError } = await getSupabase().auth.resetPasswordForEmail(address, {
      redirectTo: `${window.location.origin}/cambiar-clave`,
    });
    if (resetError) {
      setError("No pudimos enviar el email. Probá de nuevo.");
    } else {
      setNotice(`Si ${address} tiene una cuenta, te enviamos un link para elegir una clave nueva.`);
    }
  }

  return (
    <AuthScreen
      productName={productName}
      areaName={areaName}
      title={title}
      description={description}
      footer={
        showLegal ? (
          <>
            <a href="#" className="underline">
              Términos
            </a>{" "}
            ·{" "}
            <a href="#" className="underline">
              Política de privacidad
            </a>
          </>
        ) : undefined
      }
    >
      <form onSubmit={(event) => void signIn(event)} className="flex flex-col gap-4" noValidate>
        <FormField label="Email" htmlFor="sign-in-email">
          <Input
            id="sign-in-email"
            type="email"
            autoComplete="email"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            placeholder={authMode === "dev" && devPlaceholder ? devPlaceholder : "tu@email.com"}
          />
        </FormField>
        <FormField label="Clave" htmlFor="sign-in-password">
          <Input
            id="sign-in-password"
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
          />
        </FormField>
        {error ? (
          <p className="text-sm text-destructive" role="alert">
            {error}
          </p>
        ) : null}
        {notice ? (
          <p className="text-sm text-muted-foreground" aria-live="polite">
            {notice}
          </p>
        ) : null}
        <Button type="submit" size="lg" disabled={loading}>
          {loading ? "Entrando..." : "Entrar"}
        </Button>
        <button
          type="button"
          onClick={() => void forgotPassword()}
          className="self-center text-sm font-medium text-brand underline-offset-4 hover:underline"
        >
          ¿Olvidaste tu clave?
        </button>
      </form>
      <p className="border-t pt-4 text-xs text-muted-foreground">
        ¿No tenés cuenta? Las cuentas las crea un administrador: vas a recibir una invitación por
        email.
      </p>
      {authMode === "dev" ? (
        <p className="rounded-lg border border-dashed border-amber-400 bg-warning-soft px-3 py-2 text-xs text-amber-900">
          Modo desarrollo: las cuentas del seed entran con la clave <code>local-1234</code>.
        </p>
      ) : null}
    </AuthScreen>
  );
}
