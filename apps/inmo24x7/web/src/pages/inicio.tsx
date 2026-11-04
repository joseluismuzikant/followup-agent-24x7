import type { Dashboard } from "@followup/api-client-inmo24x7";
import {
  Badge,
  Button,
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  KpiCard,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@followup/ui";
import { useQuery } from "@tanstack/react-query";
import { Link, useNavigate } from "react-router";

import { fetchDashboard } from "../api/dashboard";
import { fetchOnboarding } from "../api/onboarding";
import { fetchWhatsAppStatus } from "../api/whatsapp";
import { LeadStatusBadge } from "../components/inbox/LeadStatusBadge";
import { SetupChecklist } from "../components/SetupChecklist";
import { ConnectionErrorBanner } from "../components/whatsapp/ConnectionErrorBanner";
import { apiErrorMessage } from "../lib/api-errors";
import { age, formatDuration } from "../lib/leads";

export function InicioPage() {
  const onboardingQuery = useQuery({
    queryKey: ["onboarding"],
    queryFn: fetchOnboarding,
    retry: false,
  });
  const whatsappQuery = useQuery({
    queryKey: ["whatsapp"],
    queryFn: fetchWhatsAppStatus,
    retry: false,
  });
  const dashboardQuery = useQuery({ queryKey: ["dashboard"], queryFn: fetchDashboard });
  const whatsapp = whatsappQuery.data;
  const dashboard = dashboardQuery.data;

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold">
            {dashboard ? `Hola, ${dashboard.business_name}` : "Hola"}
          </h1>
          <p className="text-sm text-muted-foreground">Esto pasó esta semana con tu agente.</p>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          {whatsapp?.status === "connected" ? (
            <Badge tone="success">
              Agente activo
              {whatsapp.display_phone_number ? ` · ${whatsapp.display_phone_number}` : ""}
            </Badge>
          ) : null}
          <Button asChild>
            <Link to="/probar">Probar el agente</Link>
          </Button>
        </div>
      </div>
      <ConnectionErrorBanner status={whatsapp} />
      {onboardingQuery.data ? (
        <SetupChecklist
          checklist={onboardingQuery.data.checklist}
          wizardUnfinished={!onboardingQuery.data.finished}
        />
      ) : null}
      {dashboardQuery.isError ? (
        <p className="text-sm text-destructive" role="alert">
          {apiErrorMessage(dashboardQuery.error, "No pudimos cargar los números de la semana.")}
        </p>
      ) : null}
      {dashboard ? <WeekSummary dashboard={dashboard} /> : null}
    </div>
  );
}

function WeekSummary({ dashboard }: { dashboard: Dashboard }) {
  const navigate = useNavigate();
  if (dashboard.received.total === 0 && dashboard.attention_today.length === 0) {
    return (
      <Card className="max-w-xl">
        <CardHeader>
          <CardTitle>Esta semana</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">
            Todavía no hay consultas esta semana. Probá tu agente o conectá WhatsApp.
          </p>
        </CardContent>
      </Card>
    );
  }
  const outOfHours = dashboard.received.out_of_hours;
  return (
    <>
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <KpiCard
          label="Consultas recibidas"
          value={dashboard.received.total}
          hint={`${outOfHours} fuera de horario`}
        />
        <KpiCard label="Calificadas" value={dashboard.qualified} hint="Con zona y presupuesto" />
        <KpiCard
          label="Visitas agendadas"
          value={dashboard.visits.total}
          hint={`El número que importa · ${dashboard.visits.confirmed} confirmadas`}
        />
        <KpiCard
          label="Respuesta promedio"
          value={formatDuration(dashboard.response_time_seconds)}
          hint="A cualquier hora"
        />
      </div>
      <Card>
        <CardHeader className="flex flex-row items-center justify-between gap-3">
          <CardTitle>Para atender hoy</CardTitle>
          <Button asChild variant="ghost" size="sm">
            <Link to="/consultas?tab=attention">Ver todas</Link>
          </Button>
        </CardHeader>
        <CardContent>
          {dashboard.attention_today.length === 0 ? (
            <p className="text-sm text-muted-foreground">No hay consultas esperando a tu equipo.</p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Interesado</TableHead>
                  <TableHead>Busca</TableHead>
                  <TableHead>Estado</TableHead>
                  <TableHead>Hace</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {dashboard.attention_today.map((lead) => (
                  <TableRow
                    key={lead.id}
                    className="cursor-pointer"
                    onClick={() => void navigate(`/consultas?lead=${lead.id}`)}
                  >
                    <TableCell>
                      <Link
                        to={`/consultas?lead=${lead.id}`}
                        className="font-medium underline-offset-4 hover:underline"
                        onClick={(event) => event.stopPropagation()}
                      >
                        {lead.name ?? "Sin nombre todavía"}
                      </Link>
                    </TableCell>
                    <TableCell className="text-muted-foreground">
                      {lead.looking_for || "—"}
                    </TableCell>
                    <TableCell>
                      <LeadStatusBadge status={lead.status} />
                    </TableCell>
                    <TableCell className="whitespace-nowrap text-muted-foreground">
                      {age(lead.created_at)}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </>
  );
}
