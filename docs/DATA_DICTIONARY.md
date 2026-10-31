# Data Dictionary & Entity-Relationship Specification

## 1. Entity-Relationship Overview & Cardinality

The system models retail SKU-location demand forecasting and inventory replenishment across 10 core operational tables plus an isolated ground-truth audit log (`ground_truth.csv` / `ground_truth.json`).

| Parent Entity | Child Entity | Cardinality | Optionality | Relationship Description |
| :--- | :--- | :--- | :--- | :--- |
| `SKU` | `SupplierSKU` | 1 : N | Mandatory (Active SKUs have >=1 supplier) | Bridge table connecting SKUs to approved suppliers with pack sizes and MOQs. |
| `Supplier` | `SupplierSKU` | 1 : N | Optional (New suppliers may have 0 SKUs initially) | Bridge table connecting suppliers to the SKUs they supply. |
| `SupplierSKU` | `LeadTimeObservation` | 1 : N | Optional (Newly onboarded links may have 0 historical shipments) | Historical PO-to-receipt lead time records for a specific supplier-SKU pair. |
| `Store`, `SKU`, `Supplier` | `ReorderPolicy` | 1 : N | Mandatory for stocked SKU-Store pairs | Defines target service level, reorder point (ROP), safety stock, and shelf capacity per store-SKU. |
| `Store`, `SKU` | `SalesHistory` | 1 : N | Optional (Unstocked pairs have 0 rows) | Daily demand and sales transactions per store-SKU (`2025-01-16` to `2026-01-14`). |
| `Store`, `SKU` | `InventorySnapshot` | 1 : N | Optional (Unstocked pairs have 0 rows) | Daily end-of-day inventory balances and stockout indicators per store-SKU (`2025-01-16` to `2026-01-14`). |
| `Store`, `SKU` | `Forecast` | 1 : N | Mandatory for forecasted pairs | Horizon demand forecast (`2026-01`, covering `2026-01-01` to `2026-01-14`) computed at cutoff `2025-12-31` alongside a naive baseline. |
| `Forecast`, `ReorderPolicy`, `Supplier` | `PurchaseRecommendation` | 1 : N | Optional (Only generated when review triggers or evaluated) | Final replenishment order recommendations respecting MOQ, pack size, store/shelf capacity, and decision traceability. |

*Note on Anomaly Isolation*: All input tables (`SKU` through `PurchaseRecommendation`) contain purely operational fields. Deliberately injected edge cases are recorded in `ground_truth.csv` / `ground_truth.json` keyed by `entity_type` and `record_id` so evaluation labels never leak into input features.

## 2. Granular Table & Field Specifications

### 2.1 `SKU` (`sku.csv`)
Master catalog of products.
- **Primary Key**: `sku_id`

| Field Name | Type | Required | Allowed Values / Format | Units | Uniqueness | Validation Rule |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `sku_id` | STRING | Required | `SKU-000001` to `SKU-999999` | ID | Unique (PK) | Regex `^SKU-\d{6}$` |
| `sku_name` | STRING | Required | Non-empty printable string | Text | Non-unique | Length 3..120 chars |
| `category` | STRING | Required | `Beverages`, `Dairy`, `Dry_Grocery`, `Household`, `Personal_Care`, `Produce` | Category | Non-unique | Must be in allowed enum list |
| `demand_profile` | STRING | Required | `SMOOTH`, `SEASONAL`, `INTERMITTENT` | Enum | Non-unique | Must be in allowed enum list |
| `unit_cost` | FLOAT | Required | `> 0.0` | USD ($) | Non-unique | `0.25 <= unit_cost <= 500.00` |
| `unit_price` | FLOAT | Required | `>= unit_cost` | USD ($) | Non-unique | `unit_price >= unit_cost` |
| `lifecycle_state` | STRING | Required | `LAUNCH`, `ACTIVE`, `PHASE_OUT`, `DISCONTINUED` | Enum | Non-unique | Valid lifecycle state; `DISCONTINUED` SKUs cannot have new approved POs |
| `effective_start_date` | DATE | Required | `YYYY-MM-DD` | ISO Date | Non-unique | Valid calendar date |
| `effective_end_date` | DATE | Optional | `YYYY-MM-DD` or empty | ISO Date | Non-unique | Empty or `>= effective_start_date`; required if `DISCONTINUED` |

