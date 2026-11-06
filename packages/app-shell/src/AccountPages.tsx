import { AuthScreen, Button, FormField, Input } from "@followup/ui";
import type { SupabaseClient } from "@supabase/supabase-js";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import type { FormEvent, ReactNode } from "react";
import { Navigate, useNavigate, useSearchParams } from "react-router";

import type { AccountApi } from "./account";
import { ApiRequestError } from "./api";
import { useAuth as useShellAuth } from "./auth/AuthProvider";
import { storeDevToken } from "./auth/dev-session";
import type { AuthMode } from "./auth/mode";
import { errorMessages } from "./errors";

const message = errorMessages({});
export const ACCOUNT_QUERY_KEY = ["account"] as const;

interface PasswordFormProps {
  submitLabel: string;
  saving: boolean;
  error: string | null;
  onSubmit: (password: string) => void;
}

/** A new password twice, with the rules the API checks (8 to 72 characters). */
export function NewPasswordForm({ submitLabel, saving, error, onSubmit }: PasswordFormProps) {
  const [password, setPassword] = useState("");
  const [repeat, setRepeat] = useState("");
  const [local, setLocal] = useState<string | null>(null);

  function submit(event: FormEvent) {
    event.preventDefault();
    if (password.length < 8) {
      setLocal("La clave tiene que tener al menos 8 caracteres.");
      return;
    }
    if (password !== repeat) {
      setLocal("Las dos claves no coinciden.");
      return;
    }
    setLocal(null);
    onSubmit(password);
  }

  const shown = local ?? error;
  return (
    <form onSubmit={submit} className="flex flex-col gap-4" noValidate>
      <FormField label="Clave nueva" htmlFor="new-password" hint="Al menos 8 caracteres.">
        <Input
          id="new-password"
          type="password"
          autoComplete="new-password"
          value={password}
          onChange={(event) => setPassword(event.target.value)}
        />
      </FormField>
      <FormField label="Repetí la clave" htmlFor="repeat-password">
        <Input
          id="repeat-password"
          type="password"
          autoComplete="new-password"
          value={repeat}
          onChange={(event) => setRepeat(event.target.value)}
        />
      </FormField>
      {shown ? (
        <p className="text-sm text-destructive" role="alert">
          {shown}
        </p>
      ) : null}
      <Button type="submit" size="lg" disabled={saving}>
        {saving ? "Guardando..." : submitLabel}
      </Button>
    </form>
  );
}

export interface AccountPageProps {
  productName: string;
  account: AccountApi;
  authMode: AuthMode;
  getSupabase: () => SupabaseClient;
  areaName?: string;
  useAuth?: typeof useShellAuth;
}

/** /cambiar-clave: after a temporary password (forced) and from "¿Olvidaste tu clave?". */
export function ChangePasswordPage({
  productName,
  account,
  areaName,
  useAuth = useShellAuth,
}: AccountPageProps) {
  const { session, loading, signOut } = useAuth();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const mutation = useMutation({
    mutationFn: (password: string) => account.changePassword(password),
    onSuccess: async () => {
      await queryClient.invalidateQueries();
      navigate("/", { replace: true });
    },
  });

  if (loading) {
    return null;
  }
  if (!session) {
    return <Navigate to="/ingreso" replace />;
  }
  return (
    <AuthScreen
      productName={productName}
      areaName={areaName}
      title="Elegí tu clave"
      description={
        <>
          Entraste como <span className="font-medium text-foreground">{session.email}</span>.
          Antes de seguir, elegí una clave que solo vos sepas.
        </>
      }
    >
      <NewPasswordForm
        submitLabel="Guardar mi clave"
        saving={mutation.isPending}
        error={
          mutation.isError ? message(mutation.error, "No pudimos guardar tu clave. Probá de nuevo.") : null
        }
        onSubmit={(password) => mutation.mutate(password)}
      />
      <button
        type="button"
        onClick={() => void signOut()}
        className="self-center text-sm text-muted-foreground underline-offset-4 hover:underline"
      >
        Cerrar sesión
      </button>
    </AuthScreen>
  );
}

