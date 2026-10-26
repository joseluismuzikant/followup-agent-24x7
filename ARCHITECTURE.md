# Arquitectura

Monorepo con un motor compartido y dos productos. Todo el código, nombres y
comentarios están en inglés; los textos de interfaz están en español.

## Capas

Cada contexto tiene tres carpetas:

- `domain/`: entidades, valores y contratos de repositorio. Python puro.
- `application/`: casos de uso.
- `infrastructure/`: SQLAlchemy, WhatsApp, LangGraph, FastAPI y demás adaptadores.

`domain` nunca importa de `application` ni de `infrastructure`. Si dos productos
necesitan una pieza, vive en `packages/core`; si no, vive en el producto.

## Contextos

En `packages/core`:

- **Tenancy**: clientes, planes, onboarding, notificaciones y auditoría.
- **Identity**: perfiles, roles y administración global.
- **Messaging**: WhatsApp Cloud API y Embedded Signup.
- **Conversation**: seguimientos, agente y derivación a una persona.

En `apps/inmo24x7/api`:

- **Leads**: calificación y coordinación de visitas.
- **Properties**: importación y validación de propiedades.

Milestone 1 implementa Tenancy, sus endpoints y los dos paneles. El resto se
agrega en los milestones 2 y 3.

## Límites actuales

- Sin autenticación: Supabase llega con el onboarding.
- Sin LangGraph ni WhatsApp: se incorporan con el agente y la conexión.
- Los tests de API usan SQLite en memoria; desarrollo y producción usan Postgres.

## Agente

Cuando se incorpore, el estado vivirá en LangGraph con el checkpointer de Postgres
y `thread_id = tenant_id:channel:visitor_id`. Las herramientas se declararán una
sola vez y tendrán un handler testeado. El grafo controlará el flujo; el LLM no
lo decidirá desde el prompt. El mismo agente servirá para WhatsApp y el simulador.
