import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { test } from "node:test";
import { createApp } from "../src/app.js";

const hash = (value) => createHash("sha256").update(value).digest("hex");

test("email registration creates a user and login session", async () => {
  const users = new Map();
  const sessions = new Map();
  const pool = {
    async query(sql, params = []) {
      if (sql.startsWith("SELECT id FROM app_users WHERE lower(email)")) {
        const user = [...users.values()].find((item) => item.email === params[0]);
        return { rows: user ? [{ id: user.id }] : [] };
      }
      if (sql.includes('password_hash AS "passwordHash"')) {
        const user = [...users.values()].find((item) => item.email === params[0]);
        return { rows: user ? [{ id: user.id, email: user.email, displayName: user.displayName, avatarUrl: null, passwordHash: user.passwordHash }] : [] };
      }
      if (sql.startsWith("INSERT INTO app_users")) {
        users.set(params[0], { id: params[0], email: params[1], displayName: params[2], passwordHash: params[3], emailOptIn: params[4], marketingOptIn: params[5], subscriptionStatus: "N", subscriptionPlan: null });
        return { rows: [] };
      }
      if (sql.startsWith("UPDATE app_users\n         SET subscription_status")) {
        const user = users.get(params[0]);
        user.subscriptionStatus = "Y";
        user.subscriptionPlan = params[1];
        return { rows: [{ id: user.id, email: user.email, displayName: user.displayName, avatarUrl: null, subscriptionStatus: "Y", subscriptionPlan: params[1] }] };
      }
      if (sql.startsWith("UPDATE app_users\n         SET email_opt_in")) {
        const user = users.get(params[0]);
        user.emailOptIn = params[1];
        user.marketingOptIn = params[2];
        return { rows: [{ id: user.id, email: user.email, displayName: user.displayName, avatarUrl: null, subscriptionStatus: user.subscriptionStatus, subscriptionPlan: user.subscriptionPlan, emailOptIn: params[1], marketingOptIn: params[2] }] };
      }
      if (sql.startsWith("INSERT INTO auth_sessions")) {
        sessions.set(params[0], params[1]);
        return { rows: [] };
      }
      if (sql.includes("FROM auth_sessions s")) {
        const user = users.get(sessions.get(params[0]));
        return { rows: user ? [{ id: user.id, email: user.email, displayName: user.displayName, avatarUrl: null, subscriptionStatus: user.subscriptionStatus, subscriptionPlan: user.subscriptionPlan, emailOptIn: user.emailOptIn, marketingOptIn: user.marketingOptIn }] : [] };
      }
      if (sql.startsWith("SELECT pg_advisory") || sql.startsWith("DELETE FROM auth_sessions WHERE expires_at") || sql.startsWith("UPDATE app_users SET last_login_at") || ["BEGIN", "COMMIT", "ROLLBACK"].includes(sql)) return { rows: [] };
      throw new Error(`Unexpected query: ${sql}`);
    },
    async connect() { return { query: (sql, params) => pool.query(sql, params), release() {} }; },
  };
  const server = createApp(pool, { provider: {} }).listen(0);
  await new Promise((resolve) => server.once("listening", resolve));
  const base = `http://127.0.0.1:${server.address().port}`;

  try {
    const response = await fetch(`${base}/api/auth/register`, {
      method: "POST",
      headers: { "content-type": "application/json", origin: "http://localhost:5173" },
      body: JSON.stringify({ displayName: "테스트 사용자", email: "PERSON@example.com", password: "secure-password", marketingOptIn: false }),
    });
    assert.equal(response.status, 201);
    assert.equal(users.size, 1);
    assert.match([...users.values()][0].passwordHash, /^scrypt\$/);
    assert.equal([...users.values()][0].emailOptIn, "Y");
    assert.equal([...users.values()][0].marketingOptIn, "N");
    const sessionCookie = response.headers.getSetCookie().find((value) => value.startsWith("shi_session="));
    assert.ok(sessionCookie);
    assert.doesNotMatch(sessionCookie, /Max-Age=/);
    const me = await fetch(`${base}/api/auth/me`, { headers: { cookie: sessionCookie.split(";")[0] } });
    assert.equal((await me.json()).user.email, "person@example.com");
    const subscription = await fetch(`${base}/api/auth/subscription`, {
      method: "POST",
      headers: { "content-type": "application/json", origin: "http://localhost:5173", cookie: sessionCookie.split(";")[0] },
      body: JSON.stringify({ plan: "professional" }),
    });
    assert.equal(subscription.status, 200);
    assert.equal((await subscription.json()).user.subscriptionStatus, "Y");
    const planChange = await fetch(`${base}/api/auth/subscription`, {
      method: "POST",
      headers: { "content-type": "application/json", origin: "http://localhost:5173", cookie: sessionCookie.split(";")[0] },
      body: JSON.stringify({ plan: "enterprise" }),
    });
    assert.equal(planChange.status, 200);
    assert.equal((await planChange.json()).user.subscriptionPlan, "enterprise");
    const preferences = await fetch(`${base}/api/auth/profile/preferences`, {
      method: "PATCH",
      headers: { "content-type": "application/json", origin: "http://localhost:5173", cookie: sessionCookie.split(";")[0] },
      body: JSON.stringify({ emailOptIn: false, marketingOptIn: true }),
    });
    assert.equal(preferences.status, 200);
    assert.equal((await preferences.json()).user.marketingOptIn, "Y");
    const login = await fetch(`${base}/api/auth/login`, {
      method: "POST",
      headers: { "content-type": "application/json", origin: "http://localhost:5173" },
      body: JSON.stringify({ email: "person@example.com", password: "secure-password" }),
    });
    assert.equal(login.status, 200);
    const loginCookie = login.headers.getSetCookie().find((value) => value.startsWith("shi_session="));
    assert.ok(loginCookie);
    assert.doesNotMatch(loginCookie, /Max-Age=/);
    const rememberedLogin = await fetch(`${base}/api/auth/login`, {
      method: "POST",
      headers: { "content-type": "application/json", origin: "http://localhost:5173" },
      body: JSON.stringify({ email: "person@example.com", password: "secure-password", rememberMe: true }),
    });
    const rememberedCookie = rememberedLogin.headers.getSetCookie().find((value) => value.startsWith("shi_session="));
    assert.equal(rememberedLogin.status, 200);
    assert.match(rememberedCookie, /Max-Age=604800/);
  } finally {
    await new Promise((resolve) => server.close(resolve));
  }
});

