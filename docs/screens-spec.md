# Screen specification

One section per screen from the product prototypes. Each section has three parts:

- **What the user sees** — layout and content, with Spanish UI copy shown verbatim.
- **What must work** — behavior, API, and data requirements.
- **Roadmap day** — the responsible day, or an explicit **Post-MVP** assignment.

Everything here is written in English; only UI copy is Spanish. Screens not mocked but
present in the navigation get a short derived spec at the end.

---

## inmo24x7

### S1 — Ingreso

**What the user sees**

- Hero copy.
- A **"Continuar con Google"** button.
- An email field with an **"Enviarme un link para entrar"** button (magic link).
- Footer links to **Términos** and **Política de privacidad**.

**What must work**

- Supabase Auth via Google OAuth and magic link, never passwords.
- Sign-up creates the tenant, the owner profile, and a trial plan in one use case.
- After authentication the user lands on their own tenant panel, never someone else's.
- Links to Términos and Política de privacidad are visible and route to placeholder pages.

**Roadmap day:** Day 1 (links and auth); **Post-MVP** (page content for Términos and
Política de privacidad).

---

### S2 — Onboarding

**What the user sees**

A five-step wizard with a progress indicator:

1. Tu negocio
2. Tu agente
3. Probalo
4. WhatsApp
5. Listo

Header options include **"Terminar después"** so the wizard can be resumed at the same step.

Only step 2 is mocked:

- Agent name, default **Sofía**.
- Live preview of the greeting, e.g. **«Hola, soy Sofía, de Inmobiliaria Sur»**.
- Tone selector: **Cercano**, **Profesional**, **Formal**.
- Editable list of qualification questions: **comprar o alquilar**, **zona**,
  **presupuesto**, **crédito hipotecario aprobado**, **cantidad de ambientes**, and
  **"+ Agregar una pregunta"**.
- Team hours presets: **L-V 9-18**, **L-S 9-13**.
- Lead notification email field.
- After-hours behavior: the agent keeps answering and proposes a visit for the team to confirm.
- Buttons **"Usar lo recomendado"** and **"Guardar y probar mi agente"**.

Steps 1 and 5 are not mocked.

**What must work**

- Wizard persists per-step state in Tenancy so "Terminar después" resumes at the same step.
- Business name and type are captured in step 1 (not mocked, but required).
- Agent configuration is stored in Tenancy and versioned.
- Qualification questions are data that the graph reads, not hard-coded logic.
- Tone, hours, questions, and notification email are all editable and saved atomically.
- Step 5 shows a test link or QR to send the first message.

**Roadmap day:** Day 2 (full wizard and persisted config); Day 5 (email notification and
WhatsApp send); Day 7 (the finished "Listo" state when WhatsApp is connected).

---

### S3 — Probalo (chat simulator)

**What the user sees**

- A chat with the agent, plus a header and a **"Reiniciar"** button.
- Property cards the agent sends: title, address, price, **"Ver fotos"**, and a note when
  the property is over budget.
- A side panel titled **"Lo que el agente ya sabe"** listing operation, zone, budget,
  rooms, name, and contact. Contact shows **Pendiente** until it is known.
- A banner **"Está usando propiedades de ejemplo"** with a **"Subir mis propiedades"** button.
- Buttons **"Ajustar el agente"** and **"Me gusta, conectar WhatsApp"**.

**What must work**

- The simulator drives the same agent runtime as WhatsApp; only the channel differs.
- Conversation state lives in the LangGraph Postgres checkpointer and survives restarts.
- "Lo que el agente ya sabe" renders the structured graph state from the API.
- Reiniciar starts a new thread.
- Sample properties are seeded per tenant until the agency imports its own.
- Property cards use real links and mark over-budget properties without inventing links.
- "Ajustar el agente" opens the saved agent configuration.
- "Me gusta, conectar WhatsApp" leads into the connection flow.

**Roadmap day:** Day 3 (simulator and graph state); Day 4 (real search and qualification);
Day 7 (WhatsApp connection from the simulator).

---

### S4 — Conectar WhatsApp

**What the user sees**

- Three explained steps.
- A **"Conectar WhatsApp"** button that launches Meta Embedded Signup.
- A help link for creating a business Facebook account.
- **"Hacerlo más tarde y seguir probando"**.
- A connection status card with: **Cuenta de Meta**, **Número verificado**,
  **Recepción de mensajes**, **Mensaje de prueba**.
- A **"Pendiente en Meta"** state reminding the user to verify the business and add a
  payment method, with links.
- Meta errors translated to Spanish, e.g. a number already registered in another account.

**What must work**

