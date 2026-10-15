import express from "express";
import { createAuth } from "./auth.js";
import { getCustomForecastConfig, NOTEBOOK_FORECAST_VESSELS, runCustomForecast } from "./forecastRunner.js";

const PLAN_LEVEL = { explore: 1, professional: 2, enterprise: 3 };

export function createApp(pool, authOptions = {}) {
  const app = express();
  app.use(express.json({ limit: "64kb" }));
  const auth = createAuth(pool, authOptions);
  app.use("/api/auth", auth.router);

  app.get("/api/health", (_request, response) => {
    response.json({ status: "ok" });
  });

  app.get("/api/ready", async (_request, response) => {
    try {
      await pool.query("SELECT 1");
      response.json({ status: "ok" });
    } catch (error) {
      console.error("Database readiness check failed", error);
      response.status(503).json({ error: "Database unavailable" });
    }
  });

  app.use("/api/v1", auth.requireUser);
  const requirePlan = (minimumPlan) => (request, response, next) => {
    if ((PLAN_LEVEL[request.user?.subscriptionPlan] ?? 0) < PLAN_LEVEL[minimumPlan]) {
      response.status(403).json({ error: `${minimumPlan} 이상 플랜에서 사용할 수 있는 기능입니다.` });
      return;
    }
    next();
  };

  app.get("/api/v1/vessels", async (_request, response) => {
    try {
      const result = await pool.query("SELECT id, name FROM vessel_types ORDER BY id");
      response.json(result.rows);
    } catch (error) {
      console.error("Failed to load vessels", error);
      response.status(500).json({ error: "Failed to load vessels" });
    }
  });

  app.get("/api/v1/master-data", requirePlan("professional"), async (request, response) => {
    const { vesselId, from, to } = request.query;
    const validMonth = (value) => typeof value === "string" && /^20\d{2}-(0[1-9]|1[0-2])$/.test(value);
    if (typeof vesselId !== "string" || !["chemical", "gas", "bulk", "tanker", "container"].includes(vesselId) ||
        (from !== undefined && !validMonth(from)) || (to !== undefined && !validMonth(to)) ||
        (from && to && from > to)) {
      response.status(400).json({ error: "Provide a valid vesselId and optional YYYY-MM from/to range." });
      return;
    }

    try {
      const result = await pool.query(
        `SELECT to_char(master.period, 'YYYY-MM') AS period,
                master.order_capacity::text AS "orderCapacity",
                master.order_capacity_unit AS unit,
                master.order_info_lag_months AS "orderInfoLagMonths",
                master.order_info_basis AS "orderInfoBasis",
                master.source_filename AS "sourceFilename",
                source.row_data AS "sourceRow",
                COALESCE(jsonb_object_agg(feature.feature_name, feature.value::text)
                  FILTER (WHERE feature.feature_name IS NOT NULL), '{}'::jsonb) AS features
         FROM vessel_monthly_master AS master
         LEFT JOIN vessel_monthly_source_rows AS source
           ON source.vessel_type_id = master.vessel_type_id AND source.period = master.period
         LEFT JOIN vessel_monthly_features AS feature
           ON feature.vessel_type_id = master.vessel_type_id AND feature.period = master.period
         WHERE master.vessel_type_id = $1
           AND master.period >= COALESCE($2::date, DATE '2000-01-01')
           AND master.period < COALESCE(($3::date + INTERVAL '1 month'), DATE '2101-01-01')
         GROUP BY master.vessel_type_id, master.period, source.row_data
         ORDER BY master.period`,
        [vesselId, from ? `${from}-01` : null, to ? `${to}-01` : null],
      );
      response.json({ vesselId, rows: result.rows });
    } catch (error) {
      console.error("Failed to load vessel master data", error);
      response.status(500).json({ error: "Failed to load vessel master data" });
    }
  });

  app.get("/api/v1/custom-forecast/config", requirePlan("enterprise"), async (request, response) => {
    const vesselId = request.query.vesselId;
    if (typeof vesselId !== "string" || !NOTEBOOK_FORECAST_VESSELS.has(vesselId)) {
      response.status(400).json({ error: "container, tanker, gas, chemical 중 하나를 선택해 주세요." });
      return;
    }
    try {
      response.json(await getCustomForecastConfig(vesselId));
    } catch (error) {
      console.error("Failed to load custom forecast config", error);
      response.status(500).json({ error: error.message || "시나리오 예측 설정을 불러오지 못했습니다." });
    }
  });

  app.post("/api/v1/custom-forecast/run", requirePlan("enterprise"), async (request, response) => {
    const vesselId = request.body?.vesselId;
    if (typeof vesselId !== "string" || !NOTEBOOK_FORECAST_VESSELS.has(vesselId)) {
      response.status(400).json({ error: "container, tanker, gas, chemical 중 하나를 선택해 주세요." });
      return;
    }

    try {
      const result = await runCustomForecast(request.body);
      response.json(result);
    } catch (error) {
      console.error("Notebook forecast failed", error);
      response.status(500).json({ error: error.message || "시나리오 예측 실행에 실패했습니다." });
    }
  });

  app.get("/api/v1/market/orders", async (request, response) => {
    const year = Number(request.query.year);
    if (typeof request.query.year !== "string" || !/^\d{4}$/.test(request.query.year) ||
        !Number.isInteger(year) || year < 2000 || year > 2100) {
      response.status(400).json({ error: "year must be a four-digit integer between 2000 and 2100" });
      return;
    }

    try {
      const result = await pool.query(
        `SELECT vessel_type_id AS "vesselId", year, month, cgt::float8 AS cgt
         FROM monthly_orders
         WHERE year = $1
         ORDER BY vessel_type_id, month`,
        [year],
      );
      response.json(result.rows);
    } catch (error) {
      console.error("Failed to load market orders", error);
      response.status(500).json({ error: "Failed to load market orders" });
    }
  });

  app.get("/api/v1/newsroom", async (_request, response) => {
    try {
      const result = await pool.query(
        `SELECT id, source_name AS "sourceName", category, title,
                article_url AS "articleUrl", published_at AS "publishedAt",
                image_url AS "imageUrl", image_alt AS "imageAlt"
         FROM newsroom.articles
         WHERE published_at >= now() - interval '180 days'
         ORDER BY published_at DESC
         LIMIT 80`,
      );

      const featured = [];
      const featuredIds = new Set();
      for (const article of result.rows) {
        if (!featured.some((item) => item.category === article.category)) {
          featured.push(article);
          featuredIds.add(article.id);
          if (featured.length === 3) break;
        }
      }
      if (featured.length < 3) {
        for (const article of result.rows) {
          if (featuredIds.has(article.id)) continue;
          featured.push(article);
          featuredIds.add(article.id);
          if (featured.length === 3) break;
        }
      }

      response.json({
        featured,
        articles: result.rows.filter((article) => !featuredIds.has(article.id)),
      });
    } catch (error) {
      console.error("Failed to load newsroom articles", error);
      response.status(500).json({ error: "Failed to load newsroom articles" });
    }
  });

  app.use((error, _request, response, _next) => {
    console.error("API request failed", error);
    response.status(500).json({ error: "Internal server error" });
  });

  return app;
}
