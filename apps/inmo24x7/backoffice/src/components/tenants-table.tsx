import type { Tenant } from "@followup/api-client-inmo24x7";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@followup/ui";

interface TenantsTableProps {
  tenants: Tenant[];
}

const dateFormatter = new Intl.DateTimeFormat("es-AR", {
  dateStyle: "medium",
  timeStyle: "short",
});

export function TenantsTable({ tenants }: TenantsTableProps) {
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Negocio</TableHead>
          <TableHead>Identificador</TableHead>
          <TableHead>Creado</TableHead>
          <TableHead>
            <span className="sr-only">Acciones</span>
          </TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {tenants.map((tenant) => (
          <TableRow key={tenant.id}>
            <TableCell className="font-medium">{tenant.name}</TableCell>
            <TableCell className="font-mono text-xs text-muted-foreground">
              {tenant.slug}
            </TableCell>
            <TableCell className="text-muted-foreground">
              {dateFormatter.format(new Date(tenant.created_at))}
            </TableCell>
            <TableCell className="text-right">
              <a
                href={`/simulador?negocio=${tenant.id}`}
                className="text-sm font-medium text-primary underline-offset-4 hover:underline"
              >
                Probar su agente
              </a>
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}
