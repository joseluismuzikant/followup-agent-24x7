import { Card, CardContent, CardHeader, CardTitle } from "@followup/ui";

export function ConsultasPage() {
  return (
    <Card className="max-w-xl">
      <CardHeader>
        <CardTitle>Consultas</CardTitle>
      </CardHeader>
      <CardContent>
        <p className="text-sm text-muted-foreground">Todavía no hay consultas.</p>
      </CardContent>
    </Card>
  );
}
