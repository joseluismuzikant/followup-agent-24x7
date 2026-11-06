import { ApiRequestError } from "@followup/api-client-cuentas-claras";
import type { OnboardingState } from "@followup/api-client-cuentas-claras";
import {
  ClaimInvitation,
  deferOnboarding,
  resumeOnboarding,
  WizardFrame as ShellWizardFrame,
} from "@followup/app-shell";
import {
  Badge,
  Button,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@followup/ui";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { Navigate, useNavigate, useParams } from "react-router";

import { fetchMe, signUp } from "../api/me";
import { advanceOnboarding, fetchOnboarding } from "../api/onboarding";
import { fetchTenantSettings, saveTenantSettings } from "../api/tenant-settings";
import { BusinessStep } from "../components/BusinessStep";
import { ImportPanel } from "../components/ImportPanel";
import { apiErrorMessage } from "../lib/api-errors";
import { useAuth } from "../lib/auth";
import {
  checklistLabels,
  PRODUCT_NAME,
  stepFromPath,
  stepIndex,
  stepPath,
  wizardSteps,
} from "../lib/product";
import type { WizardStepId } from "../lib/product";

export function OnboardingPage() {
  const { step: stepParam } = useParams();
  const meQuery = useQuery({ queryKey: ["me"], queryFn: fetchMe, retry: false });

  if (meQuery.isPending) {
    return null;
  }

  const noProfile =
    meQuery.error instanceof ApiRequestError && meQuery.error.code === "profile_not_found";
  if (meQuery.isError && !noProfile) {
    return <Navigate to="/" replace />;
  }
  if (noProfile) {
    // First time in: join the business the admin created for this email.
    return <ClaimInvitation productName={PRODUCT_NAME} signUp={signUp} useAuth={useAuth} />;
  }

  return <ExistingAccountWizard stepParam={stepParam} />;
}

function ExistingAccountWizard({ stepParam }: { stepParam: string | undefined }) {
  const onboardingQuery = useQuery({
    queryKey: ["onboarding"],
    queryFn: fetchOnboarding,
    retry: false,
  });

  if (onboardingQuery.isPending) {
    return null;
  }
  if (onboardingQuery.isError) {
    return <Navigate to="/" replace />;
  }

  const state = onboardingQuery.data;
  const saved = state.current_step as WizardStepId;
  const requested = stepFromPath(stepParam);

  if (!requested) {
    return state.finished && !stepParam ? (
      <Navigate to="/" replace />
    ) : (
      <Navigate to={stepPath(saved)} replace />
    );
  }
  const reachable = wizardSteps
    .filter((step) => stepIndex(step.id) <= stepIndex(saved))
    .map((step) => step.id);
  if (!reachable.includes(requested.id)) {
    return <Navigate to={stepPath(saved)} replace />;
  }

  return <WizardFrame current={requested.id} reachable={reachable} state={state} canDefer />;
}

interface WizardFrameProps {
  current: WizardStepId;
  reachable: WizardStepId[];
  state?: OnboardingState;
  canDefer: boolean;
}

function WizardFrame({ current, reachable, state, canDefer }: WizardFrameProps) {
  const navigate = useNavigate();

  function finishLater() {
    deferOnboarding();
    navigate("/");
  }

  return (
    <ShellWizardFrame
      productName={PRODUCT_NAME}
      steps={wizardSteps}
      current={current}
      reachable={reachable}
      onSelect={(id) => navigate(stepPath(id as WizardStepId))}
      onFinishLater={canDefer ? finishLater : undefined}
    >
      <StepContent current={current} state={state} />
    </ShellWizardFrame>
  );
}

function StepContent({ current, state }: { current: WizardStepId; state?: OnboardingState }) {
  switch (current) {
    case "business":
      return <BusinessStepContainer />;
    case "invoices":
      return <InvoicesStep state={state} />;
    case "reminders":
      return <RemindersStep />;
    case "connect":
      return <ConnectStep />;
    case "done":
      return <DoneStep state={state} />;
  }
}

function StepCard({
  title,
  description,
  children,
}: {
  title: string;
  description?: string;
  children: ReactNode;
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-xl">{title}</CardTitle>
        {description ? <CardDescription>{description}</CardDescription> : null}
      </CardHeader>
      <CardContent>{children}</CardContent>
    </Card>
  );
}

function AdvanceError({ error }: { error: unknown }) {
  return (
    <p className="text-sm text-destructive" role="alert">
      {apiErrorMessage(error, "No pudimos avanzar. Probá de nuevo.")}
    </p>
  );
}

function BusinessStepContainer() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const settingsQuery = useQuery({ queryKey: ["tenant-settings"], queryFn: fetchTenantSettings });
  const mutation = useMutation({
    mutationFn: async ({ name, type }: { name: string; type: string }) => {
      if (!settingsQuery.data) {
        throw new Error("settings not loaded");
      }
      const { business_hours, notification_emails } = settingsQuery.data;
      return saveTenantSettings({
        business_name: name,
        business_type: type,
        business_hours,
        notification_emails,
      });
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries();
      navigate(stepPath("invoices"));
    },
  });

  if (settingsQuery.isPending) {
    return null;
  }

  return (
    <StepCard
      title="Contanos de tu negocio"
      description="Con esto armamos tu panel de cobranzas. Te lleva un minuto."
    >
      <BusinessStep
        existing={settingsQuery.data}
        saving={mutation.isPending}
        error={
          mutation.isError
            ? apiErrorMessage(mutation.error, "No pudimos guardar tu negocio. Probá de nuevo.")
            : null
        }
        onSubmit={(name, type) => mutation.mutate({ name, type })}
      />
    </StepCard>
  );
}

