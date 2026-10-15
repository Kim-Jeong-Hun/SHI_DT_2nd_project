import pg from "pg";
import { createApp } from "./app.js";

const { DATABASE_URL, PORT = "3001" } = process.env;

if (!DATABASE_URL) {
  console.error("DATABASE_URL is required. See backend/.env.example.");
  process.exit(1);
}

const port = Number(PORT);
if (!Number.isInteger(port) || port < 1 || port > 65535) {
  console.error("PORT must be an integer between 1 and 65535.");
  process.exit(1);
}

const pool = new pg.Pool({ connectionString: DATABASE_URL });
const server = createApp(pool, {
  frontendUrl: process.env.FRONTEND_URL,
  googleClientId: process.env.GOOGLE_CLIENT_ID,
  googleClientSecret: process.env.GOOGLE_CLIENT_SECRET,
  googleRedirectUri: process.env.GOOGLE_REDIRECT_URI,
}).listen(port, () => {
  console.log(`API listening on http://localhost:${port}`);
});

async function shutdown() {
  server.close();
  await pool.end();
}

process.once("SIGINT", shutdown);
process.once("SIGTERM", shutdown);
