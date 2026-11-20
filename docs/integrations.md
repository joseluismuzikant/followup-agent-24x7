# inmo24x7 integrations

Three integrations live in the panel under **Configuración → Integraciones**. Owners and
managers can change them; everyone else can see them.

| Integration | What it does |
|---|---|
| **Tokko Broker** | Imports the agency's listings every 6 hours and sends each lead handed off to the team to Tokko as a web contact. |
| **Lead webhook** | Sends the same leads to any URL (another CRM, Zapier, Make) as signed JSON. |
| **Website button** | Adds a "Consultar por WhatsApp" button to the agency's website. On a property page, the button opens Sofía with that property already chosen. |

Credentials (the Tokko API key and the webhook secret) are encrypted at rest with
`TOKEN_ENCRYPTION_KEY` (AES-GCM, the same cipher as the WhatsApp tokens). They are never
returned to the browser and never logged. The webhook secret is shown once, when it is
generated.

---

## When a lead is sent

A lead is sent on its **hand-off**. That happens when Sofía passes the conversation to the
team:
- the lead picked a visit time;
- the lead answered everything (qualified);
- the lead asked to talk to a person.

Each lead is delivered once per integration. Each delivery is a job with a dedupe key per
lead and integration. A failure is retried with the job queue's exponential backoff (8
attempts, up to about 30 minutes apart):
- a timeout, a 429 or a 5xx is retried;
- any other 4xx is final;
- a redirect is final too, because redirects are not followed.

The lead panel shows the result: "Enviado a Tokko ✓", or the error. The webhook card keeps
a log of the last 20 deliveries (status code and time).

A lead who said "BAJA" (do-not-contact) is still delivered, because the agency needs to know
about them. The summary then says "Pidió no ser contactado (BAJA)" and the webhook payload
has `do_not_contact: true`.

What was already sent belongs to the agency's systems: deleting a contact or closing the
account in the backoffice does not delete anything in Tokko or behind the webhook.

---

## Lead webhook

### Request

`POST <your URL>`. The body is UTF-8 JSON. The headers are:

| Header | Value |
|---|---|
| `Content-Type` | `application/json` |
| `X-Inmo24x7-Event` | `lead.handed_off`, or `ping` for "Enviar prueba" |
| `X-Inmo24x7-Delivery` | A UUID. It is the same on every retry of one delivery, so you can drop duplicates. |
| `X-Inmo24x7-Signature` | `sha256=<hex HMAC-SHA256 of the raw body, keyed with your secret>` |

Answer with any 2xx within 10 seconds.

### Payload (`lead.handed_off`)

```json
{
  "event": "lead.handed_off",
  "delivery_id": "7d0c0d0e-3b7b-4c39-9a51-0c2f8f0f9a11",
  "sent_at": "2026-11-18T12:05:31.204118+00:00",
  "lead": {
    "id": "3f1e…",
    "created_at": "2026-11-18T11:58:02+00:00",
    "handed_off_at": "2026-11-18T12:05:30+00:00",
    "hand_off_reason": "visit",
    "channel": "whatsapp",
    "source": "web_button",
    "name": "Ana Pérez",
    "phone": "+54 9 11 5555-0188",
    "email": null,
    "operation": "rent",
    "zone": "Palermo",
    "rooms": 2,
    "budget": {"amount": 900000, "currency": "ARS"},
    "conditions": {"garantia": "caucion", "tiene_mascota": true},
    "properties": [
      {
        "id": "a8c1…",
        "title": "2 ambientes luminoso",
        "address": "Gorriti 4800",
        "operation": "rent",
        "price": "$880.000 por mes",
        "link": "https://www.tuinmobiliaria.com.ar/propiedad/501001",
        "source": "tokko",
        "external_id": "501001",
        "external_ref": "TKO501001"
      }
    ],
    "visit": {
      "starts_at": "2026-11-18T09:00:00-03:00",
      "label": "mié 18/11 09:00",
      "property": "2 ambientes luminoso · Gorriti 4800",
      "status": "proposed"
    },
    "summary": "Busca alquiler 2 amb. en Palermo, hasta $900.000, garantía: caución. Pidió visita mié 18/11 09:00. Le interesa: 2 ambientes luminoso. — vía inmo24x7",
    "do_not_contact": false,
    "panel_link": "https://app.inmo24x7.com/consultas?lead=3f1e…"
  }
}
```

