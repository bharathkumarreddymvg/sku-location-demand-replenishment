# Prompt History (`Prompt_history.md`)

**Environment**: Windows 10 (PowerShell), Python 3.10+


## 1. Resolving Windows Library & Wheel Compatibility (`requirements.txt` & Conda Env)

### Prompt 1 — Fixing `pip install` Meson / MSVC Build Error on Windows 10
> **User Prompt:**
> I am setting up my virtual environment on Windows 10 for my SKU demand forecasting & replenishment project. My base environment uses Python 3.10, and my `requirements.txt` currently has `numpy==1.26.4`, `pandas==2.2.2`, and `pytest==8.2.2`. When I ran `pip install -r requirements.txt`, `pandas==2.2.2` tried to build from source (`pandas-2.2.2.tar.gz`) using Meson and failed with `fatal error C1083: Cannot open include file: 'stdalign.h'` because my active terminal picked up Python 3.13 from Anaconda `(base)`.
>
> Give me the exact compatible version constraints in `requirements.txt` so pre-built Windows `.whl` binaries install cleanly without compiling C/Cython code, plus the Conda commands to lock a clean Python 3.10 environment.

> **Assistant Response Summary:**
> - Explained that `pandas==2.2.2` did not ship pre-built `cp313-win_amd64.whl` wheels, triggering a source build against MSVC.
> - Updated `requirements.txt` to use flexible lower bounds (`numpy>=1.26.4`, `pandas>=2.2.3`, `pytest>=8.2.2`) so `pip` always selects pre-compiled Windows binary wheels on both Python 3.10 and Python 3.13+.
> - Provided the Conda environment setup commands (`conda create -n sku_env python=3.10 -y && conda activate sku_env`) while keeping the core backend generator and validator (`generate_pipeline.py` and `validate_and_evaluate.py`) strictly on the Python standard library (`csv`, `json`, `math`, `random`, `datetime`, `hashlib`, `pathlib`, `re`) so the pipeline runs with zero external dependency risk.

### Prompt 2 — Standardizing Cross-Platform SQL & Checksum Determinism
> **User Prompt:**
> I want my `backend/schema.sql` and `seed_data.sql` to be 100% compatible with both PostgreSQL 14+ and SQLite 3.x without dialect errors, and I need `write_csv` / `write_json` in Python on Windows 10 to produce the exact same SHA-256 checksums across runs without CRLF (`\r\n`) vs LF (`\n`) differences. Check my file writer helper and SQL header.

> **Assistant Response Summary:**
> - Configured `open(..., encoding="utf-8", newline="\n")` and `csv.DictWriter(..., lineterminator="\n")` so Windows 10 never injects `\r\n` line endings during SHA-256 reproducibility checks.
> - Removed SQLite-only `PRAGMA foreign_keys = ON;` from `backend/schema.sql` and standardized transaction blocks (`BEGIN; ... COMMIT;`) and boolean literals (`TRUE`/`FALSE`) for pure ANSI SQL compatibility.

## 2. Developing Parts of the Interactive Frontend (`frontend/index.html`)

### Prompt 3 — Scaffolding the Chart.js Canvas & Tab Layout for the Frontend
> **User Prompt:**
> I have already implemented the backend simulation, stockout-imputed forecast (`2026-01` holdout window `2026-01-01` to `2026-01-14` from cutoff `2025-12-31`), naive moving-average baseline benchmark, and purchase order recommendation logic in `backend/generate_pipeline.py` and `backend/validate_and_evaluate.py`.
>
> Now help me build the HTML/Tailwind/Chart.js frontend layout (`frontend/index.html`) so a reviewer can inspect the outputs visually without running CLI commands. Specifically, help me structure:
> 1. A 2-chart view for a selected Store × SKU pair showing daily `true_unconstrained_demand` vs. `units_sold` (highlighting stockout-censored days) and `closing_on_hand` vs. `reorder_point_units` and `safety_stock_units`.
> 2. A filterable table for `purchase_recommendation.csv` that displays `closing_on_hand_units + on_order_units = inventory_position_units`, `order_status` badges (`RECOMMENDED`, `CAPACITY_CAPPED`, `HOLD_EXCEPTION`), and the `decision_trace` explanation column.

> **Assistant Response Summary:**
> - Provided the responsive Tailwind CSS grid and Chart.js configuration (`maintainAspectRatio: false`) for rendering the dual time-series charts and the Forecast vs. Naive Baseline comparison bar chart.
> - Built the client-side filter and search table rendering functions (`renderPoTable()` and `renderGroundTruthTable()`) to display the inventory position arithmetic, capacity ceilings, and step-by-step `decision_trace` strings.

### Prompt 4 — Wiring the Frontend Execution Bar to `backend/app_server.py`
> **User Prompt:**
> When I open `frontend/index.html` directly over `file://`, it only displays the initial embedded snapshot. Help me wire a lightweight standard-library `http.server` script (`backend/app_server.py`) with `GET /api/status` and `POST /api/run-pipeline` endpoints so clicking "Execute Pipeline & Recompute Now" in the frontend header triggers my Python backend with the chosen `seed` and `scale` and refreshes all KPIs and tables dynamically.

> **Assistant Response Summary:**
> - Implemented `PipelineRequestHandler` using Python's built-in `http.server.BaseHTTPRequestHandler` to serve `frontend/index.html` at `http://127.0.0.1:8000` and handle `POST /api/run-pipeline` requests by calling `run_generator()` and `run_validation_suite()`.
> - Added an async `fetch('/api/run-pipeline')` handler in the frontend script with a client-side seeded PRNG fallback so the UI updates smoothly both when connected to `backend/app_server.py` and when previewed standalone.
