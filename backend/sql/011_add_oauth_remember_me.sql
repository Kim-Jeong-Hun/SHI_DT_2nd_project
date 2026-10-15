ALTER TABLE oauth_login_attempts
  ADD COLUMN IF NOT EXISTS remember_me boolean NOT NULL DEFAULT false;