- Embedded Signup exchanges the code for a business token, stores WABA id and phone number
  id, registers the number, subscribes webhooks, and sends a test message.
- Connection state is shown as connected, pending verification, or action required.
- Meta error codes are stored and translated into clear Spanish next steps.
- "Hacerlo más tarde" leaves the wizard resumable at the WhatsApp step.
- Manual connection fallback exists in the backoffice for cases that cannot use Embedded Signup.

**Roadmap day:** Day 7; Day 5 (test/manual connection so messaging can be exercised first).

---

### S5 — Panel Inicio

**What the user sees**

- Sidebar: **Inicio**, **Consultas**, **Propiedades**, **Agente**, **Configuración**.
- A badge **"Agente activo"** plus the WhatsApp number.
- **"Probar el agente"** button.
- Setup checklist **"3 de 5 listos"** with: cuenta, agente, WhatsApp, propiedades,
  verificar empresa en Meta.
- KPIs for this week: consultas recibidas (with how many out of hours), calificadas (with
  zone and budget), visitas agendadas, and respuesta promedio.
- A table titled **"Para atender hoy"** with columns: name or phone, what they are looking
  for, status, and age.
- Statuses: **Calificando**, **Visita propuesta**, **Pidió hablar con alguien**,
  **Visita confirmada**.

**What must work**

- The dashboard is tenant-scoped and aggregates leads, visits, and response times.
- Checklist reflects onboarding progress and Meta business verification state.
- Out-of-hours is computed from the agent's configured hours.
- "Para atender hoy" is the actionable inbox subset, ordered by urgency/age.
- The active badge reflects WhatsApp connection health and a live number.

**Roadmap day:** Day 1 (shell and sidebar); Day 2 (checklist); Day 4 (lead statuses);
Day 6 (KPIs and the today table); Day 7 (verificación de empresa en Meta state).

---

### S6 — Panel Consultas

**What the user sees**

- Tabs: **"Para atender · N"**, **Visitas**, **Todas**.
- Search by name, zone, or phone.
- **"Exportar CSV"**.
- Detail pane with: name, phone, channel.
- **"Tomar la conversación"** for human takeover, where the agent pauses and the team
  replies from the panel.
- **"Confirmar visita"**, which sends the confirmation to the lead.
- Visit card with address, day and time, and awaiting-confirmation state.
- Qualification data, including **Garantía**.
- Full transcript.
- System events, e.g. **"El agente derivó la consulta a tu equipo"**.

**What must work**

- Takeover pauses the agent for that thread and routes human replies through WhatsApp.
- Confirming a visit sends the confirmation and updates the lead status.
- Tabs, search, and CSV export operate over the tenant's leads.
- The transcript includes agent messages, lead messages, and system events.
- Qualification fields come from structured graph state, never free-text parsing.

**Roadmap day:** Day 6; Day 4 (lead creation and qualification data); Day 5 (messages and
statuses via WhatsApp).

---

### S7 — Panel Propiedades

**What the user sees**

- **"Agregar una"** for manual creation and **"Importar CSV o Excel"** for bulk import.
- Import report: **"Importamos 42 de 45"** with **"Descargar las 3 con errores"** and
  row-level errors in Spanish.
