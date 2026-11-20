import type { BusinessDetail, PrivacyContact } from "@followup/api-client-inmo24x7";
import {
  Badge,
  Button,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  Dialog,
  FormField,
  Input,
} from "@followup/ui";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useId, useState } from "react";

import {
  closeBusiness,
  deleteContactData,
  fetchClosureSummary,
  findContacts,
  setContactDoNotContact,
} from "../api/backoffice";
import { apiErrorMessage } from "../lib/api-errors";
import { formatCount, formatDateTime } from "../lib/labels";

/** Business page → "Datos y privacidad": a person's or the whole agency's data deletion
 * (www.inmo24x7.com/eliminacion-de-datos) and "no contactar" for requests that arrive by
 * email or phone. */
export function PrivacyCard({
  business,
  queryKey,
}: {
  business: BusinessDetail;
  queryKey: readonly unknown[];
}) {
  const [closing, setClosing] = useState(false);
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Datos y privacidad</CardTitle>
        <CardDescription>
          Pedidos de baja y de eliminación que llegan a contacto@inmo24x7.com.
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-6 text-sm">
        <ContactsSection tenantId={business.id} />
        <DoNotContactSection tenantId={business.id} />
        <section aria-label="Cerrar cuenta" className="flex flex-col gap-2 border-t pt-4">
          <h3 className="font-semibold">Cerrar cuenta y eliminar datos</h3>
          <p className="text-muted-foreground">
            Borra todo el negocio: propiedades, consultas, conversaciones, usuarios y la
            conexión de WhatsApp. No se puede deshacer.
          </p>
          <Button
            variant="destructive"
            className="self-start"
            disabled={business.closing}
            onClick={() => setClosing(true)}
          >
            {business.closing ? "Cierre en curso" : "Cerrar cuenta y eliminar datos"}
          </Button>
        </section>
      </CardContent>
      {closing ? (
        <CloseAccountDialog
          business={business}
          queryKey={queryKey}
          onClose={() => setClosing(false)}
        />
      ) : null}
    </Card>
  );
}

function ContactsSection({ tenantId }: { tenantId: string }) {
  const queryClient = useQueryClient();
  const inputId = useId();
  const [draft, setDraft] = useState("");
  const [query, setQuery] = useState("");
  const [deleting, setDeleting] = useState<PrivacyContact | null>(null);
  const [done, setDone] = useState<string | null>(null);
  const contacts = useQuery({
    queryKey: ["privacy-contacts", tenantId, query],
    queryFn: () => findContacts(tenantId, query),
    enabled: query.length > 0,
  });
  const toggle = useMutation({
    mutationFn: (contact: PrivacyContact) =>
      setContactDoNotContact(tenantId, contact.phone, !contact.do_not_contact),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["privacy-contacts", tenantId] }),
  });

  return (
    <section aria-label="Eliminar datos de un contacto" className="flex flex-col gap-3">
      <h3 className="font-semibold">Eliminar datos de un contacto</h3>
      <form
        className="flex flex-wrap items-end gap-2"
        onSubmit={(event) => {
          event.preventDefault();
          setDone(null);
          setQuery(draft.trim());
        }}
      >
        <FormField label="Teléfono o nombre" htmlFor={inputId} className="min-w-0 flex-1">
          <Input
            id={inputId}
            value={draft}
            maxLength={100}
            placeholder="11 5555-0188 o Ana Pérez"
            onChange={(event) => setDraft(event.target.value)}
          />
        </FormField>
        <Button type="submit" variant="outline" disabled={!draft.trim()}>
          Buscar
        </Button>
      </form>
      {done ? (
        <p className="text-sm" aria-live="polite">
          {done}
        </p>
      ) : null}
      {contacts.isError ? (
        <p className="text-destructive" role="alert">
          {apiErrorMessage(contacts.error, "No pudimos buscar los contactos.")}
        </p>
      ) : null}
      {contacts.data && contacts.data.length === 0 ? (
        <p className="text-muted-foreground">No hay contactos de WhatsApp con ese teléfono o nombre.</p>
      ) : null}
      {contacts.data && contacts.data.length > 0 ? (
        <ul aria-label="Contactos encontrados" className="flex flex-col gap-2">
          {contacts.data.map((contact) => (
            <li key={contact.wa_id} className="flex flex-col gap-2 rounded-md border p-3">
              <span className="flex flex-wrap items-center gap-2">
                <span className="font-medium">{contact.phone}</span>
                {contact.names.length ? (
                  <span className="text-muted-foreground">{contact.names.join(", ")}</span>
                ) : null}
                {contact.do_not_contact ? <Badge tone="danger">No contactar</Badge> : null}
              </span>
              <span className="text-muted-foreground">
                {formatCount(contact.leads)} {contact.leads === 1 ? "consulta" : "consultas"} ·{" "}
                {formatCount(contact.messages)} mensajes · {formatCount(contact.visits)}{" "}
                {contact.visits === 1 ? "visita" : "visitas"}
                {contact.last_activity_at
                  ? ` · último mensaje ${formatDateTime(contact.last_activity_at)}`
                  : ""}
              </span>
              <span className="flex flex-wrap gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  disabled={toggle.isPending}
                  onClick={() => toggle.mutate(contact)}
                >
                  {contact.do_not_contact ? "Quitar «no contactar»" : "Marcar como no contactar"}
                </Button>
                <Button variant="destructive" size="sm" onClick={() => setDeleting(contact)}>
                  Eliminar datos
                </Button>
              </span>
            </li>
          ))}
        </ul>
      ) : null}
      {toggle.isError ? (
        <p className="text-destructive" role="alert">
          {apiErrorMessage(toggle.error, "No pudimos cambiarlo.")}
        </p>
      ) : null}
      {deleting ? (
        <DeleteContactDialog
          tenantId={tenantId}
          contact={deleting}
          onClose={() => setDeleting(null)}
          onDeleted={(message) => {
            setDeleting(null);
            setDone(message);
            void queryClient.invalidateQueries({ queryKey: ["privacy-contacts", tenantId] });
          }}
        />
      ) : null}
    </section>
  );
}