| Field | Values |
|---|---|
| `hand_off_reason` | `visit`, `qualified` or `human` |
| `source` | `web_button` when the lead came from the website button, otherwise `null` |
| `operation` | `rent`, `sale` or `null` |
| `properties` | What the lead chose or wants to visit. `external_id` and `external_ref` are set when the property came from Tokko. |
| `conditions` | The lead's situation as they said it: `garantia`, `plazo_meses`, `temporal`, `quiere_amueblado`, `tiene_mascota`, `uso_profesional`, `necesita_credito`, `necesita_financiacion`, `ofrece_permuta`. A key is present only when the lead said it. |
| `phone` / `email` | The contact they left. For WhatsApp, `phone` is their number. |

`ping` ("Enviar prueba") sends `{event, delivery_id, sent_at, tenant_id, message, panel_link}`.

### Verifying the signature

Compute the HMAC over the **raw** request body, before parsing it. Re-serialized JSON will
not match. Compare in constant time.

Python (Flask):

```python
import hashlib
import hmac

from flask import Flask, abort, request

SECRET = b"whsec_..."  # Configuración → Integraciones → Webhook
app = Flask(__name__)


@app.post("/hooks/inmo24x7")
def inmo24x7():
    raw = request.get_data()  # the exact bytes
    expected = "sha256=" + hmac.new(SECRET, raw, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, request.headers.get("X-Inmo24x7-Signature", "")):
        abort(401)
    event = request.get_json()
    # Use X-Inmo24x7-Delivery to ignore a retry you already processed.
    return "", 204
```

Node (Express):

```js
import crypto from "node:crypto";
import express from "express";

const SECRET = process.env.INMO24X7_WEBHOOK_SECRET; // "whsec_..."
const app = express();

app.post("/hooks/inmo24x7", express.raw({ type: "application/json" }), (req, res) => {
  const expected =
    "sha256=" + crypto.createHmac("sha256", SECRET).update(req.body).digest("hex");
  const given = req.get("X-Inmo24x7-Signature") ?? "";
  const ok =
    given.length === expected.length &&
    crypto.timingSafeEqual(Buffer.from(given), Buffer.from(expected));
  if (!ok) return res.sendStatus(401);
  const event = JSON.parse(req.body.toString("utf8"));
  // Use req.get("X-Inmo24x7-Delivery") to ignore a retry you already processed.
  res.sendStatus(204);
});
```

The URL must be `https://`. Plain `http://localhost` is accepted only while the panel itself
runs on localhost, for development. "Generar secreto nuevo" replaces the secret
immediately; deliveries after that are signed with the new one.

---

## Tokko Broker

### Connecting

1. In Tokko, go to **Mi empresa → Permisos → Clave API**. Each company has one key.
2. Paste the key in the Tokko card and press **Probar conexión**. inmo24x7 lists one property
   with it, and saves the key encrypted only if that call works.

The card has two switches, both on by default:

| Switch | What it does |
|---|---|
| **Importar propiedades** | A sync every 6 hours, plus **Sincronizar ahora**. |
| **Enviar consultas a Tokko** | A web contact for each hand-off. |

### Importing listings