function useAdvance(to: WizardStepId) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => advanceOnboarding(to),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["onboarding"] });
      navigate(stepPath(to));
    },
  });
}

function InvoicesStep({ state }: { state?: OnboardingState }) {
  const advance = useAdvance("reminders");
  const loaded = state?.checklist.facts.invoices_loaded ?? false;

  return (
    <StepCard
      title="Tus facturas"
      description="Exportá las facturas de tu sistema (o completá la plantilla) y subilas. Con eso ya ves qué está vencido."
    >
      <div className="flex flex-col gap-6">
        <ImportPanel />
        {advance.isError ? <AdvanceError error={advance.error} /> : null}
        <Button
          variant={loaded ? "default" : "outline"}
          className="self-start"
          disabled={advance.isPending}
          onClick={() => advance.mutate()}
        >
          {loaded ? "Seguir" : "Cargar después"}
        </Button>
      </div>
    </StepCard>
  );
}

/** The reminder sequence (C4), read-only until reminders ship. */
export const reminderSequence = [
  {
    when: "3 días antes del vencimiento",
    message: "Hola Marta, te recordamos que la factura B 0003-00001245 por $ 180.000 vence el viernes.",
  },
  {
    when: "El día del vencimiento",
    message: "Hola Marta, hoy vence la factura B 0003-00001245. Si ya la pagaste, avisanos y la marcamos.",
  },
  {
    when: "3 días después",
    message: "Hola Marta, la factura B 0003-00001245 venció hace 3 días. ¿Te podemos ayudar con algo?",
  },
  {
    when: "7 días después",
    message: "Hola Marta, seguimos con la factura B 0003-00001245 pendiente. ¿Nos confirmás una fecha de pago?",
  },
];

function RemindersStep() {
  const navigate = useNavigate();
  const advance = useAdvance("connect");

  return (
    <StepCard
      title="Así vamos a recordarles a tus clientes"
      description="Muy pronto vas a poder ajustarla."
    >
      <div className="flex flex-col gap-6">
        <ol className="flex flex-col gap-3" aria-label="Secuencia de recordatorios">
          {reminderSequence.map((step) => (
            <li key={step.when} className="rounded-md border bg-muted/40 p-3">
              <p className="text-sm font-semibold">{step.when}</p>
              <p className="text-sm text-muted-foreground">{step.message}</p>
            </li>
          ))}
        </ol>
        {advance.isError ? <AdvanceError error={advance.error} /> : null}
        <div className="flex flex-wrap gap-2">
          <Button variant="outline" onClick={() => navigate(stepPath("invoices"))}>
            ← Tus facturas
          </Button>
          <Button disabled={advance.isPending} onClick={() => advance.mutate()}>
            Seguir
          </Button>
        </div>
      </div>
    </StepCard>
  );
}

function ComingSoonCard({ title, description }: { title: string; description: string }) {
  return (
    <section
      aria-label={title}
      className="flex flex-col gap-2 rounded-md border bg-muted/40 p-4"
    >
      <div className="flex items-center justify-between gap-2">
        <h3 className="font-semibold">{title}</h3>
        <Badge tone="info">Muy pronto</Badge>
      </div>
      <p className="text-sm text-muted-foreground">{description}</p>
    </section>
  );
}

function ConnectStep() {
  const advance = useAdvance("done");

  return (
    <StepCard
      title="Conectar"
      description="Cuando estén listas, te avisamos para conectarlas en un par de clics."
    >
      <div className="flex flex-col gap-6">
        <div className="grid gap-4 sm:grid-cols-2">
          <ComingSoonCard
            title="WhatsApp"
            description="Los recordatorios salen desde tu número, con tu nombre."
          />
          <ComingSoonCard
            title="Mercado Pago"
            description="Tus clientes pagan con un link y la factura se marca sola."
          />
        </div>
        {advance.isError ? <AdvanceError error={advance.error} /> : null}
        <Button className="self-start" disabled={advance.isPending} onClick={() => advance.mutate()}>
          Seguir
        </Button>
      </div>
    </StepCard>
  );
}

function DoneStep({ state }: { state?: OnboardingState }) {
  const navigate = useNavigate();
  const items = state?.checklist.items ?? [];
  const ready = items.filter((item) => item.done);
  const pending = items.filter((item) => !item.done);
  const label = (key: string) => checklistLabels[key]?.label ?? key;

  return (
    <StepCard title="¡Listo!" description="Esto es lo que tenés hecho y lo que te falta.">
      <div className="flex flex-col gap-6">
        <div className="grid gap-6 sm:grid-cols-2">
          <section>
            <h3 className="mb-2 text-sm font-semibold">Listo</h3>
            <ul className="flex flex-col gap-1 text-sm">
              {ready.map((item) => (
                <li key={item.key}>✓ {label(item.key)}</li>
              ))}
            </ul>
          </section>
          <section>
            <h3 className="mb-2 text-sm font-semibold">Pendiente</h3>
            <ul className="flex flex-col gap-1 text-sm text-muted-foreground">
              {pending.map((item) => (
                <li key={item.key}>{label(item.key)}</li>
              ))}
            </ul>
          </section>
        </div>
        <Button
          className="self-start"
          onClick={() => {
            resumeOnboarding();
            navigate("/");
          }}
        >
          Ir a mi panel
        </Button>
      </div>
    </StepCard>
  );
}