### 2.2 `Store` (`store.csv`)
Master table of retail locations and fulfillment nodes.
- **Primary Key**: `store_id`

| Field Name | Type | Required | Allowed Values / Format | Units | Uniqueness | Validation Rule |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `store_id` | STRING | Required | `STORE-000001` to `STORE-999999` | ID | Unique (PK) | Regex `^STORE-\d{6}$` |
| `store_name` | STRING | Required | Non-empty string | Text | Unique | Length 3..80 chars |
| `region` | STRING | Required | `NORTH`, `SOUTH`, `EAST`, `WEST`, `CENTRAL` | Enum | Non-unique | Must be in allowed enum list |
| `store_format` | STRING | Required | `HYPERMARKET`, `SUPERMARKET`, `EXPRESS` | Enum | Non-unique | Must be in allowed enum list |
| `max_storage_capacity` | INTEGER | Required | `> 0` | Units | Non-unique | `500 <= max_storage_capacity <= 100000`; aggregate store inventory + POs must not exceed |
| `lifecycle_state` | STRING | Required | `OPEN`, `RENOVATION`, `CLOSED` | Enum | Non-unique | Must be in allowed enum list |
| `opened_date` | DATE | Required | `YYYY-MM-DD` | ISO Date | Non-unique | Valid calendar date `<= 2025-12-31` |

### 2.3 `Supplier` (`supplier.csv`)
Master table of external vendors.
- **Primary Key**: `supplier_id`

| Field Name | Type | Required | Allowed Values / Format | Units | Uniqueness | Validation Rule |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `supplier_id` | STRING | Required | `SUP-0001` to `SUP-9999` | ID | Unique (PK) | Regex `^SUP-\d{4}$` |
| `supplier_name` | STRING | Required | Non-empty string | Text | Unique | Length 3..100 chars |
| `country_code` | STRING | Required | `US`, `CA`, `MX`, `IN`, `DE` | ISO-2 | Non-unique | 2-letter uppercase ISO country code |
| `reliability_score` | FLOAT | Required | `0.0` to `1.0` | Ratio | Non-unique | `0.0 <= reliability_score <= 1.0` |
| `lifecycle_state` | STRING | Required | `ACTIVE`, `ON_HOLD`, `INACTIVE` | Enum | Non-unique | Must be in allowed enum list |
| `effective_date` | DATE | Required | `YYYY-MM-DD` | ISO Date | Non-unique | Valid calendar date |

### 2.4 `SupplierSKU` (`supplier_sku.csv`)
Bridge table for the many-to-many (`N:M`) relationship between `Supplier` and `SKU`, defining ordering constraints and lead-time parameters.
- **Primary Key**: `supplier_sku_id`
- **Foreign Keys**: `supplier_id -> Supplier.supplier_id`, `sku_id -> SKU.sku_id`

| Field Name | Type | Required | Allowed Values / Format | Units | Uniqueness | Validation Rule |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `supplier_sku_id` | STRING | Required | `SSKU-000001` | ID | Unique (PK) | Regex `^SSKU-\d{6}$` |
| `supplier_id` | STRING | Required | Valid `Supplier.supplier_id` | ID | Composite Unique (`supplier_id`, `sku_id`) | FK integrity to `Supplier` |
| `sku_id` | STRING | Required | Valid `SKU.sku_id` | ID | Composite Unique (`supplier_id`, `sku_id`) | FK integrity to `SKU` |
| `is_primary_supplier` | BOOLEAN | Required | `True`, `False` | Boolean | Non-unique | Exactly one primary supplier per active SKU |
| `pack_size` | INTEGER | Required | `> 0` (6, 12, 24, 48) | Units/Pack | Non-unique | `pack_size >= 1` |
| `moq_units` | INTEGER | Required | `>= pack_size` | Units | Non-unique | `moq_units >= pack_size` and `moq_units % pack_size == 0` |
| `expected_lead_time_days` | FLOAT | Required | `> 0` | Days | Non-unique | `1.0 <= expected_lead_time_days <= 60.0` |
| `lead_time_std_days` | FLOAT | Required | `>= 0` | Days | Non-unique | `0.0 <= lead_time_std_days <= 30.0` |
| `effective_start_date` | DATE | Required | `YYYY-MM-DD` | ISO Date | Non-unique | Valid calendar date |

