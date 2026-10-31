# SKU-Location Demand Forecasting & Replenishment Engine

An end-to-end synthetic data generation, stockout-aware demand forecasting, and constrained replenishment system built for Python 3.10+ on Windows 10, Linux, and macOS. It uses only the Python standard library for its core pipeline and live HTTP backend server, so it runs immediately with zero compilation or external dependency friction.

## 1. Business Context, Primary Actors & Nomenclature

- **Business Problem**: Forecast store-SKU demand across 365 days and recommend replenishment orders that respect supplier lead-time distributions, safety stock targets, minimum order quantities (MOQ), discrete pack sizes, and store storage capacity ceilings—while separating true customer demand from stockout-censored POS sales.
- **Primary Actors & Systems**:
  - **Customer**: Generates daily store-SKU demand (smooth, seasonal, and intermittent profiles) influenced by promotions and day-of-week patterns.
  - **Store / Warehouse Operator**: Tracks daily opening/closing inventory balances (`InventorySnapshot`), receives supplier shipments (`LeadTimeObservation`), and enforces shelf and backroom storage limits (`max_shelf_capacity_units` and `Store.max_storage_capacity`).
  - **Merchandising / E-Commerce Analyst**: Evaluates 14-day temporal holdout demand forecasts (`Forecast`) against a naive moving-average baseline and monitors stockout censoring (`stockout_censored_flag`).
  - **Operations Manager**: Reviews constrained purchase order recommendations (`PurchaseRecommendation`), safety stock policies (`ReorderPolicy`), and `HOLD_EXCEPTION` audit traces (`decision_trace`).
- **Deterministic ID & Nomenclature Conventions**:
  - `SKU`: `SKU-000001` .. `SKU-002000`
  - `Store`: `STORE-000001` .. `STORE-000100`
  - `Supplier`: `SUP-0001` .. `SUP-0040`
  - `SupplierSKU` (N:M Bridge): `SSKU-000001` .. `SSKU-002509`
  - `SalesHistory`: `SALE-<store-id>-<sku>-<YYYY-MM-DD>` (e.g., `SALE-STORE-000001-SKU-000138-2025-12-31`)
  - `InventorySnapshot`: `INV-<store-id>-<sku>-<YYYY-MM-DD>`
  - `Forecast`: `FC-<store-id>-<sku>-2026-01` (e.g., `FC-STORE-000001-SKU-000138-2026-01`)
  - `PurchaseRecommendation`: `PO-2026-000001` .. `PO-2026-000185`

## 2. Organized Project Layout

```text
sku_replenishment_project_bundle/
├── run_app.bat                     # One-click Windows 10 launcher for Backend + Frontend
├── README.md                       # Execution guide, business rules, and architecture
├── Prompt_history.md               # Documented prompt history for library & UI setup
├── requirements.txt                # Optional analytics/test packages (numpy, pandas, pytest)
├── backend/
│   ├── app_server.py               # Live Python HTTP Server & REST API (/api/status, /api/run-pipeline)
│   ├── generate_pipeline.py        # Step 2–9 Generator, Forecaster, Baseline & PO Engine
│   ├── validate_and_evaluate.py    # Step 8 & 10 Validator, Holdout Evaluator & Checksum Verifier
│   └── schema.sql                  # Standard ANSI SQL DDL compatible with PostgreSQL 14+ & SQLite 3.x
├── frontend/
│   └── index.html                  # Interactive Full-Stack Console with Decision Traceability
├── docs/
│   └── DATA_DICTIONARY.md          # Step 1 Granular Field Rules, Types, Units & Cardinality Spec
└── data_out/
    ├── *.csv (11 tables)           # SKU, Store, Supplier, SalesHistory, InventorySnapshot, etc.
    ├── *.json (5 files)            # Forecast, PurchaseRecommendation, GroundTruth, Manifest, Summary
    └── seed_data.sql               # Deterministic ANSI SQL Seed Inserts
```

## 3. Step-by-Step Setup & Execution Guide (Windows 10 & Python 3.10)

Open **PowerShell** or **Command Prompt (`cmd.exe`)** on Windows 10 and follow these exact steps in order:

