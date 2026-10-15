import { execFile } from "node:child_process";
import { existsSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { promisify } from "node:util";

const execFileAsync = promisify(execFile);
const defaultForecastServiceUrl = "https://shipulse-backend.vercel.app";
export const NOTEBOOK_FORECAST_VESSELS = new Set(["container", "tanker", "bulk", "gas", "chemical"]);
const configCache = new Map();

async function callLocalForecastRunner(action, payload, projectRoot) {
  const script = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../scripts/custom-forecast.py");
  const venvPython = path.join(projectRoot, "scripts", "분석", ".venv", "Scripts", "python.exe");
  const python = process.env.FORECAST_PYTHON || (existsSync(venvPython) ? venvPython : "python");
  const encodedPayload = Buffer.from(JSON.stringify(payload), "utf8").toString("base64");
  const { stdout } = await execFileAsync(python, [script, projectRoot, action, encodedPayload], {
    cwd: projectRoot,
    encoding: "utf8",
    env: { ...process.env, PYTHONUTF8: "1", PYTHONIOENCODING: "utf-8" },
    maxBuffer: 4 * 1024 * 1024,
    timeout: 10 * 60 * 1000,
    windowsHide: true,
  });
  const line = stdout.split(/\r?\n/).findLast((item) => item.startsWith("__FORECAST_JSON__"));
  if (!line) throw new Error("시나리오 예측 결과를 읽지 못했습니다.");
  return JSON.parse(line.slice("__FORECAST_JSON__".length));
}

async function callForecastService(action, payload) {
  const baseUrl = (process.env.FORECAST_SERVICE_URL || defaultForecastServiceUrl).replace(/\/$/, "");
  const response = await fetch(`${baseUrl}/api/forecast?action=${action}`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(payload),
    signal: AbortSignal.timeout(10 * 60 * 1000),
  });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(body.detail || body.error || "예측 서비스가 요청을 처리하지 못했습니다.");
  return body;
}

async function callForecastRunner(action, payload) {
  const projectRoot = process.env.FORECAST_PROJECT_ROOT;
  if (projectRoot && existsSync(projectRoot)) return callLocalForecastRunner(action, payload, projectRoot);
  return callForecastService(action, payload);
}

export function getCustomForecastConfig(vesselId) {
  if (!configCache.has(vesselId)) {
    const pending = callForecastRunner("config", { vesselId }).catch((error) => {
      configCache.delete(vesselId);
      throw error;
    });
    configCache.set(vesselId, pending);
  }
  return configCache.get(vesselId);
}

export function runCustomForecast(payload) {
  return callForecastRunner("run", payload);
}
