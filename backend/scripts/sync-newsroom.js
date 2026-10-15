import pg from "pg";

if (!process.env.DATABASE_URL) {
  throw new Error("DATABASE_URL is required. See backend/.env.example.");
}

const feeds = [
  { url: "https://www.klnews.co.kr/rss/S1N9.xml", sourceName: "물류신문", category: "해운", domains: ["klnews.co.kr"] },
  { url: "https://www.klnews.co.kr/rss/S1N8.xml", sourceName: "물류신문", category: "물류", domains: ["klnews.co.kr"] },
  { url: "https://www.klnews.co.kr/rss/S1N13.xml", sourceName: "물류신문", category: "물류", domains: ["klnews.co.kr"] },
  { url: "https://www.klnews.co.kr/rss/allArticle.xml", sourceName: "물류신문", category: null, domains: ["klnews.co.kr"] },
  { url: "https://news.samsung.com/kr/feed/rss", sourceName: "삼성전자 뉴스룸", category: null, domains: ["samsung.com"] },
  { url: "https://www.mk.co.kr/rss/30100041/", sourceName: "매일경제", category: null, domains: ["mk.co.kr"] },
  { url: "https://www.mk.co.kr/rss/50100032/", sourceName: "매일경제", category: null, domains: ["mk.co.kr"] },
  { url: "https://www.hankyung.com/feed/economy", sourceName: "한국경제", category: null, domains: ["hankyung.com"] },
  { url: "https://www.yna.co.kr/rss/news.xml", sourceName: "연합뉴스", category: null, domains: ["yna.co.kr"] },
];

const publisherHostAllowed = (hostname, domains) => domains.some((domain) => hostname === domain || hostname.endsWith(`.${domain}`));