/** /invitacion?token=…: the emailed link. The person chooses a password and comes in. */
export function InvitationPage({
  productName,
  account,
  authMode,
  getSupabase,
  useAuth = useShellAuth,
}: AccountPageProps) {
  const [params] = useSearchParams();
  const token = params.get("token") ?? "";
  const navigate = useNavigate();
  const { signOut } = useAuth();
  const invitation = useQuery({
    queryKey: ["invitation", token],
    queryFn: () => account.fetchInvitation(token),
    enabled: Boolean(token),
    retry: false,
  });
  const accept = useMutation({
    mutationFn: async (password: string) => {
      const email = await account.acceptInvitation(token, password);
      // Whoever was signed in on this browser, the invited person comes in now.
      await signOut();
      if (authMode === "dev") {
        storeDevToken(await account.devSignIn(email, password));
      } else {
        const { error } = await getSupabase().auth.signInWithPassword({ email, password });
        if (error) {
          throw error;
        }
      }
    },
    onSuccess: () => navigate("/", { replace: true }),
  });

  const screen = (title: string, body: ReactNode, description?: ReactNode) => (
    <AuthScreen productName={productName} title={title} description={description}>
      {body}
    </AuthScreen>
  );
  const toSignIn = (
    <Button asChild size="lg">
      <a href="/ingreso">Ir a entrar</a>
    </Button>
  );

  if (!token || invitation.isError) {
    return screen(
      "Link no válido",
      toSignIn,
      "Revisá que hayas abierto el link completo del email, o pedile al administrador que te lo reenvíe.",
    );
  }
  if (invitation.isPending) {
    return screen("Tu invitación", <p className="text-sm text-muted-foreground">Cargando...</p>);
  }
  const data = invitation.data;
  if (data.status === "expired") {
    return screen(
      "Este link venció",
      toSignIn,
      "Los links de invitación duran 7 días. Pedile al administrador que te lo reenvíe.",
    );
  }
  if (data.status === "used" || !data.needs_password) {
    return screen(
      "Ya tenés tu clave",
      toSignIn,
      <>
        Entrá con <span className="font-medium text-foreground">{data.email}</span> y tu clave
        para ver {data.business_name}.
      </>,
    );
  }
  return screen(
    `Bienvenido a ${productName}`,
    <NewPasswordForm
      submitLabel="Crear mi clave y entrar"
      saving={accept.isPending}
      error={accept.isError ? message(accept.error, "No pudimos guardar tu clave. Probá de nuevo.") : null}
      onSubmit={(password) => accept.mutate(password)}
    />,
    <>
      Te dieron de alta como responsable de{" "}
      <span className="font-medium text-foreground">{data.business_name}</span>. Elegí la clave
      para <span className="font-medium text-foreground">{data.email}</span>.
    </>,
  );
}

/** Between "signed in" and anything else: a temporary password goes to /cambiar-clave first. */
export function RequireAccount({
  account,
  children,
}: {
  account: AccountApi;
  children: ReactNode;
}) {
  const query = useQuery({ queryKey: ACCOUNT_QUERY_KEY, queryFn: account.fetchAccount, retry: false });
  if (query.isPending) {
    return null;
  }
  if (query.data?.must_change_password) {
    return <Navigate to="/cambiar-clave" replace />;
  }
  // Errors (an expired session, the API down) are the next guard's to show.
  return <>{children}</>;
}

/** Signed in, but nobody invited this email to this product. */
export function NotEnabledScreen({
  productName,
  email,
  supportEmail,
  onSignOut,
}: {
  productName: string;
  email: string;
  supportEmail?: string;
  onSignOut: () => void;
}) {
  return (
    <AuthScreen
      productName={productName}
      title="Tu cuenta no está habilitada"
      description={
        <>
          <span className="font-medium text-foreground">{email}</span> no tiene un negocio en{" "}
          {productName}. Las cuentas las crea un administrador: pedile que te invite
          {supportEmail ? (
            <>
              {" "}o escribinos a{" "}
              <a className="font-medium text-brand underline" href={`mailto:${supportEmail}`}>
                {supportEmail}
              </a>
            </>
          ) : null}
          .
        </>
      }
    >
      <Button variant="outline" onClick={onSignOut}>
        Cerrar sesión
      </Button>
    </AuthScreen>
  );
}

/** The first time an invited person comes in: joins the business the admin created for
 * their email (POST /me/sign-up), then the wizard. Not invited: the "no habilitada" screen. */
export function ClaimInvitation({
  productName,
  signUp,
  useAuth = useShellAuth,
}: {
  productName: string;
  signUp: () => Promise<unknown>;
  useAuth?: typeof useShellAuth;
}) {
  const { session, signOut } = useAuth();
  const queryClient = useQueryClient();
  const claim = useQuery({
    queryKey: ["sign-up"],
    queryFn: async () => {
      const result = await signUp();
      await queryClient.invalidateQueries({ queryKey: ["me"] });
      return result ?? true;
    },
    retry: false,
    staleTime: Infinity,
  });

  if (claim.isPending || claim.isSuccess) {
    return null;
  }
  const error = claim.error;
  if (error instanceof ApiRequestError && error.code === "password_change_required") {
    return <Navigate to="/cambiar-clave" replace />;
  }
  if (error instanceof ApiRequestError && error.code === "not_invited") {
    return (
      <NotEnabledScreen
        productName={productName}
        email={session?.email ?? ""}
        onSignOut={() => void signOut()}
      />
    );
  }
  return (
    <AuthScreen productName={productName} title="No pudimos preparar tu cuenta">
      <p className="text-sm text-muted-foreground" role="alert">
        {message(error, "Hubo un problema al conectarnos con el servicio. Probá de nuevo.")}
      </p>
      <Button onClick={() => void claim.refetch()}>Reintentar</Button>
    </AuthScreen>
  );
}