test("Google login creates and reuses an account, protects data, and revokes logout", async () => {
  const attempts = new Map();
  const users = new Map();
  const accounts = new Map();
  const sessions = new Map();
  const pool = {
    async query(sql, params = []) {
      if (sql.startsWith("DELETE FROM oauth_login_attempts WHERE expires_at")) return { rows: [] };
      if (sql.startsWith("INSERT INTO oauth_login_attempts")) {
        attempts.set(params[0], { verifier: params[1], rememberMe: params[2] });
        return { rows: [] };
      }
      if (sql.startsWith("DELETE FROM oauth_login_attempts WHERE state_hash")) {
        const attempt = attempts.get(params[0]);
        attempts.delete(params[0]);
        return { rows: attempt ? [{ code_verifier: attempt.verifier, remember_me: attempt.rememberMe }] : [] };
      }
      if (sql.includes("FROM auth_sessions s")) {
        const id = sessions.get(params[0]);
        const user = users.get(id);
        return { rows: user ? [{ id, email: user.email, displayName: user.displayName, avatarUrl: user.avatarUrl }] : [] };
      }
      if (sql.startsWith("DELETE FROM auth_sessions WHERE expires_at")) return { rows: [] };
      if (sql.startsWith("DELETE FROM auth_sessions")) {
        sessions.delete(params[0]);
        return { rows: [] };
      }
      if (sql.startsWith("SELECT user_id FROM oauth_accounts")) {
        const user_id = accounts.get(params[0]);
        return { rows: user_id ? [{ user_id }] : [] };
      }
      if (sql.startsWith("INSERT INTO app_users")) {
        users.set(params[0], { email: params[1], displayName: params[2], avatarUrl: params[3] });
        return { rows: [] };
      }
      if (sql.startsWith("UPDATE app_users")) {
        users.set(params[0], { email: params[1], displayName: params[2], avatarUrl: params[3] });
        return { rows: [] };
      }
      if (sql.startsWith("INSERT INTO oauth_accounts")) {
        accounts.set(params[0], params[1]);
        return { rows: [] };
      }
      if (sql.startsWith("INSERT INTO auth_sessions")) {
        sessions.set(params[0], params[1]);
        return { rows: [] };
      }
      if (sql.startsWith("SELECT pg_advisory") || ["BEGIN", "COMMIT", "ROLLBACK"].includes(sql)) return { rows: [] };
      if (sql.includes("FROM vessel_types")) return { rows: [{ id: "container", name: "컨테이너선" }] };
      throw new Error(`Unexpected query: ${sql}`);
    },
    async connect() {
      return { query: (sql, params) => pool.query(sql, params), release() {} };
    },
  };
  const provider = {
    async discover() { return {}; },
    async authorizationUrl(_config, state, verifier) {
      assert.ok(verifier.length > 20);
      return `https://accounts.example/authorize?state=${state}`;
    },
    async exchange(_config, callbackUrl, state, verifier) {
      assert.equal(callbackUrl.searchParams.get("state"), state);
      assert.ok(verifier.length > 20);
      return { sub: "google-subject-123", email: "person@example.com", email_verified: true, name: "홍길동" };
    },
  };
  const server = createApp(pool, { provider }).listen(0);
  await new Promise((resolve) => server.once("listening", resolve));
  const base = `http://127.0.0.1:${server.address().port}`;

  async function login(rememberMe = false) {
    const start = await fetch(`${base}/api/auth/google${rememberMe ? "?remember=1" : ""}`, { redirect: "manual" });
    assert.equal(start.status, 302);
    const state = new URL(start.headers.get("location")).searchParams.get("state");
    const stateCookie = start.headers.getSetCookie().find((value) => value.startsWith("shi_oauth_state="));
    assert.match(stateCookie, /HttpOnly/);
    assert.match(stateCookie, /SameSite=Lax/);
    const invalid = await fetch(`${base}/api/auth/google/callback?state=wrong&code=abc`, {
      redirect: "manual", headers: { cookie: stateCookie.split(";")[0] },
    });
    assert.equal(new URL(invalid.headers.get("location")).searchParams.get("auth_error"), "invalid_state");
    const callback = await fetch(`${base}/api/auth/google/callback?state=${state}&code=abc`, {
      redirect: "manual", headers: { cookie: stateCookie.split(";")[0] },
    });
    assert.equal(callback.status, 303);
    const sessionCookie = callback.headers.getSetCookie().find((value) => value.startsWith("shi_session="));
    assert.ok(sessionCookie);
    if (rememberMe) assert.match(sessionCookie, /Max-Age=604800/);
    else assert.doesNotMatch(sessionCookie, /Max-Age=/);
    return sessionCookie.split(";")[0];
  }

  try {
    assert.equal((await fetch(`${base}/api/v1/vessels`)).status, 401);
    const first = await login();
    assert.equal(users.size, 1);
    assert.equal(accounts.size, 1);
    assert.ok(sessions.has(hash(first.split("=")[1])));
    const me = await fetch(`${base}/api/auth/me`, { headers: { cookie: first } });
    assert.equal(me.status, 200);
    const firstId = (await me.json()).user.id;
    assert.equal((await fetch(`${base}/api/v1/vessels`, { headers: { cookie: first } })).status, 200);
    const second = await login(true);
    assert.equal(users.size, 1);
    const secondMe = await fetch(`${base}/api/auth/me`, { headers: { cookie: second } });
    assert.equal((await secondMe.json()).user.id, firstId);
    assert.equal((await fetch(`${base}/api/auth/logout`, {
      method: "POST", headers: { cookie: second, origin: "https://other.example" },
    })).status, 403);
    const logout = await fetch(`${base}/api/auth/logout`, {
      method: "POST", headers: { cookie: second, origin: "http://localhost:5173" },
    });
    assert.equal(logout.status, 204);
    assert.equal((await fetch(`${base}/api/auth/me`, { headers: { cookie: second } })).status, 401);
  } finally {
    await new Promise((resolve) => server.close(resolve));
  }
});
