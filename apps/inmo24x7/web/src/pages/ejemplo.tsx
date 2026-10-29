import { Card, CardDescription, CardHeader, CardTitle } from "@followup/ui";

/** Where sample property cards link to. Real listings link to their own pages (Day 4). */
export function EjemploPage() {
  return (
    <main className="mx-auto flex min-h-screen max-w-lg items-center p-6">
      <Card>
        <CardHeader>
          <CardTitle>Propiedad de ejemplo</CardTitle>
          <CardDescription>
            Esta propiedad es de ejemplo y sirve para probar a tu agente. Cuando subas tu
            listado, el agente va a mostrar tus propiedades con sus fotos reales.
          </CardDescription>
        </CardHeader>
      </Card>
    </main>
  );
}