### Step 1: Navigate to the Project Folder
```powershell
cd C:\path\to\sku_replenishment_project_bundle
```

### Step 2: Create and Activate a Python 3.10 Virtual Environment
**Option A — Using Conda (Recommended if Anaconda / Miniconda is installed):**
```powershell
conda create -n sku_env python=3.10 -y
conda activate sku_env
python --version
```

**Option B — Using Standard Python 3.10 `venv`:**
```powershell
py -3.10 -m venv venv
.\venv\Scripts\activate
python --version
```
*(Note: If using Command Prompt `cmd.exe` instead of PowerShell, activate with `venv\Scripts\activate.bat`)*

### Step 3: Install Dependencies from `requirements.txt`
```powershell
pip install -r requirements.txt
```

### ## 4. Temporal Holdout Window & Baseline Forecasting Benchmark

- **365-Day Simulation Window**: `2025-01-15` through `2026-01-14`
  - **Training Window (351 days)**: `2025-01-15` through `2025-12-31` (Cutoff Date = `2025-12-31`)
  - **Holdout Evaluation Window (14 days, `forecast_period = 2026-01`)**: `2026-01-01` through `2026-01-14` (`FC-<store-id>-<sku>-2026-01`)

- **Stockout-Aware Imputed Model vs. Simple Naive Baseline**:
  - **Simple Naive Baseline (`baseline_naive_total_units`)**: Trailing 56-day simple moving average of raw recorded `units_sold` (which treats stockout days with 0 units sold as zero customer demand). Achieves **19.65% WAPE** (`MAE = 20.81` units, `Bias = -16.16` units).
  - **Stockout-Imputed Forecast (`forecast_total_units`)**: Excludes days where `stockout_censored_flag == True` when estimating velocity. Achieves **12.35% WAPE** (`MAE = 13.08` units, `Bias = -6.92` units)—a **37.15% relative reduction in WAPE** by eliminating stockout downward bias.'''

### Step 5: Execute the Validation, Holdout Evaluation & Reproducibility Suite (`backend\validate_and_evaluate.py`)
Checks primary-key uniqueness, foreign-key integrity across all 20 relationships, allowed enums, inventory balance & position reconciliation (`closing_on_hand + on_order == inventory_position`), SKU-shelf and Store-level storage capacity ceilings, temporal holdout forecast accuracy vs. a naive baseline, ground-truth anomaly detection, and dual-run SHA-256 checksum reproducibility:
```powershell
python backend\validate_and_evaluate.py --data-dir data_out --seed 20261022 --scale starter
```

### Step 6: Launch the Live Full-Stack Web Application (`backend\app_server.py`)
Run the command below (or double-click **`run_app.bat`** in Windows Explorer):
```powershell
python backend\app_server.py --port 8000 --data-dir data_out
```
This starts the live local server at `http://127.0.0.1:8000`, opens `frontend/index.html` in your browser, and exposes `GET /api/status` and `POST /api/run-pipeline` so clicking **Execute Pipeline & Recompute Now** in the UI executes the Python backend on disk and updates all charts and tables in real time.

## 4. Temporal Holdout Window & Baseline Forecasting Benchmark

- **365-Day Simulation Window**: `2025-01-16` through `2026-01-14`
  - **Training Window (351 days)**: `2025-01-16` through `2025-12-31` (Cutoff Date = `2025-12-31`)
  - **Holdout Evaluation Window (14 days, `forecast_period = 2026-01`)**: `2026-01-01` through `2026-01-14` (`FC-<store-id>-<sku>-2026-01`)
- **Stockout-Aware Imputed Model vs. Simple Naive Baseline**:
  - **Simple Naive Baseline (`baseline_naive_total_units`)**: Trailing 56-day simple moving average of raw recorded `units_sold` (which treats stockout days with 0 units sold as zero customer demand). Achieves **19.65% WAPE** (`MAE = 20.81` units, `Bias = -16.16` units).
  - **Stockout-Imputed Forecast (`forecast_total_units`)**: Excludes days where `stockout_censored_flag == True` when estimating velocity. Achieves **12.35% WAPE** (`MAE = 13.08` units, `Bias = -6.92` units)—a **37.15% relative reduction in WAPE** by eliminating stockout downward bias.

## 5. Inventory-Position, Storage-Capacity & Decision Traceability Semantics

1. **Safety Stock & Reorder Point Formula (`ReorderPolicy`)**:
   $$\text{Safety Stock} = \lceil z_{\alpha} \times \sqrt{\mu_L \sigma_d^2 + \mu_d^2 \sigma_L^2} \rceil, \quad \text{ROP} = \lceil \mu_d \times \mu_L \rceil + \text{Safety Stock}$$
2. **Explicit Inventory Position Reconciliation**:
   At the `2025-12-31` cutoff date, each `PurchaseRecommendation` explicitly records `closing_on_hand_units`, `on_order_units`, and `inventory_position_units = closing_on_hand_units + on_order_units`, reconciled 1:1 against `InventorySnapshot`.
3. **Dual Storage-Capacity Enforcement**:
   Every clean order enforces both SKU-level shelf capacity (`inventory_position_units + recommended_order_units <= ReorderPolicy.max_shelf_capacity_units`) and aggregate store-level warehouse capacity (`sum(committed_units) <= Store.max_storage_capacity`).
4. **Explicit Decision Traceability (`decision_trace`)**:
   Every `PurchaseRecommendation` row includes a human-readable `decision_trace` string explaining the exact calculation path (`RECOMMENDED`, `CAPACITY_CAPPED`, or `HOLD_EXCEPTION` with the specific rule violated).

## 6. Injected Edge Cases & Ground Truth Separation (`ground_truth.csv`)

All 5 required negative scenarios (plus valid capacity-capped boundary cases) are logged in `ground_truth.csv` / `ground_truth.json` without leaking labels into input tables:

| Issue Type | Target Entity | Count | Description & Expected System Decision |
| :--- | :--- | :--- | :--- |
| `STOCKOUT_MISTAKEN_FOR_ZERO_DEMAND` | `SalesHistory` | 15 | Stockout day (`units_sold = 0`, `true_unconstrained_demand > 0`) has `stockout_censored_flag = False`. Expected: `IMPUTE_CENSORED_DEMAND`. |
| `REORDER_IGNORES_PACK_SIZE` | `PurchaseRecommendation` | 7 | `recommended_order_units` is not divisible by `pack_size` (`HOLD_EXCEPTION`). Expected: `ROUND_TO_PACK_SIZE`. |
| `DISCONTINUED_SKU_RECOMMENDED` | `PurchaseRecommendation` | 3 | Replenishment PO created for a SKU with `lifecycle_state = DISCONTINUED` (`HOLD_EXCEPTION`). Expected: `REJECT_DISCONTINUED_SKU`. |
| `LEAD_TIME_NEGATIVE` | `LeadTimeObservation` | 8 | `received_date` is earlier than `order_date` (`actual_lead_time_days = -3`). Expected: `REJECT_INVALID_LEAD_TIME`. |
| `FORECAST_USES_FUTURE_SALES` | `Forecast` | 8 | `train_window_end` extends to `2026-01-14` (past the `2025-12-31` cutoff), leaking holdout actuals. Expected: `REJECT_DATA_LEAKAGE`. |
| `CAPACITY_CONSTRAINED_ORDER` | `PurchaseRecommendation` | 10 | Valid boundary benchmark where order is capped by `max_shelf_capacity_units` (`is_anomaly = False`). Expected: `CAP_AT_STORAGE_LIMIT`. |

## 7. Fixed-Seed Reproducibility & Lawful Data Provenance

- **100% Fixed-Seed Reproducibility (Step 10)**: Running `validate_and_evaluate.py --seed 20261022` regenerates all 15 CSV, JSON, and SQL files twice in isolated directories and verifies 100% identical row counts and SHA-256 digests (`reproducible_100_percent: true` in `data_out/validation_summary.json` and `data_out/source_manifest.json`).
- **Lawful Provenance & Licensing**: All records are 100% synthetically generated from documented supply-chain domain rules using fixed seed `20261022` (`external_data_used: false`). No proprietary, confidential, or personal data is accessed or redistributed.
