import { execFile } from "node:child_process";
import { existsSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { promisify } from "node:util";

const execFileAsync = promisify(execFile);
const localProjectRoot = "G:\\.shortcut-targets-by-id\\1Mzfsu50R-PR3fJQBchRx64TKYIX8S8Pj\\SHI_DT_2nd_project\\01 기획\\Ship orders forcasting";
export const NOTEBOOK_FORECAST_VESSELS = new Set(["container", "tanker", "bulk", "gas", "chemical"]);
const configCache = new Map();

async function callForecastRunner(action, payload) {
  const projectRoot = process.env.FORECAST_PROJECT_ROOT || localProjectRoot;
  if (!existsSync(projectRoot)) throw new Error("FORECAST_PROJECT_ROOT에서 수주예측 프로젝트를 찾을 수 없습니다.");
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

export function getCustomForecastConfig(vesselId) {
  if (!configCache.has(vesselId)) configCache.set(vesselId, callForecastRunner("config", { vesselId }));
  return configCache.get(vesselId);
}

export function runCustomForecast(payload) {
  return callForecastRunner("run", payload);
}