| Ours | From Tokko |
|---|---|
| `external_id` | `id` |
| `external_ref` (the code on the website) | `reference_code` |
| Title | `publication_title` (else the address) |
| Address | `fake_address` (the public one) when set, else `address` |
| Zone | `location.name`, else the last part of `location.full_location` |
| Operation, price, currency | One listing per operation in `operations[]`: `Venta` → sale, `Alquiler` → rent (a regular rent wins over `Alquiler temporario`), from the first `prices[]` entry with an amount; `USD`/`U$S` → USD, `ARS`/`$` → ARS |
| Rooms (ambientes) | `room_amount`, else `suite_amount` + 1 |
| Link | `public_url` |
| Status | Published while `/property/` lists it; paused when it no longer does |

**One listing per operation.** A Tokko property for sale and for rent becomes two listings
here, with the same `external_id`. Sofía searches by operation, and price and currency
belong to the operation, so one listing could not show both.

**Re-sync.**
- A listing is updated in place, matched by Tokko id and operation.
- Its **conditions** (requirements and features) are ours: they are kept on every sync and
  stay editable here.
- Everything else is read-only in our form ("Se edita en Tokko"), including publish and pause.
- A property Tokko no longer lists is **paused**, never deleted, so a lead's history keeps
  pointing at it. It is published again if it comes back.
- If Tokko cannot be read to the end (a bad key, a timeout), nothing is paused.

