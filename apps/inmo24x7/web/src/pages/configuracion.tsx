import { Card, CardContent, CardHeader, CardTitle } from "@followup/ui";

export function ConfiguracionPage() {
  return (
    <Card className="max-w-xl">
      <CardHeader>
        <CardTitle>Configuración</CardTitle>
      </CardHeader>
      <CardContent>
        <p className="text-sm text-muted-foreground">Acá van los ajustes de tu cuenta.</p>
      </CardContent>
    </Card>
  );
}
