CREATE TABLE IF NOT EXISTS vessel_monthly_source_rows (
    vessel_type_id text NOT NULL,
    period date NOT NULL,
    source_filename text NOT NULL,
    row_data jsonb NOT NULL,
    imported_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (vessel_type_id, period),
    FOREIGN KEY (vessel_type_id, period)
        REFERENCES vessel_monthly_master(vessel_type_id, period) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS vessel_monthly_source_rows_period_idx
    ON vessel_monthly_source_rows (period, vessel_type_id);
