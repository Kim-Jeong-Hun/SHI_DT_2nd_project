CREATE TABLE IF NOT EXISTS vessel_types (
    id text PRIMARY KEY,
    name text NOT NULL
);

CREATE TABLE IF NOT EXISTS monthly_orders (
    vessel_type_id text NOT NULL REFERENCES vessel_types(id),
    year integer NOT NULL CHECK (year BETWEEN 2000 AND 2100),
    month integer NOT NULL CHECK (month BETWEEN 1 AND 12),
    cgt numeric(14, 2) NOT NULL CHECK (cgt >= 0),
    PRIMARY KEY (vessel_type_id, year, month)
);
