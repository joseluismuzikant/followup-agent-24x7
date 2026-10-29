import { SimulatorView } from "../components/SimulatorView";

export function ProbarPage() {
  return (
    <div className="flex flex-col gap-4">
      <p className="text-sm text-muted-foreground">
        Escribile como si fueras un cliente. Así va a responder en WhatsApp.
      </p>
      <SimulatorView />
    </div>
  );
}
