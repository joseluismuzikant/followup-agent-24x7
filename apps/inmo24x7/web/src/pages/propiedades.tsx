import type { Property, PropertyInput } from "@followup/api-client-inmo24x7";
import {
  Badge,
  Button,
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  Input,
  MD_UP,
  Pagination,
  SegmentedControl,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
  useMediaQuery,
} from "@followup/ui";
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { fetchMe } from "../api/me";
import {
  createProperty,
  fetchProperties,
  setPropertyPublished,
  updateProperty,
} from "../api/properties";
import { ImportDialog } from "../components/properties/ImportDialog";
import { PropertyFormDialog } from "../components/properties/PropertyFormDialog";
import { apiErrorMessage } from "../lib/api-errors";
import { formatPrice, operationLabels } from "../lib/properties";
import { canEditSetup } from "../lib/setup";

type OperationFilter = "all" | "sale" | "rent";

const operationFilters = [
  { value: "all", label: "Todas" },
  { value: "sale", label: "Venta" },
  { value: "rent", label: "Alquiler" },
] as const;

/** S7: the agency's listings, which are the only ones the agent shows. A table from `md` up,
 * one card per listing below it. */
export function PropiedadesPage() {
  const queryClient = useQueryClient();
  const wide = useMediaQuery(MD_UP);
  const [search, setSearch] = useState("");
  const [operation, setOperation] = useState<OperationFilter>("all");
  const [page, setPage] = useState(1);
  const [editing, setEditing] = useState<Property | "new" | null>(null);
  const [importing, setImporting] = useState(false);
  const [rowError, setRowError] = useState<string | null>(null);

  const meQuery = useQuery({ queryKey: ["me"], queryFn: fetchMe });
  const filters = {
    search: search.trim(),
    operation: operation === "all" ? undefined : operation,
    page,
  };
  const listQuery = useQuery({
    queryKey: ["properties", filters],
    queryFn: () => fetchProperties(filters),
    placeholderData: keepPreviousData,
  });

  async function refresh() {
    await queryClient.invalidateQueries({ queryKey: ["properties"] });
    await queryClient.invalidateQueries({ queryKey: ["onboarding"] });
    await queryClient.invalidateQueries({ queryKey: ["simulator"] });
  }

  const save = useMutation({
    mutationFn: (input: PropertyInput) =>
      editing && editing !== "new" ? updateProperty(editing.id, input) : createProperty(input),
    onSuccess: async () => {
      setEditing(null);
      await refresh();
    },
  });

  const toggle = useMutation({
    mutationFn: ({ id, published }: { id: string; published: boolean }) =>
      setPropertyPublished(id, published),
    onMutate: () => setRowError(null),
    onSuccess: refresh,
    onError: (failure) =>
      setRowError(apiErrorMessage(failure, "No pudimos cambiar el estado. Probá de nuevo.")),
  });

  const canEdit = meQuery.data ? canEditSetup(meQuery.data.profile.role) : false;
  const list = listQuery.data;
  const filtering = Boolean(filters.search) || operation !== "all";

  function openForm(target: Property | "new") {
    save.reset();
    setEditing(target);
  }

  return (
    <Card>
      <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-3">
        <CardTitle>Propiedades</CardTitle>
        {canEdit ? (
          <div className="flex flex-wrap gap-2">
            <Button variant="outline" onClick={() => setImporting(true)}>
              Importar CSV o Excel
            </Button>
            <Button onClick={() => openForm("new")}>Agregar una</Button>
          </div>
        ) : null}
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <div className="flex flex-wrap items-center gap-3">
          <Input
            aria-label="Buscar por dirección o zona"
            placeholder="Buscar por dirección o zona"
            value={search}
            className="w-full sm:max-w-xs"
            onChange={(event) => {
              setSearch(event.target.value);
              setPage(1);
            }}
          />
          <SegmentedControl
            ariaLabel="Operación"
            options={operationFilters}
            value={operation}
            onChange={(value) => {
              setOperation(value);
              setPage(1);
            }}
          />
        </div>

        {rowError ? (
          <p className="text-sm text-destructive" role="alert">
            {rowError}
          </p>
        ) : null}

        {listQuery.isError ? (
          <p className="text-sm text-destructive" role="alert">
            {apiErrorMessage(listQuery.error, "No pudimos cargar tus propiedades.")}
          </p>
        ) : null}

        {list && list.total === 0 ? (
          <p className="text-sm text-muted-foreground">
            {filtering
              ? "No hay propiedades que coincidan con la búsqueda."
              : "Todavía no cargaste propiedades. Mientras tanto, tu agente muestra propiedades de ejemplo."}
          </p>
        ) : null}

        {list && list.total > 0 && !wide ? (
          <>
            <ul aria-label="Propiedades" className="flex flex-col gap-3">
              {list.items.map((item) => (
                <PropertyListItem
                  key={item.id}
                  property={item}
                  canEdit={canEdit}
                  busy={toggle.isPending && toggle.variables?.id === item.id}
                  onToggle={() =>
                    toggle.mutate({ id: item.id, published: item.status !== "published" })
                  }
                  onEdit={() => openForm(item)}
                />
              ))}
            </ul>
            <Pagination
              page={list.page}
              pageSize={list.page_size}
              total={list.total}
              onPageChange={setPage}
            />
          </>
        ) : null}

        {list && list.total > 0 && wide ? (
          <>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Propiedad</TableHead>
                  <TableHead>Operación</TableHead>
                  <TableHead>Zona</TableHead>
                  <TableHead>Precio</TableHead>
                  <TableHead>Amb.</TableHead>
                  <TableHead>Estado</TableHead>
                  <TableHead>Consultas</TableHead>
                  {canEdit ? <TableHead className="sr-only">Acciones</TableHead> : null}
                </TableRow>
              </TableHeader>
              <TableBody>
                {list.items.map((item) => (
                  <PropertyRow
                    key={item.id}
                    property={item}
                    canEdit={canEdit}
                    busy={toggle.isPending && toggle.variables?.id === item.id}
                    onToggle={() =>
                      toggle.mutate({ id: item.id, published: item.status !== "published" })
                    }
                    onEdit={() => openForm(item)}
                  />
                ))}
              </TableBody>
            </Table>
            <Pagination
              page={list.page}
              pageSize={list.page_size}
              total={list.total}
              onPageChange={setPage}
            />
          </>
        ) : null}
      </CardContent>

      <PropertyFormDialog
        open={editing !== null}
        property={editing === "new" ? null : editing}
        saving={save.isPending}
        error={
          save.isError
            ? apiErrorMessage(save.error, "No pudimos guardar la propiedad. Probá de nuevo.")
            : null
        }
        onClose={() => setEditing(null)}
        onSave={(input) => save.mutate(input)}
      />
      <ImportDialog open={importing} onClose={() => setImporting(false)} />
    </Card>
  );
}

