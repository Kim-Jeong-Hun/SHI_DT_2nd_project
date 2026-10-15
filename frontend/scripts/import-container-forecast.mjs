import { readFileSync, writeFileSync } from "node:fs";
import { createHash } from "node:crypto";
import { basename, dirname, resolve } from "node:path";

// Import a vessel notebook's saved output; do not retrain or substitute mock values.
const notebookPath = process.argv[2];
if (!notebookPath) throw new Error("Usage: node scripts/import-container-forecast.mjs <notebook.ipynb>");
const vesselName = basename(notebookPath).match(/수주예측\((.+)\)_WAPE_3M/)?.[1];
const vesselConfig = {
  "컨테이너선": { id: "container", csvVessel: "Container" },
  "유조선": { id: "tanker", csvVessel: "Oil Tanker" },
  "벌크선": { id: "bulk", csvVessel: "Bulk Carrier" },
  "가스 운반선": { id: "gas", csvVessel: "Gas Carrier" },
  "케미컬 탱커": { id: "chemical", csvVessel: "Chemical Tanker" },
}[vesselName];
if (!vesselConfig) throw new Error(`Unsupported vessel notebook: ${basename(notebookPath)}`);
const raw = readFileSync(notebookPath);
const notebook = JSON.parse(raw.toString("utf8").replace(/^\uFEFF/, ""));
const sourceCell = notebook.cells.findIndex((cell) => cell.source.join("").includes("display(운영전망선.assign("));
if (sourceCell < 0) throw new Error("Monthly operational forecast cell not found");
const outputText = (cell) => (cell.outputs ?? []).map((output) =>
  (output.data?.["text/plain"] ?? output.text ?? []).join("")).join("\n");
const points = [...outputText(notebook.cells[sourceCell]).matchAll(
  /^\s*\d+\s+(\d{4}-\d{2})\s+(\d{4}-\d{2})\s+(\d{4}-\d{2})(?:\s+예측 가능)?\s+([\d.]+)/gm,
)].map(([, issuedMonth, dataCutoffMonth, targetMonth, prediction]) => ({
  issuedMonth, dataCutoffMonth, targetMonth, predictionTeu: Number(prediction),
})).filter((point) => point.targetMonth >= "2026-10" && point.targetMonth <= "2026-12");
if (points.length !== 3 || points.some((point, i) =>
  point.targetMonth !== `2026-${10 + i}` || point.issuedMonth !== `2026-0${7 + i}` || !Number.isFinite(point.predictionTeu))) {
  throw new Error(`Expected three available C+3 predictions for October–December 2026:\n${outputText(notebook.cells[sourceCell]).slice(0, 1600)}`);
}
const allOutput = notebook.cells.map(outputText).join("\n");
const model = allOutput.match(/최종 모형: ([^\r\n]+)/)?.[1];
if (!model) throw new Error("Saved final model name not found");
const actualPath = resolve(dirname(notebookPath), `../../data/processed/${vesselName}/${vesselName} 수주실적(월).csv`);
const actualRows = readFileSync(actualPath, "utf8").replace(/^\uFEFF/, "").trim().split(/\r?\n/);
const unit = actualRows[0].match(/^기준월,선종,수주용량\(([^)]+)\),/)?.[1];
if (!unit) throw new Error("Unexpected actual-order CSV columns");
const actuals = actualRows.slice(1).map((row) => {
  const [month, vessel, amount] = row.split(",", 3);
  if (vessel !== vesselConfig.csvVessel || !/^\d{4}-\d{2}$/.test(month) || !Number.isFinite(Number(amount))) {
    throw new Error(`Invalid actual-order row: ${row}`);
  }
  return { month, valueTeu: Number(amount) };
}).filter((point) => point.month <= "2026-08");
if (!actuals.length || actuals.at(-1)?.month !== "2026-08") {
  throw new Error(`Expected ${vesselName} history through August 2026`);
}
const data = {
  source: { notebook: basename(notebookPath), cell: sourceCell, sha256: createHash("sha256").update(raw).digest("hex"), actualsFile: basename(actualPath), precisionDecimals: 1 },
  vesselId: vesselConfig.id, vesselName, asOfMonth: "2026-09", unit, horizonMonths: 3, trainMonths: 48, model, actuals, points,
};
writeFileSync(new URL(`../src/data/${vesselConfig.id}Forecast.json`, import.meta.url), JSON.stringify(data, null, 2) + "\n");
console.log(`Imported ${vesselName}: ${points.length} saved forecasts (${model}); quarter total ${points.reduce((sum, p) => sum + Math.round(p.predictionTeu * 10), 0) / 10} ${unit}`);
