# WGDSS Launch and Deployment

## Fastest Local Launch

From the repository root in PowerShell:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\Start-WGDSS.ps1
```

For a button-style launch, double-click `START_WGDSS.cmd` in the repository
root. The launcher:

1. Creates the backend virtual environment if it is missing.
2. Repairs missing core backend packages when necessary.
3. Installs frontend packages when `node_modules` is missing.
4. Applies Alembic migrations.
5. Starts the FastAPI and Vite development servers in separate terminals.
6. Waits for both applications to respond, then opens the dashboard.

If either server is already healthy, the launcher reuses it instead of starting
a duplicate process on the same port.

This is a local demonstration/development launcher. It is not a public or
production deployment mechanism. Close both terminal windows, or press
`Ctrl+C` in each, to stop the application.

Use `-NoBrowser` when the browser should not open automatically:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\Start-WGDSS.ps1 -NoBrowser
```

## Manual Local Launch

Open the first PowerShell terminal:

```powershell
cd "C:\path\to\T&TEC Weather Based Generation Decision System\backend"
venv\Scripts\python.exe -m pip install -r requirements-dev.txt
venv\Scripts\python.exe -m alembic upgrade head
venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Open a second PowerShell terminal:

```powershell
cd "C:\path\to\T&TEC Weather Based Generation Decision System\frontend"
npm install
npm run dev -- --host 127.0.0.1
```

Then open:

- Dashboard: `http://localhost:5173`
- API documentation: `http://localhost:8000/docs`
- API health: `http://localhost:8000/api/v1/health`

Using `python.exe -m uvicorn` is intentional. It remains valid when the project
folder moves, unlike a stale `uvicorn.exe` launcher generated in an older
virtual-environment path.

## Validation Commands

Backend:

```powershell
cd backend
venv\Scripts\python.exe -m pytest -q
venv\Scripts\python.exe -m alembic check
```

Frontend:

```powershell
cd frontend
npm test
npm run build
```

## One-Command Production Deployment Option

The practical production target is Docker Compose. After containerization, an
approved host would run:

```powershell
docker compose up --build -d
```

The composition should contain:

- a static production frontend served by Nginx;
- FastAPI behind a production process manager;
- PostgreSQL with a persistent volume;
- a one-shot Alembic migration service;
- backend and database health checks;
- an external environment file or secret store;
- a reverse proxy or load balancer providing TLS;
- restricted CORS origins and no source-data archives inside images.

This option should be implemented only after the target host, DNS/TLS approach,
PostgreSQL backup location, secrets mechanism, and read-only SCADA/historian
network boundary are approved. The current one-click launcher is the safer
immediate option for demonstrations and engineering review.

## Deployment Safety

- Never commit `.env`, API keys, database passwords, or SCADA exports.
- Do not label mock or historical replay values as live SCADA.
- Apply migrations before starting a deployed API instance.
- Keep the dashboard unavailable for dispatch decisions when required SCADA,
  weather, or model-quality checks fail.
- Use PostgreSQL, TLS, access control, backups, monitoring, and audit logs for
  any managed deployment.
