import { ApiRequestError } from "@followup/api-client-inmo24x7";
import type { OnboardingState } from "@followup/api-client-inmo24x7";
import {
  Button,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  WizardStepper,
} from "@followup/ui";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Navigate, useNavigate, useParams } from "react-router";

import { fetchAgentSetup, saveAgentSetup } from "../api/agent-setup";
import { fetchMe, signUp } from "../api/me";
import { advanceOnboarding, fetchOnboarding } from "../api/onboarding";
import { fetchTenantSettings, saveTenantSettings } from "../api/tenant-settings";
import { AgentSetupForm } from "../components/AgentSetupForm";
import { AgentSummary } from "../components/onboarding/AgentSummary";
import { BusinessStep } from "../components/onboarding/BusinessStep";
import { apiErrorMessage } from "../lib/api-errors";
import { deferOnboarding, resumeOnboarding } from "../lib/onboarding-deferred";
import { stepFromPath, stepIndex, wizardSteps } from "../lib/setup";
import type { WizardStepId } from "../lib/setup";

const stepPath = (id: WizardStepId) =>
  `/onboarding/${wizardSteps[stepIndex(id)].path}`;

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
    if (stepParam && stepFromPath(stepParam)?.id !== "business") {
      return <Navigate to={stepPath("business")} replace />;
    }
    return <WizardFrame current="business" reachable={["business"]} canDefer={false} />;
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
  const index = stepIndex(current);

  function selectStep(id: string) {
    navigate(stepPath(id as WizardStepId));
  }

  function finishLater() {
    deferOnboarding();
    navigate("/");
  }

  return (
    <div className="min-h-screen bg-muted/40">
      <header className="border-b bg-card">
        <div className="mx-auto flex max-w-3xl flex-col gap-3 px-4 py-4">
          <div className="flex items-center justify-between gap-4">
            <p className="text-sm font-medium">
              inmo24x7 · Paso {index + 1} de {wizardSteps.length}
            </p>
            {canDefer ? (
              <Button variant="ghost" size="sm" onClick={finishLater}>
                Terminar después
              </Button>
            ) : null}
          </div>
          <WizardStepper
            ariaLabel="Pasos de la configuración"
            currentId={current}
            onSelect={selectStep}
            steps={wizardSteps.map((step) => ({
              id: step.id,
              label: step.label,
              reachable: reachable.includes(step.id),
            }))}
          />
        </div>
      </header>
      <main className="mx-auto max-w-3xl px-4 py-8">
        <StepContent current={current} state={state} />
      </main>
    </div>
  );
}

