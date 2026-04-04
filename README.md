# Med Slot Workspace

Web app + API for medication bottle slotting workflow:
- Choose a slot first (1-8)
- Scan bottles one-by-one by USB QR scanner
- Keep adding later for the same station
- Press Start Mission when ready

## QR Field Index Mapping

The backend parser first removes field `1` when it contains scanner timestamp/noise
such as time/date text from the device. After that cleanup, the parser uses this mapping:
- `0`: barcode number
- `1`: drug name
- `4`: drug strength
- `5`: drug amount
- `12`: diluent
- `13`: administration
- `14`: drug produce date (ISO, e.g. `2026-01-30`)
- `15`: hospital number (HN)
- `16`: destination code (format `S###`)

Optional fields still accepted when present:
- `8`: rate
- `17`: bed_no

Normalization rules:
- HN is uppercased before storing (e.g. `hn6200079` -> `HN6200079`).
- Destination code is uppercased before validation/storage (e.g. `s049` -> `S049`).

Supported delimiters: tab, `|`, `;`, `,` (in that priority).

## Project Structure

- `backend/`: FastAPI + SQLAlchemy
- `frontend/`: React + Vite + TypeScript
- `docker-compose.yml`: run db + backend + frontend

## Run With Docker Compose

```bash
docker compose up --build
```

Then open:
- Frontend: http://localhost:5173
- Backend API (direct): http://localhost:8000
- Backend docs (direct): http://localhost:8000/docs
- pgAdmin: http://localhost:5050

Notes:
- Frontend runs in its own container (nginx) and proxies `/api/*` and `/health` to backend.
- Backend runs in its own container (FastAPI + uvicorn).
- Database runs in its own PostgreSQL container (`db`).
- PostgreSQL data is persisted in Docker volume (`postgres_data`).
- pgAdmin runs in its own container for database management.

Environment setup (optional):

```bash
cp .env.example .env
```

Default database connection in Docker:

```text
postgresql+psycopg2://medbox:medbox123@db:5432/medbox
```

pgAdmin default login:

```text
email: admin@medbox.com
password: admin123
```

Add PostgreSQL server in pgAdmin:

```text
Host: db
Port: 5432
Username: medbox
Password: medbox123
Database: medbox
```

## Local Run (Without Docker)

### Backend

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

By default backend uses SQLite (`backend/medbot.db`).
For PostgreSQL, set `DATABASE_URL`.

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Set optional API base URL:

```bash
VITE_API_BASE=http://localhost:8000
```

If `VITE_API_BASE` is empty, frontend uses same-origin requests (`/api/...`), which is the default Docker behavior.

## Key API Endpoints

- `GET /api/slots`
- `POST /api/slots/{slot_id}/select`
- `POST /api/slots/{slot_id}/open`
- `POST /api/slots/open-empty`
- `POST /api/slots/{slot_id}/scan`
- `POST /api/slots/{slot_id}/scan-out`
- `GET /api/slots/{slot_id}/items`
- `DELETE /api/slots/{slot_id}/items/{scan_id}`
- `POST /api/slots/{slot_id}/start-mission`
- `POST /api/slots/{slot_id}/reopen`
- `GET /api/history/removals`
- `GET /api/history/export/removals.csv`

## Seed Data (Demo)

Run demo seed data into current database:

```bash
docker compose exec backend python -m app.seed_data
```

For local backend (without Docker):

```bash
cd backend
python -m app.seed_data
```

Behavior:
- Ensures slots `1..8` exist.
- Inserts demo batch/items/mission/log if there is no scan data yet.
- Skips seeding when `bottle_scans` already contains data.

## Relay and Robot Integration

Backend now supports direct Linux GPIO relay control for opening each slot.

Default relay mode is `gpio` with this fixed slot mapping:

| Slot | GPIO |
|---:|---:|
| 1 | 7 |
| 2 | 12 |
| 3 | 16 |
| 4 | 20 |
| 5 | 23 |
| 6 | 24 |
| 7 | 25 |
| 8 | 8 |

Relevant backend env vars:

- `RELAY_MODE=gpio` to pulse local GPIO directly.
- `GPIO_CHIP=/dev/gpiochip0` for the Linux gpiochip device.
- `RELAY_PULSE_MS=500` for relay pulse duration.
- `RELAY_ACTIVE_LOW=true` for relay boards where `LOW` triggers the relay and `HIGH` is idle.
- `RELAY_API_URL=` remains available only when `RELAY_MODE=http` or `RELAY_MODE=auto`.

Docker backend mounts the gpiochip device directly into the container. On development machines without GPIO hardware, relay open returns `simulated` instead of failing the whole API.

Robot mission dispatch still uses env `ROBOT_API_URL` in `start-mission`.

Full hardware notes are in `hardware/README.md`.