const decodeXml = (value) => value
  .replace(/<!\[CDATA\[([\s\S]*?)\]\]>/g, "$1")
  .replace(/&#(x[\da-f]+|\d+);/gi, (_match, code) => String.fromCodePoint(code[0].toLowerCase() === "x" ? Number.parseInt(code.slice(1), 16) : Number(code)))
  .replace(/&nbsp;/gi, " ")
  .replace(/&amp;/gi, "&")
  .replace(/&quot;/gi, '"')
  .replace(/&apos;/gi, "'")
  .replace(/&lt;/gi, "<")
  .replace(/&gt;/gi, ">");

function tagValue(xml, tagNames) {
  for (const name of tagNames) {
    const escaped = name.replace(":", "\\s*:\\s*");
    const match = xml.match(new RegExp(`<${escaped}(?:\\s[^>]*)?>([\\s\\S]*?)<\\/${escaped}>`, "i"));
    if (match) return decodeXml(match[1]).trim();
  }
  return "";
}

function imageUrl(item, articleUrl, domains) {
  const candidates = [];
  for (const match of item.matchAll(/<(?:media:thumbnail|media:content|enclosure)\b([^>]*)>/gi)) {
    const attributes = match[1];
    const url = attributes.match(/\burl=["']([^"']+)["']/i)?.[1];
    const type = attributes.match(/\btype=["']([^"']+)["']/i)?.[1] ?? "";
    if (url && (!type || type.startsWith("image/"))) candidates.push(url);
  }
  for (const match of item.matchAll(/<img\b[^>]*\bsrc=["']([^"']+)["'][^>]*>/gi)) candidates.push(decodeXml(match[1]));

  for (const candidate of candidates) {
    try {
      const parsed = new URL(candidate, articleUrl);
      if (!/^https?:$/.test(parsed.protocol) || parsed.username || parsed.password) continue;
      if (!publisherHostAllowed(parsed.hostname, domains)) continue;
      return parsed.href;
    } catch {
      // Ignore malformed image references and try the next feed candidate.
    }
  }
  return null;
}

function categoryFor(title, fallback) {
  // A source's RSS section is only a fallback: shipping feeds also carry
  // shipyard delivery and construction stories (e.g. a container ship handover).
  if (/(조선(?:업|소|산업|업계|산업계|사|기술)|조선\s*[·ㆍ]\s*(?:원자력|방산|해운)|선박\s*(수주|건조)|LNG선|암모니아선|친환경선박|해양플랜트|이지스함|해양\s*SMR)/i.test(title) ||
      (/(선박|컨테이너선|LNG선|암모니아선|친환경선박|특수선|함정|잠수함)/i.test(title) && /(수주|건조|인도|진수|명명식|착공|신조|발주)/i.test(title)) ||
      (/(한화오션|삼성중공업|HD현대중공업|HD현대重|HJ중공업)/i.test(title) && /(선박|잠수함|함정|수주|건조|진수|핵잠|LNG선)/i.test(title))) return "조선";
  if (/(물류|공급망|택배|창고|스마트물류|물류센터|운송|SCM|3PL|화물물류|항공화물)/i.test(title)) return "물류";
  if (/(해운|선사|운임|선복|항로|해상|컨테이너선|벌크선|유조선|항만)/i.test(title)) return "해운";
  return fallback;
}

function cleanHtml(value) {
  return decodeXml(value.replace(/<[^>]*>/g, " ")).replace(/\s+/g, " ").trim();
}

function classContent(html, className) {
  const escaped = className.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  return html.match(new RegExp(`<[^>]+class=["'][^"']*\\b${escaped}\\b[^"']*["'][^>]*>([\\s\\S]*?)<\\/[^>]+>`, "i"))?.[1] ?? "";
}

function parseHdHyundaiNews(html) {
  const listingUrl = "https://hd-hhi.com/kr/media-hub/press-release";
  const articles = [];
  for (const [, attributes, content] of html.matchAll(/<li\b[^>]*class=["'][^"']*\btiles-item\b[^"']*["'][^>]*>\s*<a\b([^>]*)>([\s\S]*?)<\/a>\s*<\/li>/gi)) {
    const rawUrl = attributes.match(/\bhref=["']([^"']+)["']/i)?.[1];
    const title = cleanHtml(classContent(content, "tile-subject"));
    const rawDate = cleanHtml(classContent(content, "tile-date"));
    const rawImage = content.match(/<img\b[^>]*\bsrc=["']([^"']+)["']/i)?.[1];
    if (!rawUrl || !title || categoryFor(title, null) !== "조선") continue;
    const dateParts = rawDate.match(/^(\d{4})\.(\d{2})\.(\d{2})$/);
    if (!dateParts) continue;
    const publishedAt = new Date(`${dateParts[1]}-${dateParts[2]}-${dateParts[3]}T12:00:00+09:00`);
    const cutoff = Date.now() - 180 * 24 * 60 * 60 * 1000;
    if (publishedAt.getTime() < cutoff || publishedAt.getTime() > Date.now() + 24 * 60 * 60 * 1000) continue;
    const articleUrl = new URL(rawUrl, listingUrl).href;
    const imageUrl = rawImage ? new URL(rawImage, listingUrl).href : null;
    articles.push({
      sourceName: "HD현대중공업",
      category: "조선",
      title,
      articleUrl,
      publishedAt: publishedAt.toISOString(),
      imageUrl,
      imageAlt: title,
      feedUrl: listingUrl,
    });
  }
  return articles;
}

function parseFeed(xml, feed) {
  const blocks = [...xml.matchAll(/<item\b[^>]*>([\s\S]*?)<\/item>/gi)].map((match) => match[1]);
  const cutoff = Date.now() - 180 * 24 * 60 * 60 * 1000;
  const articles = [];

  for (const item of blocks) {
    const title = tagValue(item, ["title"]).replace(/\s+/g, " ").trim();
    const rawUrl = tagValue(item, ["link", "guid"]);
    const publishedAt = new Date(tagValue(item, ["pubDate", "dc:date"]));
    if (!title || !rawUrl || Number.isNaN(publishedAt.getTime()) || publishedAt.getTime() < cutoff || publishedAt.getTime() > Date.now() + 24 * 60 * 60 * 1000) continue;

    let articleUrl;
    try {
      articleUrl = new URL(rawUrl).href;
      const hostname = new URL(articleUrl).hostname;
      if (!publisherHostAllowed(hostname, feed.domains)) continue;
    } catch {
      continue;
    }

    const category = categoryFor(title, feed.category);
    if (!category) continue;
    articles.push({
      sourceName: tagValue(item, ["source"]) || feed.sourceName,
      category,
      title,
      articleUrl,
      publishedAt: publishedAt.toISOString(),
      imageUrl: imageUrl(item, articleUrl, feed.domains),
      imageAlt: title,
      feedUrl: feed.url,
      publisherDomains: feed.domains,
    });
  }
  return articles;
}

const feedResults = await Promise.all(feeds.map(async (feed) => {
  const response = await fetch(feed.url, {
    headers: { "user-agent": "SHIP-SIGNAL-Newsroom/1.0 (+RSS reader; source attribution preserved)" },
    signal: AbortSignal.timeout(15000),
  });
  if (!response.ok) throw new Error(`RSS request failed (${response.status}): ${feed.url}`);
  return parseFeed(await response.text(), feed);
}));

const hdNewsResponse = await fetch("https://hd-hhi.com/kr/media-hub/press-release", {
  headers: { "user-agent": "SHIP-SIGNAL-Newsroom/1.0 (+publisher newsroom metadata reader)" },
  signal: AbortSignal.timeout(15000),
});
if (!hdNewsResponse.ok) throw new Error(`HD Hyundai newsroom request failed (${hdNewsResponse.status})`);

const allArticles = [...feedResults.flat(), ...parseHdHyundaiNews(await hdNewsResponse.text())];
const byUrl = new Map(allArticles.map((article) => [article.articleUrl, article]));
// Prefer the publisher's own press release over a syndicating outlet when the
// titles are identical, while retaining related but independently titled news.
const articlesByTitle = new Map();
for (const article of byUrl.values()) {
  const normalizedTitle = article.title.toLowerCase().replace(/[\s\p{P}\p{S}]/gu, "");
  const existing = articlesByTitle.get(normalizedTitle);
  if (!existing || article.sourceName === "HD현대중공업") articlesByTitle.set(normalizedTitle, article);
}
const articles = [...articlesByTitle.values()];

async function fetchPublisherImage(article) {
  if (article.imageUrl) return article;
  try {
    const page = await fetch(article.articleUrl, {
      headers: { "user-agent": "SHIP-SIGNAL-Newsroom/1.0 (+original story thumbnails; attribution preserved)" },
      signal: AbortSignal.timeout(10000),
    });
    if (!page.ok) return article;
    const html = await page.text();
    for (const tag of html.match(/<meta\b[^>]*>/gi) ?? []) {
      const property = tag.match(/\b(?:property|name)=["']([^"']+)["']/i)?.[1]?.toLowerCase();
      if (property !== "og:image" && property !== "twitter:image") continue;
      const content = tag.match(/\bcontent=["']([^"']+)["']/i)?.[1];
      if (!content) continue;
      const parsed = new URL(decodeXml(content), article.articleUrl);
      const host = parsed.hostname.toLowerCase();
      if (!/^https?:$/.test(parsed.protocol) || parsed.username || parsed.password) continue;
      if (!publisherHostAllowed(host, article.publisherDomains ?? []) && !(host === "hd-hhi.com" || host.endsWith(".hd-hhi.com"))) continue;
      return { ...article, imageUrl: parsed.href };
    }
  } catch {
    // Image previews are optional; preserve the article when its source blocks preview lookup.
  }
  return article;
}

let nextImageIndex = 0;
const imageWorkers = Array.from({ length: Math.min(6, articles.length) }, async () => {
  while (nextImageIndex < articles.length) {
    const index = nextImageIndex++;
    articles[index] = await fetchPublisherImage(articles[index]);
  }
});
await Promise.all(imageWorkers);

const pool = new pg.Pool({ connectionString: process.env.DATABASE_URL });
try {
  const client = await pool.connect();
  let duplicateHeadlineCount = 0;
  try {
    await client.query("BEGIN");
    for (const article of articles) {
      await client.query(
        `INSERT INTO newsroom.articles
           (source_name, category, title, article_url, published_at, image_url, image_alt, feed_url, updated_at)
         VALUES ($1, $2, $3, $4, $5, $6, $7, $8, now())
         ON CONFLICT (article_url) DO UPDATE SET
           source_name = EXCLUDED.source_name,
           category = EXCLUDED.category,
           title = EXCLUDED.title,
           published_at = EXCLUDED.published_at,
           image_url = EXCLUDED.image_url,
           image_alt = EXCLUDED.image_alt,
           feed_url = EXCLUDED.feed_url,
           updated_at = now()`,
        [article.sourceName, article.category, article.title, article.articleUrl, article.publishedAt, article.imageUrl, article.imageAlt, article.feedUrl],
      );
    }
    const duplicateResult = await client.query(
      `DELETE FROM newsroom.articles duplicate
       USING newsroom.articles preferred
       WHERE regexp_replace(lower(duplicate.title), '[[:space:][:punct:]]', '', 'g') =
             regexp_replace(lower(preferred.title), '[[:space:][:punct:]]', '', 'g')
         AND duplicate.article_url <> preferred.article_url
         AND ((preferred.source_name = 'HD현대중공업' AND duplicate.source_name <> 'HD현대중공업')
           OR ((preferred.source_name = 'HD현대중공업') = (duplicate.source_name = 'HD현대중공업')
               AND duplicate.id > preferred.id))`,
    );
    duplicateHeadlineCount = duplicateResult.rowCount;
    await client.query("COMMIT");
  } catch (error) {
    await client.query("ROLLBACK");
    throw error;
  } finally {
    client.release();
  }
  const imageCount = articles.filter((article) => article.imageUrl).length;
  console.log(`Synced ${articles.length} article records from ${feeds.length} RSS feeds and the HD Hyundai newsroom (${duplicateHeadlineCount} duplicate headlines removed; ${imageCount} publisher images).`);
} finally {
  await pool.end();
}
