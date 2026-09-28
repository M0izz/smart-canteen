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

## Tests
`pytest -q`

## Important
SQLite is configured for local development. For production, replace the database adapter with PostgreSQL/MySQL and use a shared database/session strategy before horizontal scaling. WebSocket/QR-camera scanning, password-reset email delivery, AWS provisioning and Jira/GitHub integration are deployment extensions rather than simulated features in this local package.
