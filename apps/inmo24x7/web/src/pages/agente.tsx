import { Card, CardContent, CardHeader, CardTitle } from "@followup/ui";

export function AgentePage() {
  return (
    <Card className="max-w-xl">
      <CardHeader>
        <CardTitle>Agente</CardTitle>
      </CardHeader>
      <CardContent>
        <p className="text-sm text-muted-foreground">
          Acá vas a poder configurar a tu agente.
        </p>
      </CardContent>
    </Card>
  );
}