function StepContent({ current, state }: { current: WizardStepId; state?: OnboardingState }) {
  switch (current) {
    case "business":
      return <BusinessStepContainer hasAccount={Boolean(state)} />;
    case "agent":
      return <AgentStepContainer />;
    case "try":
      return <TryStep />;
    case "whatsapp":
      return <WhatsAppStep />;
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
  children: React.ReactNode;
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

function BusinessStepContainer({ hasAccount }: { hasAccount: boolean }) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const settingsQuery = useQuery({
    queryKey: ["tenant-settings"],
    queryFn: fetchTenantSettings,
    enabled: hasAccount,
  });
  const mutation = useMutation({
    mutationFn: async ({ name, type }: { name: string; type: string }) => {
      if (!settingsQuery.data) {
        return signUp(name, type);
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
      navigate(stepPath("agent"));
    },
  });

  if (hasAccount && settingsQuery.isPending) {
    return null;
  }

  return (
    <StepCard
      title="Contanos de tu negocio"
      description="Con esto armamos tu agente. Te lleva un minuto."
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

function AgentStepContainer() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const setupQuery = useQuery({ queryKey: ["agent-setup"], queryFn: fetchAgentSetup });
  const meQuery = useQuery({ queryKey: ["me"], queryFn: fetchMe });
  const mutation = useMutation({
    mutationFn: async (input: Parameters<typeof saveAgentSetup>[0]) => {
      await saveAgentSetup(input);
      await advanceOnboarding("try");
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries();
      navigate(stepPath("try"));
    },
  });

  if (!setupQuery.data || !meQuery.data) {
    return null;
  }

  return (
    <StepCard title="Tu agente">
      <AgentSetupForm
        key={setupQuery.data.version}
        setup={setupQuery.data}
        businessName={meQuery.data.tenant.name}
        showIntro
        submitLabel="Guardar y probar mi agente"
        saving={mutation.isPending}
        error={
          mutation.isError
            ? apiErrorMessage(mutation.error, "No pudimos guardar tu agente. Probá de nuevo.")
            : null
        }
        onBack={() => navigate(stepPath("business"))}
        onSubmit={(input) => mutation.mutate(input)}
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

function TryStep() {
  const navigate = useNavigate();
  const setupQuery = useQuery({ queryKey: ["agent-setup"], queryFn: fetchAgentSetup });
  const advance = useAdvance("whatsapp");

  return (
    <StepCard title="Probá a tu agente">
      <div className="flex flex-col gap-6">
        <div className="rounded-lg border border-dashed p-6 text-sm text-muted-foreground">
          Muy pronto vas a poder chatear con tu agente acá.
        </div>
        {setupQuery.data ? <AgentSummary setup={setupQuery.data} /> : null}
        {advance.isError ? (
          <p className="text-sm text-destructive" role="alert">
            {apiErrorMessage(advance.error, "No pudimos avanzar. Probá de nuevo.")}
          </p>
        ) : null}
        <div className="flex flex-wrap gap-2">
          <Button variant="outline" onClick={() => navigate(stepPath("agent"))}>
            ← Ajustar el agente
          </Button>
          <Button disabled={advance.isPending} onClick={() => advance.mutate()}>
            Me gusta, conectar WhatsApp
          </Button>
        </div>
      </div>
    </StepCard>
  );
}

const whatsappSteps = [
  {
    title: "Entrá con tu cuenta de Facebook",
    text: "Necesitás una cuenta de Facebook para vincular tu negocio con WhatsApp.",
  },
  {
    title: "Elegí o creá tu cuenta de empresa en Meta",
    text: "Es la cuenta que le da permiso a tu agente para responder en tu nombre.",
  },
  {
    title: "Verificá tu número",
    text: "Te llega un código por SMS o llamada al número que quieras usar con tus clientes.",
  },
];

function WhatsAppStep() {
  const advance = useAdvance("done");

  return (
    <StepCard
      title="Conectá WhatsApp"
      description="Son tres pasos. La conexión automática llega muy pronto."
    >
      <div className="flex flex-col gap-6">
        <ol className="flex flex-col gap-3">
          {whatsappSteps.map((item, position) => (
            <li key={item.title} className="flex gap-3 text-sm">
              <span className="flex size-6 shrink-0 items-center justify-center rounded-full border text-xs">
                {position + 1}
              </span>
              <span>
                <span className="block font-medium">{item.title}</span>
                <span className="text-muted-foreground">{item.text}</span>
              </span>
            </li>
          ))}
        </ol>
        {advance.isError ? (
          <p className="text-sm text-destructive" role="alert">
            {apiErrorMessage(advance.error, "No pudimos avanzar. Probá de nuevo.")}
          </p>
        ) : null}
        <Button
          variant="outline"
          className="self-start"
          disabled={advance.isPending}
          onClick={() => advance.mutate()}
        >
          Hacerlo más tarde y seguir probando en el simulador
        </Button>
      </div>
    </StepCard>
  );
}

const checklistLabels: Record<string, string> = {
  account: "Cuenta creada",
  agent: "Agente configurado",
  whatsapp: "WhatsApp conectado",
  properties: "Propiedades cargadas",
  meta: "Empresa verificada en Meta",
};

function DoneStep({ state }: { state?: OnboardingState }) {
  const navigate = useNavigate();
  const items = state?.checklist.items ?? [];
  const ready = items.filter((item) => item.done);
  const pending = items.filter((item) => !item.done);

  return (
    <StepCard title="¡Listo!" description="Esto es lo que tenés hecho y lo que te falta.">
      <div className="flex flex-col gap-6">
        <div className="grid gap-6 sm:grid-cols-2">
          <section>
            <h3 className="mb-2 text-sm font-semibold">Listo</h3>
            <ul className="flex flex-col gap-1 text-sm">
              {ready.map((item) => (
                <li key={item.key}>✓ {checklistLabels[item.key] ?? item.key}</li>
              ))}
            </ul>
          </section>
          <section>
            <h3 className="mb-2 text-sm font-semibold">Pendiente</h3>
            <ul className="flex flex-col gap-1 text-sm text-muted-foreground">
              {pending.map((item) => (
                <li key={item.key}>{checklistLabels[item.key] ?? item.key}</li>
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
