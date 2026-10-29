import type { Tenant } from "@followup/api-client-inmo24x7";
import { Input, cn } from "@followup/ui";

interface TenantPickerProps {
  tenants: readonly Tenant[];
  query: string;
  onQueryChange: (query: string) => void;
  selectedId: string | null;
  onSelect: (tenantId: string) => void;
}

function normalize(text: string): string {
  return text
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase();
}

export function filterTenants<T extends { name: string; slug: string }>(
  tenants: readonly T[],
  query: string,
): T[] {
  const wanted = normalize(query.trim());
  if (!wanted) {
    return [...tenants];
  }
  return tenants.filter(
    (tenant) => normalize(tenant.name).includes(wanted) || tenant.slug.includes(wanted),
  );
}

/** A searchable list of businesses. Controlled: the page owns the query and selection. */
export function TenantPicker({
  tenants,
  query,
  onQueryChange,
  selectedId,
  onSelect,
}: TenantPickerProps) {
  const visible = filterTenants(tenants, query);

  return (
    <div className="flex flex-col gap-3">
      <Input
        aria-label="Buscar negocio"
        placeholder="Buscar negocio…"
        value={query}
        onChange={(event) => onQueryChange(event.target.value)}
      />
      {visible.length === 0 ? (
        <p className="text-sm text-muted-foreground">No encontramos negocios con ese nombre.</p>
      ) : (
        <ul className="flex max-h-96 flex-col gap-1 overflow-y-auto">
          {visible.map((tenant) => (
            <li key={tenant.id}>
              <button
                type="button"
                aria-pressed={tenant.id === selectedId}
                onClick={() => onSelect(tenant.id)}
                className={cn(
                  "w-full rounded-md px-3 py-2 text-left text-sm transition-colors",
                  tenant.id === selectedId
                    ? "bg-primary/10 font-medium text-primary"
                    : "hover:bg-muted",
                )}
              >
                {tenant.name}
                <span className="block font-mono text-xs text-muted-foreground">{tenant.slug}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
