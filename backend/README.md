# Backend

Express API backed by PostgreSQL. A Supabase project's PostgreSQL connection string can be used as `DATABASE_URL`.

## Run locally with Docker Desktop

1. Start Docker Desktop.
2. Copy `.env.example` to `.env`. Set `POSTGRES_PASSWORD` and use the same password in `DATABASE_URL` (URL-encode special characters in the latter).
3. Run `docker compose up -d db` from this directory. The first start creates the database and applies the SQL files in `sql/`.
4. Run `npm install` and `npm run dev` from this directory.

Check database connectivity at `http://localhost:3001/api/ready`. PostgreSQL listens only on the local machine at port 5432. `docker compose down` stops it; its named volume keeps data between restarts. The initialization SQL runs only when the volume is first created. Apply later schema changes separately as migrations.

## Vessel master data

Run `npm run db:migrate` after the database is running. To import the five vessel master CSV files, put them in one directory and run:

```powershell
npm run import:master -- "C:\path\to\master-csv-directory"
```

The import updates existing monthly records and refreshes their source rows and numeric feature values in a single transaction, so repeating it with the same files does not duplicate records or remove linked cluster labels. It does not modify the source CSV files. The current import contains 825 monthly records (165 per vessel) and 43,134 nonempty numeric feature values.

- `vessel_monthly_master`: vessel, month, order capacity, its original unit (CBM/DWT/TEU), information lag, and provenance.
- `vessel_monthly_features`: one numeric value per vessel, month, and original CSV column name. Blank values are omitted, while zero is retained.
- `vessel_monthly_source_rows`: the complete original CSV row as JSONB, preserving every column—including text-valued labels—in its source form for future analysis pipelines.

The source files are analysis inputs and have no cluster assignment columns. The existing `monthly_orders` table and API are CGT-only and remain separate because CBM, DWT, and TEU cannot be combined as CGT without a defined conversion.

## Cluster results

The five graph notebooks read the vessel master CSV files and explore variables; they do not calculate cluster assignments. Their adjacent `국면v2_최종_월별라벨.csv` and `국면v2_최종설정.json` files contain the final v2 monthly labels and model settings. Import them after the master data:

```powershell
npm run import:clusters -- "C:\path\to\analysis-root-directory"
```

The root directory must contain the five vessel folders. The import stores 634 monthly labels under the model key `regime_v2_final` and 1,792 nonempty metric values. It refreshes only that model key, leaving other model variants untouched.

- `cluster_models`: vessel, model key, method, cluster count, and complete JSON configuration.
- `cluster_monthly_assignments`: one cluster number per vessel, model, and month, linked to the master data.
- `cluster_monthly_metrics`: transformed values from the label CSV, retaining the original column names and exact numeric values.

To use an existing PostgreSQL server or Supabase instead, set `DATABASE_URL` to its connection string and run `npm run db:migrate`. For Supabase, follow its SSL and pooler settings.

The server starts on port 3001 unless `PORT` is set. The vessel master CSV data is loaded by the import command above; `monthly_orders` remains separate. `cgt` stores raw CGT, rather than the frontend mock data's ten-thousand-CGT display unit.

## Newsroom

The newsroom stores article metadata in the separate `newsroom` PostgreSQL schema. Run `npm run db:migrate`, then `npm run news:sync` from `backend/` to import recent articles from Logistics Newspaper, Maeil Business Newspaper, Korea Economic Daily, Yonhap News Agency, and HD Hyundai Heavy Industries' newsroom. The sync stores the source, category, headline, publication date, original article URL, and publisher image URL. Images remain hosted by the publisher and are displayed with a link to the original article.

`GET /api/v1/newsroom` returns the three lead articles and the remaining recent articles for the signed-in dashboard.

## Endpoints

- `GET /api/health` — process health
- `GET /api/ready` — database connectivity
- `GET /api/v1/vessels` — vessel type IDs and names
- `GET /api/v1/master-data?vesselId=chemical&from=2020-01&to=2026-08` — original source rows plus parsed numeric features for one vessel and optional inclusive month range
- `GET /api/v1/market/orders?year=2026` — monthly orders for one year, in raw CGT

The `/api/v1` endpoints require a valid login session. The health and readiness endpoints remain public.

## Google login

The frontend uses Google OpenID Connect to sign users in. Express verifies the authorization response and manages accounts and sessions in PostgreSQL. First login creates an `app_users` row and a linked `oauth_accounts` row; later logins with the same Google subject reuse that account. The browser receives an HTTP-only session cookie; the database holds only its SHA-256 hash. Logout deletes the session.

1. Start PostgreSQL and run `npm run db:migrate` to create the four auth tables.
2. In Google Cloud Console, configure the OAuth consent screen and create an **OAuth client ID** of type **Web application**. Add `http://localhost:3001/api/auth/google/callback` to **Authorized redirect URIs**. If the app is in testing mode, add the Google accounts that should be allowed to sign in as test users.
3. Set `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` in the ignored `backend/.env`. Keep `GOOGLE_REDIRECT_URI=http://localhost:3001/api/auth/google/callback` and `FRONTEND_URL=http://localhost:5173` for local development. The redirect URI must match the Google Cloud setting exactly.
4. Start the API with `npm run dev` in `backend/` and the frontend with `npm run dev` in `frontend/`. Visit `http://localhost:5173` and choose **Google 계정으로 계속하기**.

The Vite development server proxies `/api` to the Express server. The production frontend uses a Vercel rewrite so browser requests to `https://shipulse.vercel.app/api/*` are forwarded to the backend without changing the browser origin. Configure the backend Vercel project with the following production values:

```text
DATABASE_URL=<publicly reachable PostgreSQL connection string>
FRONTEND_URL=https://shipulse.vercel.app
GOOGLE_CLIENT_ID=<Google OAuth client ID>
GOOGLE_CLIENT_SECRET=<Google OAuth client secret>
GOOGLE_REDIRECT_URI=https://shipulse.vercel.app/api/auth/google/callback
```

Register the same `GOOGLE_REDIRECT_URI` as an authorized redirect URI in Google Cloud Console. A database URL pointing to `localhost` cannot be reached by Vercel. Never commit deployment credentials or the client secret.

Auth endpoints: `GET /api/auth/google` starts login, `GET /api/auth/google/callback` completes it, `GET /api/auth/me` returns the current user, and `POST /api/auth/logout` revokes the session.

`year` is required and must be between 2000 and 2100. Database errors return JSON with an `error` field.
