import { readFile, readdir } from "node:fs/promises";
import path from "node:path";
import pg from "pg";
import { parse } from "csv-parse/sync";

const sourceDirectory = process.argv[2];
if (!sourceDirectory || !process.env.DATABASE_URL) {
  throw new Error("Usage: npm run import:master -- <CSV directory> (DATABASE_URL required)");
}

const sources = [
  { filename: "마스터테이블(가스 운반선).csv", id: "gas", name: "가스 운반선", unit: "CBM" },
  { filename: "마스터테이블(벌크선).csv", id: "bulk", name: "벌크선", unit: "DWT" },
  { filename: "마스터테이블(유조선).csv", id: "tanker", name: "유조선", unit: "DWT" },
  { filename: "마스터테이블(컨테이너선).csv", id: "container", name: "컨테이너선", unit: "TEU" },
  { filename: "마스터테이블(케미컬 탱커).csv", id: "chemical", name: "케미컬 탱커", unit: "DWT" },
];

const baseColumns = new Set(["기준월", "수주용량", "수주용량단위", "수주정보시차(개월)", "수주정보가용근거"]);
const numberPattern = /^-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?$/;

function numeric(value, field, source, period) {
  const normalized = value.trim();
  if (normalized === "") return null;
  if (!numberPattern.test(normalized) || !Number.isFinite(Number(normalized))) {
    throw new Error(`${source.filename} ${period}: invalid number in ${field}: ${value}`);
  }
  return normalized;
}

const availableFiles = new Set(await readdir(sourceDirectory));
const imports = [];
for (const source of sources) {
  if (!availableFiles.has(source.filename)) throw new Error(`Missing ${source.filename}`);
  const csv = await readFile(path.join(sourceDirectory, source.filename), "utf8");
  let headers;
  const rows = parse(csv, {
    bom: true,
    skip_empty_lines: true,
    columns: (columns) => {
      if (new Set(columns).size !== columns.length || ![...baseColumns].every((column) => columns.includes(column))) {
        throw new Error(`${source.filename}: duplicate or missing required header`);
      }
      headers = columns;
      return columns;
    },
  });
  const months = new Set();
  const records = [];
  const features = [];
  const sourceRows = [];
  const numericColumns = new Set(headers.filter((column) => !baseColumns.has(column) && rows.every((row) => {
    const value = row[column];
    const normalized = value.trim();
    return normalized === "" || (numberPattern.test(normalized) && Number.isFinite(Number(normalized)));
  })));
  for (const row of rows) {
    const month = row["기준월"];
    if (!/^\d{4}-(0[1-9]|1[0-2])$/.test(month) || months.has(month)) {
      throw new Error(`${source.filename}: invalid or duplicate month ${month}`);
    }
    months.add(month);
    if (row["수주용량단위"] !== source.unit) {
      throw new Error(`${source.filename} ${month}: expected ${source.unit} unit`);
    }
    const period = `${month}-01`;
    sourceRows.push({ period, row });
    const capacity = numeric(row["수주용량"], "수주용량", source, month);
    if (capacity !== null && Number(capacity) < 0) throw new Error(`${source.filename} ${month}: negative capacity`);
    const lag = numeric(row["수주정보시차(개월)"], "수주정보시차(개월)", source, month);
    if (lag !== null && (!Number.isInteger(Number(lag)) || Number(lag) < 0)) {
      throw new Error(`${source.filename} ${month}: invalid information lag`);
    }
    records.push({ period, capacity, lag: lag === null ? null : Number(lag), basis: row["수주정보가용근거"] || null });
    for (const column of headers) {
      if (!numericColumns.has(column)) continue;
      const value = numeric(row[column], column, source, month);
      if (value !== null) features.push({ period, name: column, value });
    }
  }
  imports.push({ ...source, records, features, sourceRows });
}

const pool = new pg.Pool({ connectionString: process.env.DATABASE_URL });
const client = await pool.connect();
try {
  await client.query("BEGIN");
  for (const source of imports) {
    await client.query(
      `INSERT INTO vessel_types (id, name) VALUES ($1, $2)
       ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name`,
      [source.id, source.name],
    );
    await client.query("DELETE FROM vessel_monthly_features WHERE vessel_type_id = $1", [source.id]);
    await client.query("DELETE FROM vessel_monthly_source_rows WHERE vessel_type_id = $1", [source.id]);
    for (const record of source.records) {
      await client.query(
        `INSERT INTO vessel_monthly_master
           (vessel_type_id, period, order_capacity, order_capacity_unit, order_info_lag_months, order_info_basis, source_filename)
         VALUES ($1, $2, $3, $4, $5, $6, $7)
         ON CONFLICT (vessel_type_id, period) DO UPDATE SET
           order_capacity = EXCLUDED.order_capacity,
           order_capacity_unit = EXCLUDED.order_capacity_unit,
           order_info_lag_months = EXCLUDED.order_info_lag_months,
           order_info_basis = EXCLUDED.order_info_basis,
           source_filename = EXCLUDED.source_filename,
           imported_at = now()`,
        [source.id, record.period, record.capacity, source.unit, record.lag, record.basis, source.filename],
      );
    }
    for (let offset = 0; offset < source.features.length; offset += 500) {
      const batch = source.features.slice(offset, offset + 500);
      const params = batch.flatMap((feature) => [source.id, feature.period, feature.name, feature.value]);
      const placeholders = batch.map((_, index) => {
        const start = index * 4;
        return `($${start + 1}, $${start + 2}, $${start + 3}, $${start + 4})`;
      });
      await client.query(
        `INSERT INTO vessel_monthly_features (vessel_type_id, period, feature_name, value)
         VALUES ${placeholders.join(", ")}`,
        params,
      );
    }
    for (let offset = 0; offset < source.sourceRows.length; offset += 100) {
      const batch = source.sourceRows.slice(offset, offset + 100);
      const params = batch.flatMap((item) => [source.id, item.period, source.filename, JSON.stringify(item.row)]);
      const placeholders = batch.map((_, index) => {
        const start = index * 4;
        return `($${start + 1}, $${start + 2}, $${start + 3}, $${start + 4}::jsonb)`;
      });
      await client.query(
        `INSERT INTO vessel_monthly_source_rows (vessel_type_id, period, source_filename, row_data)
         VALUES ${placeholders.join(", ")}`,
        params,
      );
    }
    console.log(`${source.name}: ${source.records.length} months, ${source.features.length} feature values`);
  }
  await client.query("COMMIT");
} catch (error) {
  await client.query("ROLLBACK");
  throw error;
} finally {
  client.release();
  await pool.end();
}
