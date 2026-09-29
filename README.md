# Smart Canteen — Pre-Order & Digital Queue Management

This VS Code-ready Flask + SQLite application implements the core end-to-end canteen workflow requested in the supplied specification: authentication, role-based access, SQL-backed menu, cart/order creation, queue, notifications, staff status workflow, admin analytics and audit logging. The source specification requires HTML/CSS/Vanilla JS + Flask + SQL and a complete ZIP deliverable.

## Run in VS Code

### Windows PowerShell
```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python backend/run.py
```
Open http://127.0.0.1:5000

### Demo accounts
- Student: vrushali@example.com / Student@123
- Staff: staff@example.com / Staff@123
- Admin: admin@example.com / Admin@123

Change these credentials before deployment.

## Docker
`docker compose up --build`

## Vercel
Deploy the repository root; Vercel detects the Flask app from `app.py`. Set `SECRET_KEY` and a hosted PostgreSQL connection string as `DATABASE_URL` (or Vercel Postgres `POSTGRES_URL`) in the Vercel project environment variables for both Production and Preview. The app creates its schema and demo records on startup. Without a PostgreSQL URL, it falls back to SQLite in `/tmp`, which is temporary and not shared across function instances.

## Test's
`pytest -q`

## Important
SQLite is configured for local development. For production, replace the database adapter with PostgreSQL/MySQL and use a shared database/session strategy before horizontal scaling. WebSocket/QR-camera scanning, password-reset email delivery, AWS provisioning and Jira/GitHub integration are deployment extensions rather than simulated features in this local package.

## Menu Photography
The bundled dish photos are local copies sourced from Unsplash and used under the [Unsplash License](https://unsplash.com/license). They are free to use subject to the license terms.