function DeleteContactDialog({
  tenantId,
  contact,
  onClose,
  onDeleted,
}: {
  tenantId: string;
  contact: PrivacyContact;
  onClose: () => void;
  onDeleted: (message: string) => void;
}) {
  const inputId = useId();
  const [typed, setTyped] = useState("");
  const remove = useMutation({
    mutationFn: () => deleteContactData(tenantId, contact.wa_id, typed),
    onSuccess: (counts) =>
      onDeleted(
        `Listo: eliminamos ${counts.leads} ${counts.leads === 1 ? "consulta" : "consultas"} y ${counts.messages} mensajes de ${contact.phone}.`,
      ),
  });
  return (
    <Dialog open title={`Eliminar datos de ${contact.phone}`} onClose={onClose}>
      <form
        className="flex flex-col gap-4 text-sm"
        onSubmit={(event) => {
          event.preventDefault();
          remove.mutate();
        }}
      >
        <div className="flex flex-col gap-1">
          <p className="font-medium">Se borra, solo en este negocio:</p>
          <ul className="list-disc pl-5">
            <li>
              {contact.leads} {contact.leads === 1 ? "consulta" : "consultas"}, con su historial,
              condiciones y {contact.visits} {contact.visits === 1 ? "visita" : "visitas"}
            </li>
            <li>la conversación ({contact.messages} mensajes) y lo que el agente sabía</li>
            <li>los mensajes de WhatsApp y los avisos pendientes de esa persona</li>
            <li>el registro de envíos a Tokko y al webhook</li>
          </ul>
          <p className="text-muted-foreground">
            Se conserva el «no contactar» si lo pidió, para no volver a escribirle, y el
            consumo del agente sin vínculo con la conversación. Las copias de seguridad lo
            pierden en su próxima rotación.
          </p>
          <p className="text-muted-foreground">
            Lo que ya se envió a Tokko o al webhook queda en esos sistemas.
          </p>
        </div>
        <FormField
          label="Escribí el teléfono para confirmar"
          htmlFor={inputId}
          hint={contact.phone}
        >
          <Input
            id={inputId}
            value={typed}
            maxLength={40}
            autoComplete="off"
            onChange={(event) => setTyped(event.target.value)}
          />
        </FormField>
        {remove.isError ? (
          <p className="text-destructive" role="alert">
            {apiErrorMessage(remove.error, "No pudimos eliminar los datos.")}
          </p>
        ) : null}
        <div className="flex justify-end gap-2">
          <Button type="button" variant="outline" onClick={onClose}>
            Volver
          </Button>
          <Button type="submit" variant="destructive" disabled={!typed.trim() || remove.isPending}>
            {remove.isPending ? "Eliminando…" : "Eliminar datos"}
          </Button>
        </div>
      </form>
    </Dialog>
  );
}

