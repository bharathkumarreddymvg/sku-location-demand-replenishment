-- ============================================================================
-- Standard ANSI SQL Relational Schema DDL:
-- SKU-Location Demand Forecasting & Replenishment Engine
-- Pure standard SQL-99 DDL compatible with both PostgreSQL 14+ and SQLite 3.x
-- (Note: In SQLite CLI/Python, enable foreign key enforcement via connection
-- configuration rather than non-standard SQLite PRAGMA statements here.)
-- ============================================================================

CREATE TABLE IF NOT EXISTS sku (
    sku_id VARCHAR(16) PRIMARY KEY,
    sku_name VARCHAR(120) NOT NULL,
    category VARCHAR(32) NOT NULL CHECK (category IN ('Beverages', 'Dairy', 'Dry_Grocery', 'Household', 'Personal_Care', 'Produce')),
    demand_profile VARCHAR(24) NOT NULL CHECK (demand_profile IN ('SMOOTH', 'SEASONAL', 'INTERMITTENT')),
    unit_cost DECIMAL(10, 2) NOT NULL CHECK (unit_cost > 0),
    unit_price DECIMAL(10, 2) NOT NULL CHECK (unit_price >= unit_cost),
    lifecycle_state VARCHAR(24) NOT NULL CHECK (lifecycle_state IN ('LAUNCH', 'ACTIVE', 'PHASE_OUT', 'DISCONTINUED')),
    effective_start_date DATE NOT NULL,
    effective_end_date DATE NULL
);

CREATE TABLE IF NOT EXISTS store (
    store_id VARCHAR(16) PRIMARY KEY,
    store_name VARCHAR(80) NOT NULL UNIQUE,
    region VARCHAR(16) NOT NULL CHECK (region IN ('NORTH', 'SOUTH', 'EAST', 'WEST', 'CENTRAL')),
    store_format VARCHAR(24) NOT NULL CHECK (store_format IN ('HYPERMARKET', 'SUPERMARKET', 'EXPRESS')),
    max_storage_capacity INTEGER NOT NULL CHECK (max_storage_capacity > 0),
    lifecycle_state VARCHAR(24) NOT NULL CHECK (lifecycle_state IN ('OPEN', 'RENOVATION', 'CLOSED')),
    opened_date DATE NOT NULL
);

CREATE TABLE IF NOT EXISTS supplier (
    supplier_id VARCHAR(16) PRIMARY KEY,
    supplier_name VARCHAR(100) NOT NULL UNIQUE,
    country_code CHAR(2) NOT NULL,
    reliability_score DECIMAL(4, 3) NOT NULL CHECK (reliability_score >= 0.0 AND reliability_score <= 1.0),
    lifecycle_state VARCHAR(24) NOT NULL CHECK (lifecycle_state IN ('ACTIVE', 'ON_HOLD', 'INACTIVE')),
    effective_date DATE NOT NULL
);

CREATE TABLE IF NOT EXISTS supplier_sku (
    supplier_sku_id VARCHAR(16) PRIMARY KEY,
    supplier_id VARCHAR(16) NOT NULL REFERENCES supplier(supplier_id),
    sku_id VARCHAR(16) NOT NULL REFERENCES sku(sku_id),
    is_primary_supplier BOOLEAN NOT NULL,
    pack_size INTEGER NOT NULL CHECK (pack_size >= 1),
    moq_units INTEGER NOT NULL CHECK (moq_units >= pack_size AND moq_units % pack_size = 0),
    expected_lead_time_days DECIMAL(6, 2) NOT NULL CHECK (expected_lead_time_days > 0),
    lead_time_std_days DECIMAL(6, 2) NOT NULL CHECK (lead_time_std_days >= 0),
    effective_start_date DATE NOT NULL,
    UNIQUE (supplier_id, sku_id)
);