- Search by address or zone, and an operation filter.
- Columns: title + address + listing link, operation, zone, price (ARS or USD), rooms,
  status **Publicada**/**Pausada**, inquiries per property.
- Pagination.

**What must work**

- CSV and XLSX import with per-item validation and a downloadable error report.
- Manual create and edit.
- Publish and pause.
- The agent only shows published properties and always uses their real listing links.
- Inquiry counts are computed from lead-property associations.

**Roadmap day:** Day 4.

---

### S8 — Backoffice Negocios (admins only)

**What the user sees**

- Nav: **Negocios**, **Conversaciones**, **Simulador**, **Salud del sistema**, **Planes**.
- **"Dar de alta un negocio"**.
- KPIs: activos, en prueba, onboarding sin terminar, WhatsApp con problemas.
- Search by name or email.
- Filters: **Todos**, **Necesitan ayuda**, **En prueba**.
- Columns: name + owner email, plan (**Pro** / **Prueba · N días**), onboarding **N de 5**,
  WhatsApp status (**Conectado**, **Verificación pendiente**, **Acción requerida**,
  **Sin conectar**), inquiries last 7 days, sign-up date.

**What must work**

- Admin-only access enforced by the global admin flag.
- List is tenant-scoped for operators but cross-tenant for admins.
- KPIs and filters derive from the same data as the panel.
- WhatsApp status maps connection health and Meta verification.
- Manual "Dar de alta" covers accounts that cannot complete self-serve Embedded Signup.

**Roadmap day:** Day 1 (admin shell and listing); Day 7 (KPIs, filters, plan, WhatsApp
status, manual onboarding).

---

### S9 — Backoffice Detalle del negocio

**What the user sees**

- Plan, sign-up date, and owner.
- **"Probar su agente"** and **"Suspender"**.
- WhatsApp connection health with plain-language diagnosis, how long messages have been
  failing, and the Meta error code, e.g. **190** (permission revoked), plus technical detail.
- Number, WABA, business verification, and last message received.
- **"Enviarle link para reconectar"**, **"Reintentar configuración"**,
  **"Enviar mensaje de prueba"**.
- Activity log of system and user events with actor and time.
- Onboarding checklist.
- Plan usage: conversations this month **N de 1.000** and users.
- Users with roles: **dueño**, **agente**.

**What must work**

- Connection health stores and surfaces Meta error codes, revoked tokens, and failing webhooks.
- Reconnect link and retry run the same steps as Embedded Signup completion.
- Activity log reads from the Tenancy audit log.
- Suspend disables the tenant without deleting data.
- Plan usage is computed from actual conversation activity.
- User roles come from Identity and are editable by owners/admins.

**Roadmap day:** Day 7.

---

## Cuentas Claras

### C1 — Panel Inicio

**What the user sees**

- Nav: **Inicio**, **Facturas**, **Aprobaciones** (count badge), **Clientes**,
  **Recordatorios y cobros**.
- Status **"Cobrando en automático · WhatsApp y Mercado Pago conectados"**.
- **"Importar facturas"** button.
- KPIs: recuperado este mes, total a cobrar (**N facturas**), vencido (**N facturas**),
  promesas de pago (**N clientes**, before date).
- Aging buckets: **todavía no vence**, **1-15**, **16-30**, **más de 30 días**.
- A **"Necesita tu atención"** list: promise to approve, payment to verify, installment
  plan to approve.
- Today's activity: reminders sent, paid with link, replied with a question, and the next
  send time.

**What must work**

- KPIs, aging buckets, attention list, and activity are computed from invoices, payments,
  approvals, and reminders.
- The Aprobaciones count badge matches the pending approval list.
- Status reflects both WhatsApp and Mercado Pago connection health.
- "Importar facturas" leads to the CSV import flow.

**Roadmap day:** Day 11; Day 8 (invoices), Day 9 (reminders/payments), Day 10 (approvals).

---

### C2 — Facturas

**What the user sees**

- **"Descargar plantilla CSV"** and **"Importar facturas"**.
- Tabs with counts: **Pendientes**, **Vencidas**, **Con promesa**, **Pagadas este mes**.
- Search by client or invoice number.
- Columns: client + subtitle, invoice number (**B 0003-00001245**), amount, due date,
  status (**Promesa por aprobar**, **Pago para verificar**, **Vencida · N días**,
  **Por vencer**, **Pagada · Mercado Pago**), and **"Lo próximo"** (next scheduled action,
  e.g. **"Recordatorio mañana 9:30"**).
- Pagination.
- A notice that ARCA import is coming.

**What must work**

- CSV template download and import with an error report.
- Tabs, counts, search, statuses, and "Lo próximo" come from invoice and scheduling data.
- ARCA import is not available in the MVP; only the notice is shown.

**Roadmap day:** Day 8; Day 9 (Lo próximo); **Post-MVP** (ARCA invoice reading).

---

### C3 — Aprobaciones

**What the user sees**

Three card types, each showing the client's literal message and a preview of what the
agent will answer:

- **Promesa de pago:** **"Aprobar 5 nov"**, **"Proponer otra fecha"**, **"Responder yo"**.
- **Plan de cuotas:** the schedule of installments; **"Aprobar 3 cuotas"**,
  **"Ofrecer 2 cuotas"**, **"Rechazar"**.
- **Pago para verificar:** the receipt image sent by WhatsApp (tap to enlarge), a note when
  the payment is not found in Mercado Pago; **"Confirmar que pagó"**, **"Pedir otro comprobante"**.

After a decision, the agent continues the conversation.

**What must work**

- Approval decisions update the approval state and let the agent continue the same thread.
- Promise and installment counters reflect the pending approvals.
- Receipt media is downloaded from WhatsApp and stored, and enlarges on tap.
- Payment verification is based on Mercado Pago lookups, not only the attached image.

**Roadmap day:** Day 10; Day 9 (installment schedules and payment link); Day 11 (approval
count badge on C1).

---

### C4 — Recordatorios y cobros

**What the user sees**

- An editable sequence of steps: 3 days before, due date, 7 days after, each with its
  WhatsApp template text and Meta status (**aprobada** / **en revisión**).
- The last step at 15 days stops messaging and notifies the owner.
- **"+ Agregar un paso"**.
- Send window presets.
- **"No enviar en feriados"** (Argentine holidays).
- **"Pausar si el cliente prometió pagar"**.
- Mercado Pago connected account with **"Cambiar cuenta"**.
- WhatsApp number plus usage **"1.000 respuestas gratis por mes; vas usando 214"**.
- **"Guardar cambios"**.

**What must work**

- Reminder policy is tenant-scoped and editable, with escalation and stop conditions.
- Templates per tenant sync their Meta status.
- Argentine holidays are sourced and verified for 2026–2027.
- Mercado Pago OAuth is per business so payments go to that business's own account.
- WhatsApp usage is measured against the free tier.

**Roadmap day:** Day 9; Day 11 (usage surfaced with live counts).

---

### C5 — Backoffice Negocios y envíos

**What the user sees**

- Nav: **Negocios y envíos**, **Conversaciones**, **Plantillas de WhatsApp**, **Simulador**,
  **Planes**.
- KPIs: recordatorios enviados, envíos fallidos, pagos registrados, plantillas en revisión.
- Failed sends list with reason and action: number has no WhatsApp → avisar al negocio;
  Meta paused a template for low quality → revisar plantilla; Mercado Pago webhook invalid
  signature → ver detalle. Plus **"Reintentar todos"**.
- Tenants table with plan by managed clients (**Hasta 50** / **Hasta 150** /
  **Prueba · N días**), managed clients, recovered this month, WhatsApp status, Mercado Pago status.

**What must work**

- Failed sends surface their root cause and offer the right remediation.
- "Reintentar todos" retries only retryable failures.
- Template health and Mercado Pago webhook health are monitored.
- Plan is shown read-only for the MVP.

**Roadmap day:** Day 11; Day 9 (template status and Mercado Pago OAuth); **Post-MVP**
(Planes administration beyond a read-only view).

---

## Screens in the navigation, not mocked

These are short specs derived from the related screens above.

### inmo24x7 — Agente

Edit the same agent configuration as the onboarding wizard: name, tone, hours,
qualification questions, and notification email. Changes are stored in Tenancy, versioned,
and read by the graph on the next conversation.

**Roadmap day:** Day 2.

### inmo24x7 — Configuración

Business profile, team hours, notification destinations, and account settings that feed
the dashboard and agent. Agent-specific settings link to Agente.

**Roadmap day:** Day 2 (business profile, hours, notifications); **Post-MVP** (any advanced
account and billing settings beyond the MVP).

### Cuentas Claras — Clientes

The companies that owe money: name, contact, and metadata used by invoices, reminders, and
the collections agent. Imported and managed from the CSV import.

**Roadmap day:** Day 8.

---

## Coverage appendix

Every screen element maps to a day or Post-MVP. This table is the cross-check used when the
plan changes.

| Screen | Day(s) | Post-MVP / note |
| --- | --- | --- |
| S1 Ingreso | 1 | Términos and Política page content |
| S2 Onboarding | 2 | — |
| S3 Probalo | 3, 4, 7 | sample properties replaced after import |
| S4 Conectar WhatsApp | 7 (5 for manual/test) | — |
| S5 Panel Inicio | 1, 2, 4, 6, 7 | — |
| S6 Panel Consultas | 6 (4, 5) | — |
| S7 Panel Propiedades | 4 | — |
| S8 Backoffice Negocios | 1, 7 | — |
| S9 Backoffice Detalle | 7 | — |
| inmo24x7 Agente | 2 | — |
| inmo24x7 Configuración | 2 | advanced billing/settings |
| C1 Panel Inicio | 11 (8, 9, 10) | — |
| C2 Facturas | 8 (9) | ARCA invoice reading |
| C3 Aprobaciones | 10 (9, 11) | — |
| C4 Recordatorios y cobros | 9 (11) | — |
| C5 Backoffice | 11 (9) | Planes beyond read-only |
| Cuentas Claras Clientes | 8 | — |

Cross-product screens that are only in navigation (Conversaciones, Plantillas de WhatsApp,
Simulador, Salud del sistema, Planes) resolve as follows:

- **Simulador** (both products): Day 3 for inmo24x7; Day 8 for Cuentas Claras reuse.
- **Conversaciones** cross-tenant viewer: Day 7 for inmo24x7 if it fits; otherwise Post-MVP.
- **Plantillas de WhatsApp**: Day 9 (template status sync).
- **Salud del sistema**: Day 7 (deploy and system health).
- **Planes**: read-only plan display on Day 7 (inmo24x7) and Day 11 (Cuentas Claras);
  administration beyond read-only is Post-MVP.
