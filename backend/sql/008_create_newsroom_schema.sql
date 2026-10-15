CREATE SCHEMA IF NOT EXISTS newsroom;

CREATE TABLE IF NOT EXISTS newsroom.articles (
  id bigserial PRIMARY KEY,
  source_name text NOT NULL,
  category text NOT NULL CHECK (category IN ('조선', '해운', '물류')),
  title text NOT NULL,
  article_url text NOT NULL UNIQUE,
  published_at timestamptz NOT NULL,
  image_url text,
  image_alt text,
  feed_url text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS newsroom_articles_published_idx
  ON newsroom.articles (published_at DESC);

CREATE INDEX IF NOT EXISTS newsroom_articles_category_published_idx
  ON newsroom.articles (category, published_at DESC);
