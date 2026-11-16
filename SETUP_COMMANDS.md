# Dispensary Desk — Production-Ready PostgreSQL Setup & Run Guide

> Complete reference for running Dispensary Desk with **PostgreSQL 16**.
> Project path: `c:\Users\asus\Downloads\dispensary-desk\dispensary-desk`

---

## 🟢 Live Access URLs

| Application / Service | Local URL | Network URL (other hospital PCs) |
|---|---|---|
| **Hospital Web App (Main UI)** | http://localhost:5173 | `http://192.168.1.11:5173` |
| **Remote / Cloud Web App** | http://localhost:5174 | `http://192.168.1.11:5174` |
| **Hospital API Docs** | http://localhost:8000/api/docs | `http://192.168.1.11:8000/api/docs` |
| **Cloud API Docs** | http://localhost:8001/api/docs | `http://192.168.1.11:8001/api/docs` |

---

## 📦 What Was Installed and Where

### 1. Database Server: PostgreSQL 16
* **Install Location:** `C:\Program Files\PostgreSQL\16\`
* **Data Directory:** `C:\Program Files\PostgreSQL\16\data\`
* **Windows Service:** `postgresql-x64-16` / `postgresql-16` (Running automatically on Windows boot)
* **Port:** `5432`
* **Superuser:** `postgres` (password: `postgres123`)
* **Application User:** `dispensary` (password: `dispensary123`)
* **Databases Created:**
  - `hospital_db` (primary authoritative dispensary DB: 116 medicines, bills, inventory)
  - `cloud_db` (sync replica + user accounts and OTP)

### 2. Python Virtual Environment
* **Location:** `c:\Users\asus\Downloads\dispensary-desk\dispensary-desk\backend\.venv\`
* **Installed Packages:**
  - `fastapi`, `uvicorn[standard]` (HTTP server & API framework)
  - `sqlalchemy`, `alembic` (ORM and schema migrations)
  - `psycopg` (PostgreSQL 3 database driver)
  - `pydantic`, `pydantic-settings` (Validation & settings)
  - `argon2-cffi`, `PyJWT` (Password security & JWT tokens)
  - `httpx` (HTTP sync peer client)

### 3. Frontend Packages
* **Location:** `c:\Users\asus\Downloads\dispensary-desk\dispensary-desk\frontend\node_modules\`
* **Framework:** React 18, TypeScript, Vite, Tailwind CSS, TanStack Query, Axios

### 4. Configuration Files Updated for PostgreSQL
* `scripts\env-hospital.cmd`: configured to `postgresql+psycopg://dispensary:dispensary123@localhost:5432/hospital_db`
* `scripts\env-cloud.cmd`: configured to `postgresql+psycopg://dispensary:dispensary123@localhost:5432/cloud_db`
* `backend\.devdata\secrets.cmd`: generated cryptographic JWT and synchronization keys

---

## 🚀 Everyday Use (How to Run)

### To Start Everything:
Simply double-click **`start.bat`** in the project folder!

Or run in 4 separate terminal windows:

#### Window 1: Hospital Backend (:8000)
```cmd
cd backend
call ..\scripts\env-hospital.cmd
.venv\Scripts\python.exe -m uvicorn app.main:create_app --factory --host 0.0.0.0 --port 8000
```

#### Window 2: Cloud Backend (:8001)
```cmd
cd backend
call ..\scripts\env-cloud.cmd
.venv\Scripts\python.exe -m uvicorn app.main:create_app --factory --host 0.0.0.0 --port 8001
```

#### Window 3: Hospital Frontend UI (:5173)
```cmd
cd frontend
set VITE_API_PROXY=http://127.0.0.1:8000
npx vite --host --port 5173 --strictPort
```

#### Window 4: Remote Frontend UI (:5174)
```cmd
cd frontend
set VITE_API_PROXY=http://127.0.0.1:8001
npx vite --host --port 5174 --strictPort
```

### To Stop Everything:
Double-click **`stop.bat`** in the project folder or close the terminal windows.

---

## 🏥 Hospital Access from Other Computers (LAN)

Other computers on the clinic/hospital network (WiFi or ethernet cable) do **NOT** need any installation.

1. Keep this server computer running and connected to the hospital WiFi / router.
2. On any other hospital PC, open Chrome / Edge and visit:
   ```
   http://192.168.1.11:5173
   ```
3. Staff can sign in, create bills, and manage inventory directly from the web browser!
