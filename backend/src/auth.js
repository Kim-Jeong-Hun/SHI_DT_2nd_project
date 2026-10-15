import { createHash, randomBytes, randomUUID, scrypt as scryptCallback, timingSafeEqual } from "node:crypto";
import { promisify } from "node:util";
import express, { Router } from "express";
import { parseCookie } from "cookie";
import * as oidc from "openid-client";

const SESSION_COOKIE = "shi_session";
const STATE_COOKIE = "shi_oauth_state";
const SESSION_AGE_MS = 7 * 24 * 60 * 60 * 1000;
const STATE_AGE_MS = 10 * 60 * 1000;
const scrypt = promisify(scryptCallback);

const hash = (value) => createHash("sha256").update(value).digest("hex");
const cookies = (request) => parseCookie(request.headers.cookie ?? "");
const sameValue = (left, right) => {
  if (typeof left !== "string" || typeof right !== "string") return false;
  const a = Buffer.from(left);
  const b = Buffer.from(right);
  return a.length === b.length && timingSafeEqual(a, b);
};

async function hashPassword(password) {
  const salt = randomBytes(16).toString("base64url");
  const derived = await scrypt(password, salt, 64);
  return `scrypt$${salt}$${Buffer.from(derived).toString("base64url")}`;
}

async function verifyPassword(password, storedHash) {
  const [algorithm, salt, encodedHash] = typeof storedHash === "string" ? storedHash.split("$") : [];
  if (algorithm !== "scrypt" || !salt || !encodedHash) return false;
  const expected = Buffer.from(encodedHash, "base64url");
  const actual = Buffer.from(await scrypt(password, salt, expected.length));
  return expected.length === actual.length && timingSafeEqual(expected, actual);
}

