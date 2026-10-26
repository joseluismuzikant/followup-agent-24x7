# followup-agent-24x7

Plataforma de agentes de WhatsApp que siguen cada conversación hasta un resultado.

- **inmo24x7**: califica consultas inmobiliarias y coordina visitas. Es el primer producto.
- **Cuentas Claras**: cobranza de facturas para empresas de servicios. Solo está definido el alcance.

Estado actual: **milestone 1**, la base del panel, la API y la tenencia.

## Requisitos

- Docker con Compose.
- [uv](https://docs.astral.sh/uv/).
- Node.js 22 o superior. Corepack, incluido con Node, provee `pnpm`.


## Arrancar

```bash
uv run --all-packages python scripts/dev.py
```

El comando instala dependencias, levanta Postgres, aplica migraciones y arranca
la API y los dos paneles. Se detiene todo con `Ctrl+C`.

- Panel: http://localhost:5173
- Backoffice: http://localhost:5174
- API: http://localhost:8001
- Documentación de la API: http://localhost:8001/docs

Postgres local usa el puerto 5433 para no chocar con otras bases.

### Paso a paso, sin script

```bash
uv sync --all-packages
corepack pnpm install --frozen-lockfile
docker compose up -d --wait db
uv --directory apps/inmo24x7/api run alembic upgrade head
```

Después, en terminales separadas:

```bash
uv --directory apps/inmo24x7/api run uvicorn inmo24x7_api.main:app --reload --port 8001
corepack pnpm --filter @inmo24x7/web dev
corepack pnpm --filter @inmo24x7/backoffice dev
```

## Variables de entorno

Copiá `.env.example` a `.env` para cambiarlas. El script de desarrollo y Vite
leen el `.env` de la raíz. Docker Compose también lo lee automáticamente.

| Variable | Valor local por defecto | La usa | Descripción |
| --- | --- | --- | --- |
| `POSTGRES_USER` | `followup` | Docker Compose | Usuario inicial de Postgres local. |
| `POSTGRES_PASSWORD` | `followup` | Docker Compose | Contraseña inicial de Postgres local. |
| `POSTGRES_DB` | `followup` | Docker Compose | Nombre de la base local. |
| `DATABASE_URL` | `postgresql+psycopg://followup:followup@localhost:5433/followup` | API, Alembic | Conexión a Postgres. En producción apunta a Supabase. Si cambiás usuario, contraseña, base o puerto, actualizala. |
| `CORS_ORIGINS` | `http://localhost:5173,http://localhost:5174` | API | Orígenes permitidos, separados por coma. |
| `VITE_API_URL` | `http://localhost:8001` | Web, backoffice | URL pública de la API. Se incorpora al build de los paneles. |

Las variables de Supabase y Meta se agregan en los milestones 2 y 3. No hay
secretos reales en el repositorio.

## Tests, lint y tipos

```bash
uv run --all-packages pytest
corepack pnpm test

uv run ruff check .
uv run ruff format --check .
corepack pnpm lint
corepack pnpm typecheck

uv run --all-packages python scripts/generate_types.py
```

## API

```bash
curl http://localhost:8001/health
curl http://localhost:8001/tenants
curl -X POST http://localhost:8001/tenants \
  -H "Content-Type: application/json" \
  -d '{"name":"Inmobiliaria Sur"}'
```

## Estructura

```text
apps/inmo24x7/api          API FastAPI
apps/inmo24x7/web          panel para clientes
apps/inmo24x7/backoffice   administración interna
apps/cuentas-claras        alcance del segundo producto
packages/core              dominio y aplicación compartidos
packages/ui                componentes React compartidos
scripts                    arranque local y generación de tipos
```

## Imágenes

Las imágenes son multiarquitectura (amd64 y arm64):

```bash
docker buildx build --platform linux/amd64,linux/arm64 \
  -f apps/inmo24x7/api/Dockerfile -t mi-registro/inmo24x7-api:latest --push .
```

Se repite el mismo comando con los Dockerfiles de `web` y `backoffice`. Los paneles
necesitan `--build-arg VITE_API_URL=https://api.example.com` en el build.

## Licencia

TODO: elegir una licencia antes de distribuir el proyecto.