CREATE TABLE IF NOT EXISTS lead_time_observation (
    observation_id VARCHAR(16) PRIMARY KEY,
    supplier_sku_id VARCHAR(16) NOT NULL REFERENCES supplier_sku(supplier_sku_id),
    supplier_id VARCHAR(16) NOT NULL REFERENCES supplier(supplier_id),
    sku_id VARCHAR(16) NOT NULL REFERENCES sku(sku_id),
    store_id VARCHAR(16) NOT NULL REFERENCES store(store_id),
    order_date DATE NOT NULL,
    received_date DATE NOT NULL,
    actual_lead_time_days INTEGER NOT NULL,
    delay_days INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS reorder_policy (
    policy_id VARCHAR(32) PRIMARY KEY,
    store_id VARCHAR(16) NOT NULL REFERENCES store(store_id),
    sku_id VARCHAR(16) NOT NULL REFERENCES sku(sku_id),
    primary_supplier_id VARCHAR(16) NOT NULL REFERENCES supplier(supplier_id),
    service_level_target DECIMAL(5, 3) NOT NULL,
    z_score DECIMAL(6, 4) NOT NULL,
    safety_stock_units INTEGER NOT NULL CHECK (safety_stock_units >= 0),
    reorder_point_units INTEGER NOT NULL CHECK (reorder_point_units >= safety_stock_units),
    max_shelf_capacity_units INTEGER NOT NULL CHECK (max_shelf_capacity_units > 0),
    review_cycle_days INTEGER NOT NULL CHECK (review_cycle_days > 0),
    UNIQUE (store_id, sku_id)
);

CREATE TABLE IF NOT EXISTS sales_history (
    sale_id VARCHAR(48) PRIMARY KEY,
    store_id VARCHAR(16) NOT NULL REFERENCES store(store_id),
    sku_id VARCHAR(16) NOT NULL REFERENCES sku(sku_id),
    sale_date DATE NOT NULL,
    units_sold INTEGER NOT NULL CHECK (units_sold >= 0),
    true_unconstrained_demand INTEGER NOT NULL CHECK (true_unconstrained_demand >= units_sold),
    lost_sales_units INTEGER NOT NULL CHECK (lost_sales_units >= 0),
    promo_flag BOOLEAN NOT NULL,
    discount_pct DECIMAL(4, 2) NOT NULL CHECK (discount_pct >= 0.0 AND discount_pct <= 0.80),
    stockout_censored_flag BOOLEAN NOT NULL,
    gross_revenue DECIMAL(12, 2) NOT NULL CHECK (gross_revenue >= 0.0),
    UNIQUE (store_id, sku_id, sale_date)
);

CREATE TABLE IF NOT EXISTS inventory_snapshot (
    snapshot_id VARCHAR(48) PRIMARY KEY,
    store_id VARCHAR(16) NOT NULL REFERENCES store(store_id),
    sku_id VARCHAR(16) NOT NULL REFERENCES sku(sku_id),
    snapshot_date DATE NOT NULL,
    opening_on_hand INTEGER NOT NULL CHECK (opening_on_hand >= 0),
    receipts_units INTEGER NOT NULL CHECK (receipts_units >= 0),
    units_sold INTEGER NOT NULL CHECK (units_sold >= 0),
    closing_on_hand INTEGER NOT NULL CHECK (closing_on_hand >= 0),
    on_order_units INTEGER NOT NULL CHECK (on_order_units >= 0),
    stockout_flag BOOLEAN NOT NULL,
    inventory_status VARCHAR(16) NOT NULL CHECK (inventory_status IN ('IN_STOCK', 'LOW_STOCK', 'STOCKOUT')),
    UNIQUE (store_id, sku_id, snapshot_date)
);

CREATE TABLE IF NOT EXISTS forecast (
    forecast_id VARCHAR(48) PRIMARY KEY,
    store_id VARCHAR(16) NOT NULL REFERENCES store(store_id),
    sku_id VARCHAR(16) NOT NULL REFERENCES sku(sku_id),
    forecast_period VARCHAR(12) NOT NULL,
    train_window_start DATE NOT NULL,
    train_window_end DATE NOT NULL,
    horizon_days INTEGER NOT NULL CHECK (horizon_days > 0),
    forecast_daily_mean DECIMAL(10, 2) NOT NULL CHECK (forecast_daily_mean >= 0),
    forecast_total_units DECIMAL(10, 2) NOT NULL CHECK (forecast_total_units >= 0),
    baseline_naive_total_units DECIMAL(10, 2) NOT NULL CHECK (baseline_naive_total_units >= 0),
    holdout_actual_units INTEGER NOT NULL CHECK (holdout_actual_units >= 0),
    model_method VARCHAR(36) NOT NULL,
    UNIQUE (store_id, sku_id, forecast_period)
);

CREATE TABLE IF NOT EXISTS purchase_recommendation (
    po_id VARCHAR(24) PRIMARY KEY,
    store_id VARCHAR(16) NOT NULL REFERENCES store(store_id),
    sku_id VARCHAR(16) NOT NULL REFERENCES sku(sku_id),
    supplier_id VARCHAR(16) NOT NULL REFERENCES supplier(supplier_id),
    forecast_id VARCHAR(48) NOT NULL REFERENCES forecast(forecast_id),
    policy_id VARCHAR(32) NOT NULL REFERENCES reorder_policy(policy_id),
    recommendation_date DATE NOT NULL,
    closing_on_hand_units INTEGER NOT NULL CHECK (closing_on_hand_units >= 0),
    on_order_units INTEGER NOT NULL CHECK (on_order_units >= 0),
    inventory_position_units INTEGER NOT NULL CHECK (inventory_position_units = closing_on_hand_units + on_order_units),
    target_stock_level_units INTEGER NOT NULL,
    raw_needed_units INTEGER NOT NULL,
    pack_size INTEGER NOT NULL,
    moq_units INTEGER NOT NULL,
    max_shelf_capacity_units INTEGER NOT NULL,
    recommended_order_units INTEGER NOT NULL,
    order_status VARCHAR(24) NOT NULL CHECK (order_status IN ('RECOMMENDED', 'CAPACITY_CAPPED', 'HOLD_EXCEPTION')),
    decision_trace VARCHAR(320) NOT NULL
);