function DoNotContactSection({ tenantId }: { tenantId: string }) {
  const inputId = useId();
  const [phone, setPhone] = useState("");
  const [done, setDone] = useState<string | null>(null);
  const mark = useMutation({
    mutationFn: () => setContactDoNotContact(tenantId, phone, true),
    onSuccess: (result) => {
      setDone(`${result.phone} no va a recibir mensajes de este negocio.`);
      setPhone("");
    },
  });
  return (
    <section aria-label="No contactar un número" className="flex flex-col gap-2 border-t pt-4">
      <h3 className="font-semibold">No contactar un número</h3>
      <p className="text-muted-foreground">
        Para una «BAJA» que llega por email o por teléfono, aunque ese número nunca haya escrito.
        Si la persona vuelve a escribir, se reactiva sola.
      </p>
      <form
        className="flex flex-wrap items-end gap-2"
        onSubmit={(event) => {
          event.preventDefault();
          setDone(null);
          mark.mutate();
        }}
      >
        <FormField label="Teléfono" htmlFor={inputId} className="min-w-0 flex-1">
          <Input
            id={inputId}
            value={phone}
            maxLength={40}
            inputMode="tel"
            placeholder="+54 9 11 5555-0188"
            onChange={(event) => setPhone(event.target.value)}
          />
        </FormField>
        <Button type="submit" variant="outline" disabled={!phone.trim() || mark.isPending}>
          Marcar como no contactar
        </Button>
      </form>
      {done ? <p aria-live="polite">{done}</p> : null}
      {mark.isError ? (
        <p className="text-destructive" role="alert">
          {apiErrorMessage(mark.error, "No pudimos marcarlo.")}
        </p>
      ) : null}
    </section>
  );
}

function CloseAccountDialog({
  business,
  queryKey,
  onClose,
}: {
  business: BusinessDetail;
  queryKey: readonly unknown[];
  onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const inputId = useId();
  const [typed, setTyped] = useState("");
  const summary = useQuery({
    queryKey: ["closure", business.id],
    queryFn: () => fetchClosureSummary(business.id),
  });
  const close = useMutation({
    mutationFn: () => closeBusiness(business.id, typed),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey });
      onClose();
    },
  });
  const data = summary.data;
  return (
    <Dialog open title={`Cerrar ${business.name}`} onClose={onClose}>
      <form
        className="flex flex-col gap-4 text-sm"
        onSubmit={(event) => {
          event.preventDefault();
          close.mutate();
        }}
      >
        {data ? (
          <div className="flex flex-col gap-1">
            <p className="font-medium">Se borra todo, sin vuelta atrás:</p>
            <ul aria-label="Lo que se borra" className="list-disc pl-5">
              <li>{data.properties} propiedades y sus importaciones</li>
              <li>
                {data.leads} consultas y {data.conversations} conversaciones ({data.messages}{" "}
                mensajes)
              </li>
              <li>
                {data.users} {data.users === 1 ? "usuario" : "usuarios"}
                {data.users_kept
                  ? ` (${data.users_kept} sigue${data.users_kept === 1 ? "" : "n"} entrando a su otro negocio)`
                  : ""}
              </li>
              <li>
                la configuración del agente, las condiciones y
                {data.whatsapp_connected
                  ? " la conexión de WhatsApp: nuestra app deja de recibir sus mensajes en Meta"
                  : " los datos de WhatsApp"}
              </li>
              <li>
                las integraciones y sus claves (Tokko, webhook, botón de la web), las
                sincronizaciones y el registro de envíos
              </li>
            </ul>
            <p className="text-muted-foreground">
              El negocio se detiene en el momento y los datos se borran en los próximos
              minutos. Queda solo el consumo del agente para la facturación, sin datos
              personales.
            </p>
            <p className="text-muted-foreground">
              Lo que ya se envió a Tokko o al webhook queda en esos sistemas.
            </p>
          </div>
        ) : (
          <p className="text-muted-foreground">Cargando lo que se borra…</p>
        )}
        <FormField
          label="Escribí el nombre del negocio para confirmar"
          htmlFor={inputId}
          hint={business.name}
        >
          <Input
            id={inputId}
            value={typed}
            maxLength={200}
            autoComplete="off"
            onChange={(event) => setTyped(event.target.value)}
          />
        </FormField>
        {close.isError ? (
          <p className="text-destructive" role="alert">
            {apiErrorMessage(close.error, "No pudimos cerrar la cuenta.")}
          </p>
        ) : null}
        <div className="flex justify-end gap-2">
          <Button type="button" variant="outline" onClick={onClose}>
            Volver
          </Button>
          <Button type="submit" variant="destructive" disabled={!typed.trim() || close.isPending}>
            {close.isPending ? "Cerrando…" : "Cerrar cuenta y eliminar datos"}
          </Button>
        </div>
      </form>
    </Dialog>
  );
}
