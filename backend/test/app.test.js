import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { after, before, test } from "node:test";
import { createApp } from "../src/app.js";

const calls = [];
const pool = {
  async query(sql, params) {
    calls.push({ sql, params });
    if (sql === "SELECT 1") return { rows: [{ "?column?": 1 }] };
    if (sql.includes("FROM auth_sessions s")) {
      const exploreHash = createHash("sha256").update("explore-session").digest("hex");
      const subscriptionPlan = params[0] === exploreHash ? "explore" : "enterprise";
      return { rows: [{ id: "test-user", email: "test@example.com", displayName: "테스트", avatarUrl: null, subscriptionStatus: "Y", subscriptionPlan }] };
    }
    if (sql.includes("FROM monthly_orders")) {
      return { rows: [{ vesselId: "container", year: 2026, month: 1, cgt: 600000 }] };
    }
    return { rows: [{ id: "container", name: "컨테이너선" }] };
  },
};

let server;
let baseUrl;
const authenticated = { headers: { cookie: "shi_session=test-session" } };
const exploreAuthenticated = { headers: { cookie: "shi_session=explore-session" } };

before(async () => {
  server = createApp(pool).listen(0);
  await new Promise((resolve) => server.once("listening", resolve));
  baseUrl = `http://127.0.0.1:${server.address().port}`;
});

after(async () => {
  await new Promise((resolve) => server.close(resolve));
});

test("health and readiness endpoints respond", async () => {
  const health = await fetch(`${baseUrl}/api/health`);
  const ready = await fetch(`${baseUrl}/api/ready`);
  assert.deepEqual(await health.json(), { status: "ok" });
  assert.deepEqual(await ready.json(), { status: "ok" });
});

test("market orders require a valid year", async () => {
  for (const query of ["", "?year=1999", "?year=2026x", "?year=2026&year=2025"]) {
    const response = await fetch(`${baseUrl}/api/v1/market/orders${query}`, authenticated);
    assert.equal(response.status, 400);
  }
});

test("market orders use a parameterized year", async () => {
  const response = await fetch(`${baseUrl}/api/v1/market/orders?year=2026`, authenticated);
  assert.equal(response.status, 200);
  assert.deepEqual(await response.json(), [
    { vesselId: "container", year: 2026, month: 1, cgt: 600000 },
  ]);
  assert.deepEqual(calls.at(-1).params, [2026]);
});

test("market endpoints require a login session", async () => {
  const response = await fetch(`${baseUrl}/api/v1/vessels`);
  assert.equal(response.status, 401);
});

test("custom forecast accepts only supported vessel types", async () => {
  const response = await fetch(`${baseUrl}/api/v1/custom-forecast/run`, {
    ...authenticated,
    method: "POST",
    headers: { ...authenticated.headers, "content-type": "application/json" },
    body: JSON.stringify({ vesselId: "lng" }),
  });
  assert.equal(response.status, 400);
  assert.match((await response.json()).error, /container/);
});

test("plan-restricted APIs reject insufficient subscriptions", async () => {
  const masterData = await fetch(`${baseUrl}/api/v1/master-data?vesselId=container`, exploreAuthenticated);
  const customForecast = await fetch(`${baseUrl}/api/v1/custom-forecast/config?vesselId=container`, exploreAuthenticated);
  const shipPulse = await fetch(`${baseUrl}/api/v1/ship-pulse`, exploreAuthenticated);
  assert.equal(masterData.status, 403);
  assert.equal(customForecast.status, 403);
  assert.equal(shipPulse.status, 403);
});

test("ShipPulse HTML is available to Enterprise subscriptions", async () => {
  const response = await fetch(`${baseUrl}/api/v1/ship-pulse`, authenticated);
  assert.equal(response.status, 200);
  assert.match(response.headers.get("content-type"), /^text\/html/);
  assert.equal(response.headers.get("cache-control"), "private, no-store");
  assert.match(await response.text(), /수주용량과 CSV 지표 보기/);
});

test("unconfigured Google login returns to the login screen", async () => {
  const response = await fetch(`${baseUrl}/api/auth/google`, { redirect: "manual" });
  assert.equal(response.status, 303);
  assert.equal(new URL(response.headers.get("location")).searchParams.get("auth_error"), "not_configured");
});
