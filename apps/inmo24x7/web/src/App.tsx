import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  PanelLayout,
} from "@followup/ui";
import { useQuery } from "@tanstack/react-query";

import { fetchReadiness } from "./api/health";
import { apiErrorMessage } from "./lib/api-errors";

const navItems = [
  { label: "Inicio", href: "/", active: true },
  { label: "Conversaciones", href: "#" },
  { label: "Propiedades", href: "#" },
  { label: "Configuración", href: "#" },
];

const features = [
  {
    title: "Seguimiento automático",
    description: "Tu agente retoma cada conversación hasta llegar a una visita.",
  },
  {
    title: "Consultas ordenadas",
    description: "Cada interesado queda calificado con los datos que importan.",
  },
  {
    title: "Siempre disponible",
    description: "Atiende consultas por WhatsApp a toda hora, sin perder el tono.",
  },
];

function ServiceStatus() {
  const readinessQuery = useQuery({
    queryKey: ["readiness"],
    queryFn: fetchReadiness,
    retry: 1,
  });

  if (readinessQuery.isPending) {
    return (
      <span className="text-sm text-muted-foreground" aria-live="polite">
        Verificando servicio...
      </span>
    );
  }

  if (readinessQuery.isError) {
    return (
      <span
        className="text-sm text-destructive"
        title={apiErrorMessage(readinessQuery.error, "Servicio no disponible.")}
        aria-live="polite"
      >
        Servicio no disponible
      </span>
    );
  }

  return (
    <span className="flex items-center gap-2 text-sm text-muted-foreground" aria-live="polite">
      <span className="size-2 rounded-full bg-emerald-500" aria-hidden="true" />
      Servicio disponible
    </span>
  );
}

export function App() {
  return (
    <PanelLayout
      productName="inmo24x7"
      areaName="Panel"
      title="Hola"
      description="Este es el espacio donde vas a hacer crecer tu inmobiliaria."
      navItems={navItems}
      action={<ServiceStatus />}
    >
      <div className="grid gap-6 xl:grid-cols-[minmax(0,1.5fr)_minmax(280px,1fr)]">
        <Card>
          <CardHeader>
            <CardTitle>Tu panel está listo</CardTitle>
            <CardDescription>
              Muy pronto vas a poder configurar tu agente y conectar WhatsApp desde acá.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="grid gap-4 sm:grid-cols-3">
              {features.map((feature) => (
                <div key={feature.title} className="rounded-lg border bg-muted/40 p-4">
                  <p className="text-sm font-semibold">{feature.title}</p>
                  <p className="mt-1 text-sm leading-relaxed text-muted-foreground">
                    {feature.description}
                  </p>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>

        <Card className="bg-primary text-primary-foreground">
          <CardHeader>
            <CardTitle>Un agente, no un chatbot</CardTitle>
            <CardDescription className="text-primary-foreground/75">
              inmo24x7 sigue cada oportunidad con un objetivo claro: coordinar la
              próxima visita.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <p className="text-sm leading-relaxed text-primary-foreground/90">
              Sin bandejas interminables ni mensajes que quedan sin respuesta. El
              agente se ocupa del seguimiento y te avisa cuando necesita una persona.
            </p>
          </CardContent>
        </Card>
      </div>
    </PanelLayout>
  );
}
