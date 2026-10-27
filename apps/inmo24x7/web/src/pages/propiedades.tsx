import { Card, CardContent, CardHeader, CardTitle } from "@followup/ui";

export function PropiedadesPage() {
  return (
    <Card className="max-w-xl">
      <CardHeader>
        <CardTitle>Propiedades</CardTitle>
      </CardHeader>
      <CardContent>
        <p className="text-sm text-muted-foreground">Todavía no cargaste propiedades.</p>
      </CardContent>
    </Card>
  );
}
