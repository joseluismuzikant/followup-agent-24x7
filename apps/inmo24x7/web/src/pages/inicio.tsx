import { Card, CardContent, CardHeader, CardTitle } from "@followup/ui";

export function InicioPage() {
  return (
    <Card className="max-w-xl">
      <CardHeader>
        <CardTitle>Hola</CardTitle>
      </CardHeader>
      <CardContent>
        <p className="text-sm text-muted-foreground">
          Tu panel está listo. Muy pronto vas a poder configurar tu agente.
        </p>
      </CardContent>
    </Card>
  );
}
