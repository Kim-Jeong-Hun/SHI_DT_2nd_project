import { readFile } from "node:fs/promises";
import pg from "pg";

if (!process.env.DATABASE_URL) {
  throw new Error("DATABASE_URL is required. See backend/.env.example.");
}

const pool = new pg.Pool({ connectionString: process.env.DATABASE_URL });
const client = await pool.connect();
try {
  await client.query("BEGIN");
  for (const filename of ["001_create_market_tables.sql", "002_create_vessel_master_tables.sql", "003_create_cluster_result_tables.sql", "004_create_auth_tables.sql", "005_add_password_auth.sql", "006_add_subscription_status.sql", "007_add_communication_preferences.sql", "008_create_newsroom_schema.sql", "009_default_email_opt_in.sql", "010_create_vessel_source_rows.sql", "011_add_oauth_remember_me.sql"]) {
    const sql = await readFile(new URL(`../sql/${filename}`, import.meta.url), "utf8");
    await client.query(sql);
    console.log(`Applied ${filename}`);
  }
  await client.query("COMMIT");
} catch (error) {
  await client.query("ROLLBACK");
  throw error;
} finally {
  client.release();
  await pool.end();
}