function PropertyRow({
  property,
  canEdit,
  busy,
  onToggle,
  onEdit,
}: {
  property: Property;
  canEdit: boolean;
  busy: boolean;
  onToggle: () => void;
  onEdit: () => void;
}) {
  const published = property.status === "published";
  return (
    <TableRow>
      <TableCell>
        <div className="flex flex-col">
          <span className="font-medium">{property.title}</span>
          <span className="text-xs text-muted-foreground">
            {property.address} ·{" "}
            <a
              href={property.link}
              target="_blank"
              rel="noreferrer"
              className="underline-offset-4 hover:underline"
            >
              ver aviso
            </a>
          </span>
        </div>
      </TableCell>
      <TableCell>{operationLabels[property.operation]}</TableCell>
      <TableCell>{property.zone}</TableCell>
      <TableCell className="whitespace-nowrap">
        {formatPrice(property.price, property.currency)}
      </TableCell>
      <TableCell>{property.rooms}</TableCell>
      <TableCell>
        <div className="flex items-center gap-2">
          <Badge tone={published ? "success" : "neutral"}>
            {published ? "Publicada" : "Pausada"}
          </Badge>
          {canEdit ? (
            <Button
              variant="link"
              size="sm"
              className="px-0"
              disabled={busy}
              aria-label={`${published ? "Pausar" : "Publicar"}: ${property.title}`}
              onClick={onToggle}
            >
              {published ? "Pausar" : "Publicar"}
            </Button>
          ) : null}
        </div>
      </TableCell>
      <TableCell>{property.inquiries}</TableCell>
      {canEdit ? (
        <TableCell>
          <Button
            variant="ghost"
            size="sm"
            aria-label={`Editar: ${property.title}`}
            onClick={onEdit}
          >
            Editar
          </Button>
        </TableCell>
      ) : null}
    </TableRow>
  );
}

/** A listing on a phone: what the table's columns say, and the same two actions. */
function PropertyListItem({
  property,
  canEdit,
  busy,
  onToggle,
  onEdit,
}: {
  property: Property;
  canEdit: boolean;
  busy: boolean;
  onToggle: () => void;
  onEdit: () => void;
}) {
  const published = property.status === "published";
  return (
    <li className="flex flex-col gap-2 rounded-lg border bg-card p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="flex min-w-0 flex-col">
          <span className="font-medium">{property.title}</span>
          <span className="text-sm text-muted-foreground">{property.address}</span>
        </div>
        <Badge tone={published ? "success" : "neutral"}>
          {published ? "Publicada" : "Pausada"}
        </Badge>
      </div>
      <p className="text-sm">
        <span className="font-semibold">{formatPrice(property.price, property.currency)}</span>
        <span className="text-muted-foreground">
          {" "}
          · {operationLabels[property.operation]} · {property.zone} · {property.rooms} amb.
        </span>
      </p>
      <div className="flex flex-wrap items-center justify-between gap-2 text-sm">
        <span className="text-muted-foreground">
          {property.inquiries === 1 ? "1 consulta" : `${property.inquiries} consultas`} ·{" "}
          <a
            href={property.link}
            target="_blank"
            rel="noreferrer"
            className="text-brand underline underline-offset-4"
          >
            ver aviso
          </a>
        </span>
        {canEdit ? (
          <div className="flex gap-2">
            <Button
              variant="outline"
              size="sm"
              disabled={busy}
              aria-label={`${published ? "Pausar" : "Publicar"}: ${property.title}`}
              onClick={onToggle}
            >
              {published ? "Pausar" : "Publicar"}
            </Button>
            <Button
              variant="outline"
              size="sm"
              aria-label={`Editar: ${property.title}`}
              onClick={onEdit}
            >
              Editar
            </Button>
          </div>
        ) : null}
      </div>
    </li>
  );
}
