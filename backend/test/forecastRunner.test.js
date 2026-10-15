import assert from "node:assert/strict";
import { after, before, test } from "node:test";
import { getCustomForecastConfig, runCustomForecast } from "../src/forecastRunner.js";

const originalFetch = globalThis.fetch;
const originalServiceUrl = process.env.FORECAST_SERVICE_URL;
const originalProjectRoot = process.env.FORECAST_PROJECT_ROOT;
const requests = [];

before(() => {
  delete process.env.FORECAST_PROJECT_ROOT;
  process.env.FORECAST_SERVICE_URL = "https://forecast.example.test/";
  globalThis.fetch = async (url, options) => {
    requests.push({ url, options });
    const payload = JSON.parse(options.body);
    return new Response(JSON.stringify({ ok: true, vesselId: payload.vesselId }), {
      status: 200,
      headers: { "content-type": "application/json" },
    });
  };
});

after(() => {
  globalThis.fetch = originalFetch;
  if (originalServiceUrl === undefined) delete process.env.FORECAST_SERVICE_URL;
  else process.env.FORECAST_SERVICE_URL = originalServiceUrl;
  if (originalProjectRoot === undefined) delete process.env.FORECAST_PROJECT_ROOT;
  else process.env.FORECAST_PROJECT_ROOT = originalProjectRoot;
});

test("uses the shared forecast service when a local project is unavailable", async () => {
  const result = await runCustomForecast({ vesselId: "bulk", observationMonth: "2026-07", values: {} });
  assert.deepEqual(result, { ok: true, vesselId: "bulk" });
  assert.equal(requests.at(-1).url, "https://forecast.example.test/api/forecast?action=run");
  assert.equal(requests.at(-1).options.method, "POST");
});

test("loads portable forecast configuration from the shared service", async () => {
  const result = await getCustomForecastConfig("container");
  assert.deepEqual(result, { ok: true, vesselId: "container" });
  assert.equal(requests.at(-1).url, "https://forecast.example.test/api/forecast?action=config");
});
