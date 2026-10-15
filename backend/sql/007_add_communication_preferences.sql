ALTER TABLE app_users
  ADD COLUMN IF NOT EXISTS email_opt_in char(1) NOT NULL DEFAULT 'N',
  ADD COLUMN IF NOT EXISTS marketing_opt_in char(1) NOT NULL DEFAULT 'N',
  ADD COLUMN IF NOT EXISTS marketing_consent_at timestamptz;

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'app_users_email_opt_in_check') THEN
    ALTER TABLE app_users ADD CONSTRAINT app_users_email_opt_in_check CHECK (email_opt_in IN ('Y', 'N'));
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'app_users_marketing_opt_in_check') THEN
    ALTER TABLE app_users ADD CONSTRAINT app_users_marketing_opt_in_check CHECK (marketing_opt_in IN ('Y', 'N'));
  END IF;
END $$;
