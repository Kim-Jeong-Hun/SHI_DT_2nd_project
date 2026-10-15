CREATE TABLE IF NOT EXISTS cluster_models (
    vessel_type_id text NOT NULL REFERENCES vessel_types(id),
    model_key text NOT NULL,
    method text NOT NULL,
    cluster_count integer NOT NULL CHECK (cluster_count > 0),
    configuration jsonb NOT NULL,
    source_filename text NOT NULL,
    imported_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (vessel_type_id, model_key)
);

CREATE TABLE IF NOT EXISTS cluster_monthly_assignments (
    vessel_type_id text NOT NULL,
    model_key text NOT NULL,
    period date NOT NULL CHECK (period = date_trunc('month', period)::date),
    cluster_number integer NOT NULL CHECK (cluster_number > 0),
    PRIMARY KEY (vessel_type_id, model_key, period),
    FOREIGN KEY (vessel_type_id, model_key)
        REFERENCES cluster_models(vessel_type_id, model_key) ON DELETE CASCADE,
    FOREIGN KEY (vessel_type_id, period)
        REFERENCES vessel_monthly_master(vessel_type_id, period)
);

CREATE TABLE IF NOT EXISTS cluster_monthly_metrics (
    vessel_type_id text NOT NULL,
    model_key text NOT NULL,
    period date NOT NULL,
    metric_name text NOT NULL,
    value numeric NOT NULL,
    PRIMARY KEY (vessel_type_id, model_key, period, metric_name),
    FOREIGN KEY (vessel_type_id, model_key, period)
        REFERENCES cluster_monthly_assignments(vessel_type_id, model_key, period) ON DELETE CASCADE
);
