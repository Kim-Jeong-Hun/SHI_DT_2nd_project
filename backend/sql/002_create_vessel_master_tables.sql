CREATE TABLE IF NOT EXISTS vessel_monthly_master (
    vessel_type_id text NOT NULL REFERENCES vessel_types(id),
    period date NOT NULL CHECK (period = date_trunc('month', period)::date),
    order_capacity numeric CHECK (order_capacity >= 0),
    order_capacity_unit text NOT NULL CHECK (order_capacity_unit IN ('CBM', 'DWT', 'TEU')),
    order_info_lag_months integer CHECK (order_info_lag_months >= 0),
    order_info_basis text,
    source_filename text NOT NULL,
    imported_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (vessel_type_id, period)
);

CREATE TABLE IF NOT EXISTS vessel_monthly_features (
    vessel_type_id text NOT NULL,
    period date NOT NULL,
    feature_name text NOT NULL,
    value numeric NOT NULL,
    PRIMARY KEY (vessel_type_id, period, feature_name),
    FOREIGN KEY (vessel_type_id, period)
        REFERENCES vessel_monthly_master(vessel_type_id, period) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS vessel_monthly_features_name_period_idx
    ON vessel_monthly_features (feature_name, period);
