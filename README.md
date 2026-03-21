# Med Slot Workspace

Web app + API for medication bottle slotting workflow:
- Choose a slot first (1-8)
- Scan bottles one-by-one by USB QR scanner
- Keep adding later for the same station
- Press Start Mission when ready

## QR Field Index Mapping

The backend parser uses fixed index mapping:
- `0`: item_id
- `1`: patient_name
- `2`: drug_code
- `5`: strength
- `6`: qty
- `9`: rate
- `13`: diluent
- `14`: administration
- `15`: order_date
- `16`: hn
- `17`: station_code (format `S###`)
- `18`: bed_no

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

- Relay command uses env `RELAY_API_URL`.
- Backend sends `POST {RELAY_API_URL}` with payload:

```json
{
	"slot_id": 1,
	"action": "open"
}
```

- If `RELAY_API_URL` is empty, backend returns `relay_result=simulated` for development.
- Robot mission dispatch uses env `ROBOT_API_URL` in `start-mission` endpoint.
- Fixed Slot/Channel/GPIO mapping is documented in `hardware/README.md`.
