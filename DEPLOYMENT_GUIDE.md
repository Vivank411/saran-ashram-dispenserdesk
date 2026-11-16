# Dispensary Desk — Continuous Deployment & Instant Updates Guide

This guide ensures that **whenever you make changes to the code**, they are **automatically visible in the web app without repeating setup procedures**.

---

## ⚡ How It Works (Two Environments)

### 1. 🏠 Local Hospital Server (Live Right Now on Your PC)
* **Frontend (React / Vite):** Has **Hot Module Replacement (HMR)** enabled.
  - Whenever you save any `.tsx`, `.ts`, or `.css` file in `frontend/src/`, Vite updates your browser screen **in milliseconds** without refreshing the page!
* **Backend (FastAPI / Python):** Now configured with `--reload`.
  - Whenever you save any `.py` file in `backend/app/`, Uvicorn **automatically reloads in 1 second**.
* **Database:** Lives continuously in PostgreSQL 16. You **never re-run migrations or seeds** unless you explicitly add a new table.

---

### 2. ☁️ Live Web App Deployment (Internet / Cloud)
When deploying to the cloud (100% Free Stack: **Neon + Render + Vercel**), the system uses **CI/CD Continuous Deployment**:

```
                       YOU (On your computer)
                                 │
                   Make code change & save file
                                 │
                    git commit -am "My changes"
                            git push
                                 │
                                 ▼
                         GITHUB REPOSITORY
                                 │
            ┌────────────────────┴────────────────────┐
            ▼                                         ▼
      VERCEL (Frontend)                       RENDER (Backend)
  * Detects git push                      * Detects git push
  * Rebuilds React in 30s                 * Rebuilds FastAPI in 60s
  * Updates live website                  * Updates live API
            │                                         │
            └────────────────────┬────────────────────┘
                                 ▼
                     NEON CLOUD POSTGRESQL
                   (Database stays persistent)
```

> **You never run setup commands again.** You simply push your code, and the live web app updates itself automatically.

---

## 🚀 Step-by-Step Cloud Deployment (Free Forever)

### Step 1: Create a Free GitHub Repository
1. Go to [github.com/new](https://github.com/new) and create a repository (e.g. `dispensary-desk`).
2. Link your local project and push:
   ```cmd
   cd c:\Users\asus\Downloads\dispensary-desk\dispensary-desk
   git remote add origin https://github.com/<YOUR_GITHUB_USERNAME>/dispensary-desk.git
   git branch -M main
   git push -u origin main
   ```

---

### Step 2: Create Free PostgreSQL Database on Neon
1. Go to [neon.tech](https://neon.tech) and sign up (Free).
2. Click **"New Project"** ➔ Name it `dispensary-db` ➔ PostgreSQL 16.
3. Copy the **Connection String** (it looks like `postgresql://user:pass@ep-xyz.neon.tech/neondb?sslmode=require`).

---

### Step 3: Deploy Backend on Render (Free)
1. Go to [render.com](https://render.com) and sign in with GitHub.
2. Click **"New +"** ➔ **"Web Service"** ➔ Select your `dispensary-desk` repository.
3. Settings:
   * **Root Directory:** `backend`
   * **Runtime:** `Python 3`
   * **Build Command:** `pip install -r requirements.txt && alembic upgrade head`
   * **Start Command:** `uvicorn app.main:create_app --factory --host 0.0.0.0 --port $PORT`
4. Add **Environment Variables**:
   * `APP_ROLE` = `hospital`
   * `DATABASE_URL` = *(Paste your Neon connection string)*
   * `JWT_SECRET` = *(Click Generate or paste random 32 hex chars)*
   * `SYNC_SHARED_SECRET` = *(Click Generate or paste random 32 hex chars)*
5. Click **"Create Web Service"**.
6. When done, copy your live backend URL (e.g. `https://dispensary-backend.onrender.com`).

---

### Step 4: Deploy Frontend on Vercel (Free)
1. Go to [vercel.com](https://vercel.com) and sign in with GitHub.
2. Click **"Add New..."** ➔ **"Project"** ➔ Import `dispensary-desk`.
3. Settings:
   * **Root Directory:** Click "Edit" and choose `frontend`
   * **Framework Preset:** `Vite`
4. Add **Environment Variable**:
   * `VITE_API_PROXY` = `https://dispensary-backend.onrender.com` *(your Render backend URL)*
5. Click **"Deploy"**.
6. In ~45 seconds, your app will be live at `https://dispensary-desk.vercel.app`!

---

## 🔁 Everyday Update Routine (From Now On)

Whenever you want to modify code (e.g., change a page, update a feature, adjust styling):

1. **Edit the file** in your editor (e.g., VS Code or Notepad).
2. **Push the change:**
   ```cmd
   git add .
   git commit -m "Updated medicine pricing screen"
   git push
   ```
3. **Done!** Vercel and Render immediately update the live web application. No server restarting, no terminal commands, no DB resetting.