export function createAuth(pool, options = {}) {
  const frontendUrl = new URL(options.frontendUrl ?? "http://localhost:5173");
  const redirectUri = options.googleRedirectUri ?? "http://localhost:3001/api/auth/google/callback";
  const secure = new URL(redirectUri).protocol === "https:";
  const configured = Boolean(options.googleClientId && options.googleClientSecret);
  const provider = options.provider ?? {
    async discover() {
      return oidc.discovery(new URL("https://accounts.google.com"), options.googleClientId, options.googleClientSecret);
    },
    async authorizationUrl(config, state, verifier) {
      return oidc.buildAuthorizationUrl(config, {
        redirect_uri: redirectUri,
        scope: "openid email profile",
        state,
        code_challenge: await oidc.calculatePKCECodeChallenge(verifier),
        code_challenge_method: "S256",
      }).href;
    },
    async exchange(config, callbackUrl, state, verifier) {
      const tokens = await oidc.authorizationCodeGrant(config, callbackUrl, {
        expectedState: state,
        pkceCodeVerifier: verifier,
      });
      return tokens.claims();
    },
  };
  let discoveryPromise;
  const getProviderConfig = () => {
    if (!discoveryPromise) {
      discoveryPromise = provider.discover().catch((error) => {
        discoveryPromise = undefined;
        throw error;
      });
    }
    return discoveryPromise;
  };

  const cookieOptions = { httpOnly: true, secure, sameSite: "lax", path: "/" };
  const sessionCookieOptions = (rememberMe) => (
    rememberMe ? { ...cookieOptions, maxAge: SESSION_AGE_MS } : cookieOptions
  );
  const router = Router();
  router.use(express.json({ limit: "10kb" }));

  router.post("/register", async (request, response, next) => {
    if (request.get("origin") !== frontendUrl.origin) {
      return response.status(403).json({ error: "Invalid origin" });
    }

    const displayName = typeof request.body?.displayName === "string" ? request.body.displayName.trim() : "";
    const email = typeof request.body?.email === "string" ? request.body.email.trim().toLowerCase() : "";
    const password = typeof request.body?.password === "string" ? request.body.password : "";
    const emailOptIn = request.body?.emailOptIn !== false ? "Y" : "N";
    const marketingOptIn = request.body?.marketingOptIn === true ? "Y" : "N";
    if (displayName.length < 2 || displayName.length > 50) {
      return response.status(400).json({ error: "이름은 2자 이상 50자 이하로 입력해 주세요." });
    }
    if (email.length > 254 || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
      return response.status(400).json({ error: "올바른 이메일 주소를 입력해 주세요." });
    }
    if (password.length < 8 || password.length > 128) {
      return response.status(400).json({ error: "비밀번호는 8자 이상 128자 이하로 입력해 주세요." });
    }

    const client = await pool.connect();
    try {
      await client.query("BEGIN");
      await client.query("SELECT pg_advisory_xact_lock(hashtext($1))", [`email:${email}`]);
      const existing = await client.query("SELECT id FROM app_users WHERE lower(email) = $1", [email]);
      if (existing.rows[0]) {
        await client.query("ROLLBACK");
        return response.status(409).json({ error: "이미 가입된 이메일입니다. 로그인해 주세요." });
      }

      const userId = randomUUID();
      const passwordHash = await hashPassword(password);
      await client.query(
        `INSERT INTO app_users
           (id, email, display_name, password_hash, email_opt_in, marketing_opt_in, marketing_consent_at)
         VALUES ($1, $2, $3, $4, $5, $6, CASE WHEN $6 = 'Y' THEN now() ELSE NULL END)`,
        [userId, email, displayName, passwordHash, emailOptIn, marketingOptIn],
      );
      const sessionToken = randomBytes(32).toString("base64url");
      await client.query("DELETE FROM auth_sessions WHERE expires_at <= now()");
      await client.query(
        "INSERT INTO auth_sessions (token_hash, user_id, expires_at) VALUES ($1, $2, now() + interval '7 days')",
        [hash(sessionToken), userId],
      );
      await client.query("COMMIT");
      response.cookie(SESSION_COOKIE, sessionToken, cookieOptions);
      response.status(201).json({ user: { id: userId, email, displayName, avatarUrl: null, subscriptionStatus: "N", subscriptionPlan: null, emailOptIn, marketingOptIn } });
    } catch (error) {
      await client.query("ROLLBACK");
      next(error);
    } finally {
      client.release();
    }
  });

  router.post("/login", async (request, response, next) => {
    if (request.get("origin") !== frontendUrl.origin) {
      return response.status(403).json({ error: "Invalid origin" });
    }
    const email = typeof request.body?.email === "string" ? request.body.email.trim().toLowerCase() : "";
    const password = typeof request.body?.password === "string" ? request.body.password : "";
    const rememberMe = request.body?.rememberMe === true;
    if (!email || !password) return response.status(400).json({ error: "이메일과 비밀번호를 입력해 주세요." });

    try {
      const result = await pool.query(
        `SELECT id, email, display_name AS "displayName", avatar_url AS "avatarUrl", password_hash AS "passwordHash",
                subscription_status AS "subscriptionStatus", subscription_plan AS "subscriptionPlan",
                email_opt_in AS "emailOptIn", marketing_opt_in AS "marketingOptIn"
         FROM app_users WHERE lower(email) = $1`,
        [email],
      );
      const user = result.rows[0];
      if (!user || !(await verifyPassword(password, user.passwordHash))) {
        return response.status(401).json({ error: "이메일 또는 비밀번호가 올바르지 않습니다." });
      }
      const sessionToken = randomBytes(32).toString("base64url");
      await pool.query("DELETE FROM auth_sessions WHERE expires_at <= now()");
      await pool.query(
        "INSERT INTO auth_sessions (token_hash, user_id, expires_at) VALUES ($1, $2, now() + interval '7 days')",
        [hash(sessionToken), user.id],
      );
      await pool.query("UPDATE app_users SET last_login_at = now(), updated_at = now() WHERE id = $1", [user.id]);
      response.cookie(SESSION_COOKIE, sessionToken, sessionCookieOptions(rememberMe));
      const { passwordHash: _passwordHash, ...publicUser } = user;
      response.json({ user: publicUser });
    } catch (error) {
      next(error);
    }
  });

  async function currentUser(request) {
    const token = cookies(request)[SESSION_COOKIE];
    if (!token) return null;
    const result = await pool.query(
      `SELECT u.id, u.email, u.display_name AS "displayName", u.avatar_url AS "avatarUrl",
              u.subscription_status AS "subscriptionStatus", u.subscription_plan AS "subscriptionPlan",
              u.email_opt_in AS "emailOptIn", u.marketing_opt_in AS "marketingOptIn"
       FROM auth_sessions s JOIN app_users u ON u.id = s.user_id
       WHERE s.token_hash = $1 AND s.expires_at > now()`,
      [hash(token)],
    );
    return result.rows[0] ?? null;
  }

  async function requireUser(request, response, next) {
    try {
      const user = await currentUser(request);
      if (!user) return response.status(401).json({ error: "Authentication required" });
      request.user = user;
      next();
    } catch (error) {
      next(error);
    }
  }

  router.get("/me", async (request, response, next) => {
    try {
      const user = await currentUser(request);
      if (!user) return response.status(401).json({ error: "Authentication required" });
      response.json({ user });
    } catch (error) {
      next(error);
    }
  });

  router.post("/subscription", async (request, response, next) => {
    if (request.get("origin") !== frontendUrl.origin) {
      return response.status(403).json({ error: "Invalid origin" });
    }
    const plan = typeof request.body?.plan === "string" ? request.body.plan : "";
    if (!new Set(["explore", "professional", "enterprise"]).has(plan)) {
      return response.status(400).json({ error: "올바른 구독 플랜을 선택해 주세요." });
    }
    try {
      const user = await currentUser(request);
      if (!user) return response.status(401).json({ error: "Authentication required" });
      const result = await pool.query(
        `UPDATE app_users
         SET subscription_status = 'Y', subscription_plan = $2,
             subscription_started_at = COALESCE(subscription_started_at, now()), updated_at = now()
         WHERE id = $1
         RETURNING id, email, display_name AS "displayName", avatar_url AS "avatarUrl",
                   subscription_status AS "subscriptionStatus", subscription_plan AS "subscriptionPlan",
                   email_opt_in AS "emailOptIn", marketing_opt_in AS "marketingOptIn"`,
        [user.id, plan],
      );
      response.json({ user: result.rows[0] });
    } catch (error) {
      next(error);
    }
  });

  router.patch("/profile/preferences", async (request, response, next) => {
    if (request.get("origin") !== frontendUrl.origin) {
      return response.status(403).json({ error: "Invalid origin" });
    }
    if (typeof request.body?.emailOptIn !== "boolean" || typeof request.body?.marketingOptIn !== "boolean") {
      return response.status(400).json({ error: "수신 설정 값이 올바르지 않습니다." });
    }
    try {
      const user = await currentUser(request);
      if (!user) return response.status(401).json({ error: "Authentication required" });
      const emailOptIn = request.body.emailOptIn ? "Y" : "N";
      const marketingOptIn = request.body.marketingOptIn ? "Y" : "N";
      const result = await pool.query(
        `UPDATE app_users
         SET email_opt_in = $2::char(1), marketing_opt_in = $3::char(1),
             marketing_consent_at = CASE
               WHEN $3::char(1) = 'Y'::char(1) THEN COALESCE(marketing_consent_at, now())
               ELSE NULL
             END,
             updated_at = now()
         WHERE id = $1
         RETURNING id, email, display_name AS "displayName", avatar_url AS "avatarUrl",
                   subscription_status AS "subscriptionStatus", subscription_plan AS "subscriptionPlan",
                   email_opt_in AS "emailOptIn", marketing_opt_in AS "marketingOptIn"`,
        [user.id, emailOptIn, marketingOptIn],
      );
      response.json({ user: result.rows[0] });
    } catch (error) {
      next(error);
    }
  });

  router.get("/google", async (request, response, next) => {
    if (!configured && !options.provider) {
      const target = new URL(frontendUrl);
      target.searchParams.set("auth_error", "not_configured");
      return response.redirect(303, target.href);
    }
    try {
      const config = await getProviderConfig();
      const rememberMe = request.query.remember === "1";
      const state = randomBytes(32).toString("base64url");
      const verifier = oidc.randomPKCECodeVerifier();
      const authorizationUrl = await provider.authorizationUrl(config, state, verifier);
      await pool.query("DELETE FROM oauth_login_attempts WHERE expires_at <= now()");
      await pool.query(
        "INSERT INTO oauth_login_attempts (state_hash, code_verifier, remember_me, expires_at) VALUES ($1, $2, $3, now() + interval '10 minutes')",
        [hash(state), verifier, rememberMe],
      );
      response.cookie(STATE_COOKIE, state, { ...cookieOptions, maxAge: STATE_AGE_MS });
      response.redirect(authorizationUrl);
    } catch (error) {
      next(error);
    }
  });

  router.get("/google/callback", async (request, response, next) => {
    const failure = (reason) => {
      response.clearCookie(STATE_COOKIE, cookieOptions);
      const target = new URL(frontendUrl);
      target.searchParams.set("auth_error", reason);
      response.redirect(303, target.href);
    };
    const callbackUrl = new URL(redirectUri);
    callbackUrl.search = new URL(request.originalUrl, callbackUrl).search;
    const states = callbackUrl.searchParams.getAll("state");
    const state = states.length === 1 ? states[0] : null;
    if (!sameValue(state, cookies(request)[STATE_COOKIE])) return failure("invalid_state");
    if (callbackUrl.searchParams.has("error")) return failure("access_denied");
    if (callbackUrl.searchParams.getAll("code").length !== 1) return failure("invalid_response");

    try {
      const attempt = await pool.query(
        "DELETE FROM oauth_login_attempts WHERE state_hash = $1 AND expires_at > now() RETURNING code_verifier, remember_me",
        [hash(state)],
      );
      if (!attempt.rows[0]) return failure("expired_state");
      const config = await getProviderConfig();
      let claims;
      try {
        claims = await provider.exchange(config, callbackUrl, state, attempt.rows[0].code_verifier);
      } catch (error) {
        console.error("Google OAuth token exchange failed", error);
        return failure(error?.error === "invalid_client" ? "oauth_configuration" : "oauth_exchange");
      }
      if (typeof claims?.sub !== "string" || !claims.sub) return failure("invalid_identity");

      const client = await pool.connect();
      let sessionToken;
      try {
        await client.query("BEGIN");
        await client.query("SELECT pg_advisory_xact_lock(hashtext($1))", [`google:${claims.sub}`]);
        const account = await client.query(
          "SELECT user_id FROM oauth_accounts WHERE provider = 'google' AND provider_subject = $1",
          [claims.sub],
        );
        const email = claims.email_verified === true && typeof claims.email === "string" ? claims.email : null;
        const displayName = typeof claims.name === "string" && claims.name.trim() ? claims.name : email ?? "Google 사용자";
        const avatarUrl = typeof claims.picture === "string" ? claims.picture : null;
        let userId = account.rows[0]?.user_id;
        if (userId) {
          await client.query(
            "UPDATE app_users SET email = $2, display_name = $3, avatar_url = $4, updated_at = now(), last_login_at = now() WHERE id = $1",
            [userId, email, displayName, avatarUrl],
          );
        } else {
          userId = randomUUID();
          await client.query(
            "INSERT INTO app_users (id, email, display_name, avatar_url) VALUES ($1, $2, $3, $4)",
            [userId, email, displayName, avatarUrl],
          );
          await client.query(
            "INSERT INTO oauth_accounts (provider, provider_subject, user_id) VALUES ('google', $1, $2)",
            [claims.sub, userId],
          );
        }
        sessionToken = randomBytes(32).toString("base64url");
        await client.query("DELETE FROM auth_sessions WHERE expires_at <= now()");
        await client.query(
          "INSERT INTO auth_sessions (token_hash, user_id, expires_at) VALUES ($1, $2, now() + interval '7 days')",
          [hash(sessionToken), userId],
        );
        await client.query("COMMIT");
      } catch (error) {
        await client.query("ROLLBACK");
        throw error;
      } finally {
        client.release();
      }
      response.clearCookie(STATE_COOKIE, cookieOptions);
      response.cookie(SESSION_COOKIE, sessionToken, sessionCookieOptions(attempt.rows[0].remember_me === true));
      response.redirect(303, frontendUrl.href);
    } catch (error) {
      next(error);
    }
  });

  router.post("/logout", async (request, response, next) => {
    if (request.get("origin") !== frontendUrl.origin) {
      return response.status(403).json({ error: "Invalid origin" });
    }
    try {
      const token = cookies(request)[SESSION_COOKIE];
      if (token) await pool.query("DELETE FROM auth_sessions WHERE token_hash = $1", [hash(token)]);
      response.clearCookie(SESSION_COOKIE, cookieOptions);
      response.status(204).end();
    } catch (error) {
      next(error);
    }
  });

  return { router, requireUser };
}
