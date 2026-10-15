ALTER TABLE app_users
  ADD COLUMN IF NOT EXISTS subscription_status char(1) NOT NULL DEFAULT 'N',
  ADD COLUMN IF NOT EXISTS subscription_plan text,
  ADD COLUMN IF NOT EXISTS subscription_started_at timestamptz;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'app_users_subscription_status_check'
  ) THEN
    ALTER TABLE app_users
      ADD CONSTRAINT app_users_subscription_status_check
      CHECK (subscription_status IN ('Y', 'N'));
  END IF;
END $$;
