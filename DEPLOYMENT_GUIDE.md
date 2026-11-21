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
When deploying to the cloud (100% Free Stack: **Neon + Oracle Cloud Always Free + Vercel**), the system uses **CI/CD Continuous Deployment**:

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
      VERCEL (Frontend)                  ORACLE CLOUD VM (Backend)
  * Detects git push                      * Checks GitHub every 5 min
  * Rebuilds React in 30s                 * Rebuilds FastAPI (Docker)
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

### Step 3: Deploy Backend on Oracle Cloud Always Free VM (Free, never sleeps)
Oracle's Always Free VM runs 24/7 with no time limit and no sleeping, unlike Render's free tier.

1. Sign up at [oracle.com/cloud/free](https://www.oracle.com/cloud/free/). A card is needed for verification only; Always Free resources are never charged. Pick a nearby **Home Region** (e.g. Mumbai or Hyderabad). It can't be changed later.
2. **Compute ➔ Instances ➔ Create Instance**:
   * **Image:** Canonical Ubuntu 24.04
   * **Shape:** `VM.Standard.A1.Flex` (Ampere, 1 OCPU / 6 GB is plenty) or `VM.Standard.E2.1.Micro`. Both are marked *Always Free-eligible*.
   * Download the SSH private key. Create.
3. Open ports 80 and 443 in Oracle's network firewall: Instance ➔ **Subnet** ➔ **Default Security List** ➔ **Add Ingress Rules** ➔ Source `0.0.0.0/0`, TCP, destination port `80,443`.
4. SSH in (`ssh -i key.pem ubuntu@<PUBLIC_IP>`) and run:
   ```bash
   git clone https://github.com/<YOUR_GITHUB_USERNAME>/saran-ashram-dispenserdesk.git ~/dispenserdesk
   bash ~/dispenserdesk/deploy/oracle/setup.sh
   ```
   The first run installs Docker, opens the VM's own firewall and creates `deploy/.env.oracle`. It generates the secrets and an `API_DOMAIN` like `140-238-12-34.sslip.io` for you. sslip.io is a free hostname, so you don't need to buy a domain.
5. Edit the env file and paste your Neon string. It must start with `postgresql+psycopg://`. To keep existing logins valid, reuse the `JWT_SECRET` and `SYNC_SHARED_SECRET` you had on Render.
   ```bash
   nano ~/dispenserdesk/deploy/.env.oracle
   bash ~/dispenserdesk/deploy/oracle/setup.sh
   ```
   The second run starts the API behind Caddy, which gets and renews a free HTTPS certificate automatically. It also turns on auto-deploy: a cron job pulls `main` every 5 minutes and rebuilds the API when something changed.
6. Check `https://<API_DOMAIN>/api/health` in a browser. That URL is your backend URL.

> Private repo? Make the VM able to pull it: create a GitHub **deploy key** (read-only) on the VM and clone with the `git@github.com:` URL.

---

### Step 4: Deploy Frontend on Vercel (Free)
1. Go to [vercel.com](https://vercel.com) and sign in with GitHub.
2. Click **"Add New..."** ➔ **"Project"** ➔ Import `dispensary-desk`.
3. Settings:
   * **Root Directory:** Click "Edit" and choose `frontend`
   * **Framework Preset:** `Vite`
4. Add **Environment Variable**:
   * In `frontend/vercel.json`, set the `/api/:match*` rewrite destination to `https://<API_DOMAIN>/api/:match*` *(your Oracle backend URL)* and push.
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
3. **Done!** Vercel updates the frontend immediately and the Oracle VM picks up the backend within 5 minutes; together they update the live web application. No server restarting, no terminal commands, no DB resetting.