### 2.5 `LeadTimeObservation` (`lead_time_observation.csv`)
Historical shipment records tracking actual vs. promised supplier delivery times, including supplier delays.
- **Primary Key**: `observation_id`
- **Foreign Keys**: `supplier_sku_id -> SupplierSKU.supplier_sku_id`, `supplier_id -> Supplier.supplier_id`, `sku_id -> SKU.sku_id`, `store_id -> Store.store_id`

| Field Name | Type | Required | Allowed Values / Format | Units | Uniqueness | Validation Rule |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `observation_id` | STRING | Required | `LTO-000001` | ID | Unique (PK) | Regex `^LTO-\d{6}$` |
| `supplier_sku_id` | STRING | Required | Valid `SupplierSKU.supplier_sku_id` | ID | Non-unique | FK integrity to `SupplierSKU` |
| `supplier_id` | STRING | Required | Valid `Supplier.supplier_id` | ID | Non-unique | FK integrity to `Supplier` |
| `sku_id` | STRING | Required | Valid `SKU.sku_id` | ID | Non-unique | FK integrity to `SKU` |
| `store_id` | STRING | Required | Valid `Store.store_id` | ID | Non-unique | FK integrity to `Store` |
| `order_date` | DATE | Required | `YYYY-MM-DD` | ISO Date | Non-unique | Valid date |
| `received_date` | DATE | Required | `YYYY-MM-DD` | ISO Date | Non-unique | `received_date >= order_date` (violated in `LEAD_TIME_NEGATIVE` edge case) |
| `actual_lead_time_days` | INTEGER | Required | `> 0` | Days | Non-unique | `actual_lead_time_days == (received_date - order_date).days` and `> 0` |
| `delay_days` | INTEGER | Required | Integer | Days | Non-unique | `max(0, actual_lead_time_days - round(expected_lead_time_days))` |

### 2.6 `SalesHistory` (`sales_history.csv`)
Daily store-SKU sales records capturing promotions, seasonality, and stockout-censored demand across `2025-01-16` through `2026-01-14`.
- **Primary Key**: `sale_id`
- **Foreign Keys**: `store_id -> Store.store_id`, `sku_id -> SKU.sku_id`

| Field Name | Type | Required | Allowed Values / Format | Units | Uniqueness | Validation Rule |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `sale_id` | STRING | Required | `SALE-<store_id>-<sku_id>-<YYYY-MM-DD>` | ID | Unique (PK) | Regex `^SALE-STORE-\d{6}-SKU-\d{6}-\d{4}-\d{2}-\d{2}$` |
| `store_id` | STRING | Required | Valid `Store.store_id` | ID | Composite Unique (`store_id`, `sku_id`, `sale_date`) | FK integrity to `Store` |
| `sku_id` | STRING | Required | Valid `SKU.sku_id` | ID | Composite Unique (`store_id`, `sku_id`, `sale_date`) | FK integrity to `SKU` |
| `sale_date` | DATE | Required | `2025-01-16` to `2026-01-14` | ISO Date | Composite Unique (`store_id`, `sku_id`, `sale_date`) | Valid date in simulation window |
| `units_sold` | INTEGER | Required | `>= 0` | Units | Non-unique | `units_sold >= 0` |
| `true_unconstrained_demand` | INTEGER | Required | `>= units_sold` | Units | Non-unique | `true_unconstrained_demand >= units_sold` |
| `lost_sales_units` | INTEGER | Required | `>= 0` | Units | Non-unique | `lost_sales_units == true_unconstrained_demand - units_sold` |
| `promo_flag` | BOOLEAN | Required | `True`, `False` | Boolean | Non-unique | Boolean |
| `discount_pct` | FLOAT | Required | `0.0` to `0.50` | Ratio | Non-unique | `0.0` if `promo_flag == False`, else `> 0.0` |
| `stockout_censored_flag` | BOOLEAN | Required | `True`, `False` | Boolean | Non-unique | `True` when demand was truncated by stockout (violated in `STOCKOUT_MISTAKEN_FOR_ZERO_DEMAND`) |
| `gross_revenue` | FLOAT | Required | `>= 0.0` | USD ($) | Non-unique | `round(units_sold * unit_price * (1 - discount_pct), 2)` |

