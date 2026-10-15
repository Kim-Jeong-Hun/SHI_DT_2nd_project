import { readFile } from "node:fs/promises";
import path from "node:path";
import pg from "pg";
import { parse } from "csv-parse/sync";

const sourceRoot = process.argv[2];
if (!sourceRoot || !process.env.DATABASE_URL) {
  throw new Error("Usage: npm run import:clusters -- <analysis root directory> (DATABASE_URL required)");
}

const modelKey = "regime_v2_final";
const labelFilename = "국면v2_최종_월별라벨.csv";
const configFilename = "국면v2_최종설정.json";
const sources = [
  { id: "gas", directory: "가스_운반선" },
  { id: "bulk", directory: "벌크선" },
  { id: "tanker", directory: "유조선" },
  { id: "container", directory: "컨테이너선" },
  { id: "chemical", directory: "케미컬_탱커" },
];
const numberPattern = /^-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?$/;

function numeric(value, filename, period, field) {
  if (value === "") return null;
  if (!numberPattern.test(value) || !Number.isFinite(Number(value))) {
    throw new Error(`${filename} ${period}: invalid number in ${field}: ${value}`);
  }
  return value;
}

const imports = [];
for (const source of sources) {
  const folder = path.join(sourceRoot, source.directory);
  const config = JSON.parse(await readFile(path.join(folder, configFilename), "utf8"));
  if (typeof config["모델"] !== "string" || !Number.isInteger(config["군집수"]) || config["군집수"] < 1) {
    throw new Error(`${source.directory}: invalid final model configuration`);
  }
  let headers;
  const rows = parse(await readFile(path.join(folder, labelFilename), "utf8"), {
    bom: true,
    skip_empty_lines: true,
    columns: (columns) => {
      if (new Set(columns).size !== columns.length || !columns.includes("기준월") || !columns.includes("군집")) {
        throw new Error(`${source.directory}: duplicate or missing label header`);
      }
      headers = columns;
      return columns;
    },
  });
  const months = new Set();
  const assignments = [];
  const metrics = [];
  for (const row of rows) {
    const period = row["기준월"];
    if (!/^\d{4}-(0[1-9]|1[0-2])-01$/.test(period) || months.has(period)) {
      throw new Error(`${source.directory}: invalid or duplicate month ${period}`);
    }
    months.add(period);
    const cluster = Number(row["군집"]);
    if (!Number.isInteger(cluster) || cluster < 1 || cluster > config["군집수"]) {
      throw new Error(`${source.directory} ${period}: invalid cluster number ${row["군집"]}`);
    }
    assignments.push({ period, cluster });
    for (const header of headers) {
      if (header === "기준월" || header === "군집") continue;
      const value = numeric(row[header], labelFilename, period, header);
      if (value !== null) metrics.push({ period, name: header, value });
    }
  }
  imports.push({ ...source, config, assignments, metrics });
}

const pool = new pg.Pool({ connectionString: process.env.DATABASE_URL });
const client = await pool.connect();
try {
  await client.query("BEGIN");
  for (const source of imports) {
    await client.query(
      "DELETE FROM cluster_models WHERE vessel_type_id = $1 AND model_key = $2",
      [source.id, modelKey],
    );
    await client.query(
      `INSERT INTO cluster_models
         (vessel_type_id, model_key, method, cluster_count, configuration, source_filename)
       VALUES ($1, $2, $3, $4, $5, $6)`,
      [source.id, modelKey, source.config["모델"], source.config["군집수"], source.config, labelFilename],
    );
    for (const assignment of source.assignments) {
      await client.query(
        `INSERT INTO cluster_monthly_assignments
           (vessel_type_id, model_key, period, cluster_number)
         VALUES ($1, $2, $3, $4)`,
        [source.id, modelKey, assignment.period, assignment.cluster],
      );
    }
    for (let offset = 0; offset < source.metrics.length; offset += 500) {
      const batch = source.metrics.slice(offset, offset + 500);
      const params = batch.flatMap((metric) => [source.id, modelKey, metric.period, metric.name, metric.value]);
      const placeholders = batch.map((_, index) => {
        const start = index * 5;
        return `($${start + 1}, $${start + 2}, $${start + 3}, $${start + 4}, $${start + 5})`;
      });
      await client.query(
        `INSERT INTO cluster_monthly_metrics
           (vessel_type_id, model_key, period, metric_name, value)
         VALUES ${placeholders.join(", ")}`,
        params,
      );
    }
    console.log(`${source.id}: ${source.assignments.length} monthly labels, ${source.metrics.length} metrics`);
  }
  await client.query("COMMIT");
} catch (error) {
  await client.query("ROLLBACK");
  throw error;
} finally {
  client.release();
  await pool.end();
}