Each sync leaves a report like the spreadsheet import's: created, updated, paused,
unchanged, and failed with the reason ("la venta no tiene precio publicado", "no tiene
link público", …).

Disconnecting deletes the key. Imported listings stay as they are, still marked as Tokko's,
and are no longer updated.

### Sending leads

`POST /api/v1/webcontact/?key=…&format=json&lang=es_ar` with this JSON body:

```json
{
  "name": "Ana Pérez",
  "cellphone": "+54 9 11 5555-0188",
  "email": "ana@example.com",
  "properties": [501001],
  "tags": ["inmo24x7"],
  "text": "Busca alquiler 2 amb. en Palermo, hasta $900.000, garantía: caución. Pidió visita mié 18/11 09:00. — vía inmo24x7"
}
```

- `properties` holds the Tokko ids of the chosen properties that came from Tokko. It is left
  out when there are none.
- A 401 or 403 means the key was revoked: final. Reconnect with the new key.
- Any other 4xx is final too ("Tokko rechazó el contacto").
- A 5xx, a 429 or a timeout is retried.

### Endpoints and sources

What Tokko's public documentation confirms:

| What | Source |
|---|---|
| The base URL `http://www.tokkobroker.com/api/v1/<resource>/?format=json&key=<api_key>&lang=es_ar`, the `property` resource and one key per company | <https://developers.tokkobroker.com/docs/atributos.md> |
| Where the key is: "Mi empresa → Permisos" | <https://developers.tokkobroker.com/docs/first-step.md> |
| The resource index (`property`, `webcontact`, `inactiveproperty`, `location`, …), readable without a key | <https://www.tokkobroker.com/api/v1/> |
| The fields of Zapier's **Create Web Contact** action: `name` (required), `email`, `phone`, `cellphone`, `text`, `properties`, `developments`, `tags`, `agent_mail` | <https://zapier.com/apps/tokko-broker/integrations> |
| The API playground (needs a key) | <https://www.tokkobroker.com/api/playground> |

We call `https://` on the same host the docs give as `http://`, so the key never travels
in clear.

### To verify with a real key

The schemas (`/api/v1/property/schema/`, `/api/v1/webcontact/schema/`) answer 401 without a
key. Every item below lives in one module,
`apps/inmo24x7/api/src/inmo24x7_api/integrations/tokko.py`, so fixing one is a local change:

1. **Pagination:** `limit`/`offset` parameters and the `{"meta": {"next", "total_count"},
   "objects": [...]}` envelope.
2. **Property fields:** the names in the table above, especially `fake_address`,
   `location.name`, `operations[].operation_type` (in es_ar: "Venta", "Alquiler", "Alquiler
   temporario"), `prices[].currency` and `public_url` (is it the agency's own web page or
   Tokko's listing sheet?).
3. **Listed means published:** that `/property/` returns only active listings (unpublished
   ones are in `inactiveproperty`), and whether reserved or sold ones need a `status` filter.
4. **Web contact:** that `webcontact` takes a POST with the Zapier field names above, and its
   response (we read an `id` if there is one; nothing depends on it). Tokko's other
   documented contact endpoint, `POST /portals/simple_portal/api/v1/contact/`
   (<https://developers.tokkobroker.com/docs/contact.md>), is for portals: it needs a
   `publication_id` and an email, and the portal turned on. It is not used.
5. **Duplicates:** whether Tokko merges two web contacts with the same phone. We send one
   per lead.

How to check them all at once: `curl "https://www.tokkobroker.com/api/v1/property/schema/?format=json&key=$KEY"`
and `.../property/?format=json&lang=es_ar&limit=1&key=$KEY`, then compare with the table.

---

## Website button

The agency pastes one line on every page of its website:

```html
<script src="https://app.inmo24x7.com/widget.js" data-agencia="<public id>" async></script>
```

The panel's "Botón para tu web" card shows the line ready to copy, with the agency's id.

- **Tokko websites:** in the website's settings, use the custom code section, or add it in
  Google Tag Manager as "Custom HTML" on all pages.
- **Any other site:** paste it before `</body>`.

### What it does

- It shows a floating "Consultar por WhatsApp" link. The colors, text and side are set in the
  panel; `data-color` and `data-texto` on the script tag override them.
- It is a keyboard-focusable link with an `aria-label` and a 48 px target. It truncates
  instead of overflowing on a phone.
- It opens `https://wa.me/<agency number>` with a prefilled text:
  - on a property page: `Hola, me interesa la propiedad «<título>» (ref. <código>)`;
  - anywhere else: `Hola, les escribo desde su web para hacer una consulta.`
- The code comes from `data-propiedad="…"` on any element: Tokko's code, our id, or the
  property's link. Without it, the page's own URL is used when its path has a number in it
  (`/propiedad/12345-depto`).
- The title comes from `data-titulo` on that element, else `og:title`, else `<title>`.
- It has no dependencies, sets no cookies, uses no storage and does no tracking.
- The file is ASCII only, so the « » arrive intact even on sites without a UTF-8 charset.
- Without a connected WhatsApp number, it shows nothing.

### What Sofía does with it

In the lead's **first** message, Sofía looks for the reference: our id, Tokko's code or id,
or the link (trailing slash ignored). It must match a published property, and it is read
without the model. When found, the property is **already chosen**:
1. Sofía greets naming it.
2. She asks only what that property still needs (for example the guarantee).
3. She offers its visit times.

The lead's source is stored as `web_button`. It shows as "Web — botón" in the inbox and as
"N desde tu web" under Inicio's "Consultas recibidas". An unknown or paused reference is a
normal conversation, still marked as coming from the web.

### Its configuration endpoint

`GET https://app.inmo24x7.com/widget/v1/<public id>`. Caddy sends `/widget/v1/*` on the
panel's host to the API. The response:

```json
{"agency_name": "Inmobiliaria Sur", "phone": "5491155550100", "color": "#047857",
 "text_color": "#ffffff", "position": "right", "label": "Consultar por WhatsApp"}
```

Only public data: what any visitor of the website sees anyway. It is GET only (other methods
get 405), with `Access-Control-Allow-Origin: *` and no credentials, and cached for 5
minutes. An unknown id, a disabled button or a suspended agency gets 404.

---

## Deleting data

These extend the backoffice privacy requests ("Datos y privacidad").

**Eliminar datos de un contacto** also deletes that contact's delivery log rows (Tokko and
webhook) and their pending delivery jobs.

**Cerrar cuenta y eliminar datos** also deletes:
- the integration settings and their **credentials** (the Tokko API key, the webhook secret);
- the sync reports;
- the whole delivery log.

What was already sent to Tokko or to the agency's webhook stays in those systems. Both
confirmations say so.