### 2.7 `InventorySnapshot` (`inventory_snapshot.csv`)
Daily end-of-day inventory ledger preserving full state history across `2025-01-16` through `2026-01-14`.
- **Primary Key**: `snapshot_id`
- **Foreign Keys**: `store_id -> Store.store_id`, `sku_id -> SKU.sku_id`

| Field Name | Type | Required | Allowed Values / Format | Units | Uniqueness | Validation Rule |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `snapshot_id` | STRING | Required | `INV-<store_id>-<sku_id>-<YYYY-MM-DD>` | ID | Unique (PK) | Regex `^INV-STORE-\d{6}-SKU-\d{6}-\d{4}-\d{2}-\d{2}$` |
| `store_id` | STRING | Required | Valid `Store.store_id` | ID | Composite Unique (`store_id`, `sku_id`, `snapshot_date`) | FK integrity to `Store` |
| `sku_id` | STRING | Required | Valid `SKU.sku_id` | ID | Composite Unique (`store_id`, `sku_id`, `snapshot_date`) | FK integrity to `SKU` |
| `snapshot_date` | DATE | Required | `2025-01-16` to `2026-01-14` | ISO Date | Composite Unique (`store_id`, `sku_id`, `snapshot_date`) | Valid date in simulation window |
| `opening_on_hand` | INTEGER | Required | `>= 0` | Units | Non-unique | Equals prior day `closing_on_hand` |
| `receipts_units` | INTEGER | Required | `>= 0` | Units | Non-unique | `receipts_units >= 0` |
| `units_sold` | INTEGER | Required | `>= 0` | Units | Non-unique | Matches `SalesHistory.units_sold` for same store-SKU-date |
| `closing_on_hand` | INTEGER | Required | `>= 0` | Units | Non-unique | `opening_on_hand + receipts_units - units_sold == closing_on_hand` |
| `on_order_units` | INTEGER | Required | `>= 0` | Units | Non-unique | Open PO quantity in transit |
| `stockout_flag` | BOOLEAN | Required | `True`, `False` | Boolean | Non-unique | `True` if `closing_on_hand == 0` while SKU is active |
| `inventory_status` | STRING | Required | `IN_STOCK`, `LOW_STOCK`, `STOCKOUT` | Enum | Non-unique | `STOCKOUT` if `closing_on_hand == 0` |

### 2.8 `ReorderPolicy` (`reorder_policy.csv`)
Store-SKU inventory control parameters derived from lead time distributions and target service levels.
- **Primary Key**: `policy_id`
- **Foreign Keys**: `store_id -> Store.store_id`, `sku_id -> SKU.sku_id`, `primary_supplier_id -> Supplier.supplier_id`

| Field Name | Type | Required | Allowed Values / Format | Units | Uniqueness | Validation Rule |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `policy_id` | STRING | Required | `RP-<store_id>-<sku_id>` | ID | Unique (PK) | Regex `^RP-STORE-\d{6}-SKU-\d{6}$` |
| `store_id` | STRING | Required | Valid `Store.store_id` | ID | Composite Unique (`store_id`, `sku_id`) | FK integrity to `Store` |
| `sku_id` | STRING | Required | Valid `SKU.sku_id` | ID | Composite Unique (`store_id`, `sku_id`) | FK integrity to `SKU` |
| `primary_supplier_id` | STRING | Required | Valid `Supplier.supplier_id` | ID | Non-unique | FK integrity to `Supplier` |
| `service_level_target` | FLOAT | Required | `0.90`, `0.95`, `0.98` | Probability | Non-unique | `0.50 <= service_level_target <= 0.999` |
| `z_score` | FLOAT | Required | `1.2816`, `1.6449`, `2.0537` | Z-value | Non-unique | Matches standard normal quantile for `service_level_target` |
| `safety_stock_units` | INTEGER | Required | `>= 0` | Units | Non-unique | `ceil(z * sqrt(L * sigma_d^2 + d^2 * sigma_L^2))` |
| `reorder_point_units` | INTEGER | Required | `>= safety_stock_units` | Units | Non-unique | `ceil(avg_daily_demand * mean_lead_time) + safety_stock_units` |
| `max_shelf_capacity_units` | INTEGER | Required | `> reorder_point_units` | Units | Non-unique | Store shelf cap for this SKU (`<= Store.max_storage_capacity`) |
| `review_cycle_days` | INTEGER | Required | `7` or `14` | Days | Non-unique | `review_cycle_days > 0` |

### 2.9 `Forecast` (`forecast.csv` / `forecast.json`)
Demand forecasts generated at the temporal holdout cutoff (`2025-12-31`) for the evaluation horizon `2026-01` (`2026-01-01` to `2026-01-14`, `FC-<store-id>-<sku>-2026-01`), including a naive unimputed baseline benchmark.
- **Primary Key**: `forecast_id`
- **Foreign Keys**: `store_id -> Store.store_id`, `sku_id -> SKU.sku_id`

| Field Name | Type | Required | Allowed Values / Format | Units | Uniqueness | Validation Rule |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `forecast_id` | STRING | Required | `FC-<store_id>-<sku_id>-2026-01` | ID | Unique (PK) | Regex `^FC-STORE-\d{6}-SKU-\d{6}-2026-01$` |
| `store_id` | STRING | Required | Valid `Store.store_id` | ID | Composite Unique (`store_id`, `sku_id`, `forecast_period`) | FK integrity to `Store` |
| `sku_id` | STRING | Required | Valid `SKU.sku_id` | ID | Composite Unique (`store_id`, `sku_id`, `forecast_period`) | FK integrity to `SKU` |
| `forecast_period` | STRING | Required | `2026-01` | Period | Non-unique | Matches `YYYY-MM` of holdout evaluation window (`2026-01-01`..`2026-01-14`) |
| `train_window_start` | DATE | Required | `2025-01-16` | ISO Date | Non-unique | `train_window_start < train_window_end` |
| `train_window_end` | DATE | Required | `2025-12-31` | ISO Date | Non-unique | `<= cutoff_date` (`2025-12-31`); violated in `FORECAST_USES_FUTURE_SALES` (`2026-01-14`) |
| `horizon_days` | INTEGER | Required | `14` | Days | Non-unique | `horizon_days == 14` |
| `forecast_daily_mean` | FLOAT | Required | `>= 0.0` | Units/Day | Non-unique | Stockout-imputed baseline daily forecast |
| `forecast_total_units` | FLOAT | Required | `>= 0.0` | Units | Non-unique | `round(forecast_daily_mean * horizon_days, 2)` |
| `baseline_naive_total_units` | FLOAT | Required | `>= 0.0` | Units | Non-unique | Unimputed 56-day simple moving average benchmark (`treats stockouts as zero demand`) |
| `holdout_actual_units` | INTEGER | Required | `>= 0` | Units | Non-unique | Sum of uncensored demand in `2026-01` holdout window (`2026-01-01` to `2026-01-14`) |
| `model_method` | STRING | Required | `SEASONAL_MOVING_AVG_IMPUTED`, `CROSTON_SBA`, `LEAKED_FUTURE_LOOKAHEAD` | Enum | Non-unique | Valid forecasting method |

### 2.10 `PurchaseRecommendation` (`purchase_recommendation.csv` / `purchase_recommendation.json`)
Replenishment purchase orders generated at cutoff `2025-12-31` for `2026-01` from forecasts, explicit inventory positions (`closing_on_hand_units + on_order_units`), reorder policies, supplier constraints, and decision traces.
- **Primary Key**: `po_id`
- **Foreign Keys**: `store_id -> Store.store_id`, `sku_id -> SKU.sku_id`, `supplier_id -> Supplier.supplier_id`, `forecast_id -> Forecast.forecast_id`, `policy_id -> ReorderPolicy.policy_id`

| Field Name | Type | Required | Allowed Values / Format | Units | Uniqueness | Validation Rule |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `po_id` | STRING | Required | `PO-2026-000001` | ID | Unique (PK) | Regex `^PO-2026-\d{6}$` |
| `store_id` | STRING | Required | Valid `Store.store_id` | ID | Non-unique | FK integrity to `Store` |
| `sku_id` | STRING | Required | Valid `SKU.sku_id` | ID | Non-unique | FK integrity to `SKU` (must be `ACTIVE`, `LAUNCH`, or `PHASE_OUT`; violated in `DISCONTINUED_SKU_RECOMMENDED`) |
| `supplier_id` | STRING | Required | Valid `Supplier.supplier_id` | ID | Non-unique | FK integrity to `Supplier` |
| `forecast_id` | STRING | Required | Valid `Forecast.forecast_id` | ID | Non-unique | FK integrity to `Forecast` |
| `policy_id` | STRING | Required | Valid `ReorderPolicy.policy_id` | ID | Non-unique | FK integrity to `ReorderPolicy` |
| `recommendation_date` | DATE | Required | `2025-12-31` | ISO Date | Non-unique | Matches forecast cutoff date |
| `closing_on_hand_units` | INTEGER | Required | `>= 0` | Units | Non-unique | Reconciles 1:1 with `InventorySnapshot.closing_on_hand` at cutoff date |
| `on_order_units` | INTEGER | Required | `>= 0` | Units | Non-unique | Reconciles 1:1 with `InventorySnapshot.on_order_units` at cutoff date |
| `inventory_position_units` | INTEGER | Required | `>= 0` | Units | Non-unique | `closing_on_hand_units + on_order_units == inventory_position_units` |
| `target_stock_level_units` | INTEGER | Required | `>= 0` | Units | Non-unique | `reorder_point_units + ceil(forecast_total_units)` |
| `raw_needed_units` | INTEGER | Required | `>= 0` | Units | Non-unique | `max(0, target_stock_level_units - inventory_position_units)` |
| `pack_size` | INTEGER | Required | `>= 1` | Units | Non-unique | Matches `SupplierSKU.pack_size` |
| `moq_units` | INTEGER | Required | `>= pack_size` | Units | Non-unique | Matches `SupplierSKU.moq_units` |
| `max_shelf_capacity_units` | INTEGER | Required | `> 0` | Units | Non-unique | Matches `ReorderPolicy.max_shelf_capacity_units` |
| `recommended_order_units` | INTEGER | Required | `>= 0` | Units | Non-unique | Must be `>= moq_units` (if `>0`), divisible by `pack_size` (violated in `REORDER_IGNORES_PACK_SIZE`), and `inventory_position + order <= max_shelf_capacity` |
| `order_status` | STRING | Required | `RECOMMENDED`, `CAPACITY_CAPPED`, `HOLD_EXCEPTION` | Enum | Non-unique | Valid status |
| `decision_trace` | STRING | Required | Non-empty explanation | Text | Non-unique | Explicit step-by-step audit trace of how the order or exception was derived |

### 2.11 `GroundTruth` (`ground_truth.csv` / `ground_truth.json`)
Separate audit and evaluation table containing all injected anomalies and expected replenishment decisions. Never joined or leaked into model inputs.
- **Primary Key**: `ground_truth_id`

| Field Name | Type | Required | Allowed Values / Format | Units | Uniqueness | Validation Rule |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `ground_truth_id` | STRING | Required | `GT-000001` | ID | Unique (PK) | Regex `^GT-\d{6}$` |
| `entity_type` | STRING | Required | `SalesHistory`, `PurchaseRecommendation`, `LeadTimeObservation`, `Forecast` | Table Name | Non-unique | Valid entity name |
| `record_id` | STRING | Required | Primary Key of target row | ID | Unique per entity | Must exist in target table |
| `issue_type` | STRING | Required | `STOCKOUT_MISTAKEN_FOR_ZERO_DEMAND`, `REORDER_IGNORES_PACK_SIZE`, `DISCONTINUED_SKU_RECOMMENDED`, `LEAD_TIME_NEGATIVE`, `FORECAST_USES_FUTURE_SALES`, `CAPACITY_CONSTRAINED_ORDER` | Enum | Non-unique | Documented rule label |
| `is_anomaly` | BOOLEAN | Required | `True`, `False` | Boolean | Non-unique | `True` for negative edge cases, `False` for valid boundary benchmarks |
| `expected_decision` | STRING | Required | `IMPUTE_CENSORED_DEMAND`, `ROUND_TO_PACK_SIZE`, `REJECT_DISCONTINUED_SKU`, `REJECT_INVALID_LEAD_TIME`, `REJECT_DATA_LEAKAGE`, `CAP_AT_STORAGE_LIMIT` | Enum | Non-unique | Expected system action |
| `expected_value` | FLOAT | Required | Numeric | Units / Days | Non-unique | True corrected numeric value |
| `observed_value` | FLOAT | Required | Numeric | Units / Days | Non-unique | Corrupted or constrained value in record |
| `rule_reference` | STRING | Required | Rule description | Text | Non-unique | Traceability description |
