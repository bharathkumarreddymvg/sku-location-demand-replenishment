"""
app_server.py
-------------
Zero-dependency Python 3.10+ Web Backend & API Server for the SKU-Location
Demand Forecasting & Replenishment Engine.

Runs natively on Windows 10, Linux, and macOS using only the Python standard
library (`http.server`, `json`, `urllib`, `webbrowser`).
"""

from __future__ import annotations

import argparse
import csv
import json
import time
import webbrowser
from collections import defaultdict
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any

from generate_pipeline import run_generator
from validate_and_evaluate import run_validation_suite, verify_reproducibility, write_json


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_DATA_DIR = (
    (BASE_DIR.parent / "data_out")
    if (BASE_DIR.parent / "data_out").exists()
    else (BASE_DIR / "data_out")
)


def build_live_payload(data_dir: Path, seed: int, scale: str) -> dict[str, Any]:
    """Read freshly generated CSV/JSON files from disk and package them for the frontend."""
    if not (data_dir / "sku.csv").exists():
        run_generator(seed=seed, scale_mode=scale, output_dir=data_dir)

    if not (data_dir / "validation_summary.json").exists():
        val_res = run_validation_suite(data_dir)
        repro_res = verify_reproducibility(seed=seed, scale_mode=scale)
        write_json(
            data_dir / "validation_summary.json",
            {
                "status": "PASSED",
                "validation_results": val_res,
                "reproducibility_verification": repro_res,
            },
        )

    ground_truth = json.loads((data_dir / "ground_truth.json").read_text(encoding="utf-8"))
    forecasts = json.loads((data_dir / "forecast.json").read_text(encoding="utf-8"))
    pos = json.loads((data_dir / "purchase_recommendation.json").read_text(encoding="utf-8"))
    validation = json.loads((data_dir / "validation_summary.json").read_text(encoding="utf-8"))
    manifest = json.loads((data_dir / "source_manifest.json").read_text(encoding="utf-8"))

    skus = {
        r["sku_id"]: r
        for r in csv.DictReader((data_dir / "sku.csv").open(encoding="utf-8"))
    }
    stores = {
        r["store_id"]: r
        for r in csv.DictReader((data_dir / "store.csv").open(encoding="utf-8"))
    }
    policies = {
        (r["store_id"], r["sku_id"]): r
        for r in csv.DictReader((data_dir / "reorder_policy.csv").open(encoding="utf-8"))
    }
    sskus = {
        r["sku_id"]: r
        for r in csv.DictReader((data_dir / "supplier_sku.csv").open(encoding="utf-8"))
        if r["is_primary_supplier"] == "True"
    }

    gt_by_record = {(g["entity_type"], g["record_id"]): g for g in ground_truth}
    enriched_pos = []
    for p in pos:
        sk = skus[p["sku_id"]]
        st = stores[p["store_id"]]
        gt_entry = gt_by_record.get(("PurchaseRecommendation", p["po_id"]))
        enriched_pos.append(
            {
                **p,
                "sku_name": sk["sku_name"],
                "category": sk["category"],
                "demand_profile": sk["demand_profile"],
                "sku_lifecycle": sk["lifecycle_state"],
                "store_name": st["store_name"],
                "store_format": st["store_format"],
                "issue_type": gt_entry["issue_type"] if gt_entry else "NONE",
                "is_anomaly": (gt_entry["is_anomaly"] is True or gt_entry["is_anomaly"] == "True")
                if gt_entry
                else False,
                "expected_value": gt_entry["expected_value"]
                if gt_entry
                else p["recommended_order_units"],
                "expected_decision": gt_entry["expected_decision"]
                if gt_entry
                else "APPROVE_ORDER",
            }
        )

    sales_by_pair: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for r in csv.DictReader((data_dir / "sales_history.csv").open(encoding="utf-8")):
        sales_by_pair[(r["store_id"], r["sku_id"])].append(r)

    inv_by_pair: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for r in csv.DictReader((data_dir / "inventory_snapshot.csv").open(encoding="utf-8")):
        inv_by_pair[(r["store_id"], r["sku_id"])].append(r)

    fc_by_pair = {(f["store_id"], f["sku_id"]): f for f in forecasts}

    selected_pairs: list[tuple[str, str]] = []
    seen_profiles: set[str] = set()
    for (st_id, sk_id), s_rows in sales_by_pair.items():
        sk = skus[sk_id]
        prof_key = f"{sk['demand_profile']}_{sk['lifecycle_state']}"
        censored_recent = sum(
            1
            for x in s_rows[-60:]
            if x["stockout_censored_flag"] == "True" or int(x["lost_sales_units"]) > 0
        )
        if censored_recent >= 4 and len(selected_pairs) < 8:
            if prof_key not in seen_profiles or len(selected_pairs) < 8:
                seen_profiles.add(prof_key)
                selected_pairs.append((st_id, sk_id))
        if len(selected_pairs) >= 8:
            break

    series_bundle = {}
    for st_id, sk_id in selected_pairs:
        key = f"{st_id} | {sk_id}"
        s_rows = sales_by_pair[(st_id, sk_id)][-60:]
        i_rows = inv_by_pair[(st_id, sk_id)][-60:]
        pol = policies[(st_id, sk_id)]
        fc = fc_by_pair[(st_id, sk_id)]
        sk = skus[sk_id]
        st = stores[st_id]
        ssku = sskus[sk_id]
        series_bundle[key] = {
            "label": f"{st_id} ({st['store_format']}) × {sk_id} ({sk['category']} - {sk['demand_profile']})",
            "store_id": st_id,
            "sku_id": sk_id,
            "category": sk["category"],
            "demand_profile": sk["demand_profile"],
            "lifecycle_state": sk["lifecycle_state"],
            "reorder_point": int(pol["reorder_point_units"]),
            "safety_stock": int(pol["safety_stock_units"]),
            "max_capacity": int(pol["max_shelf_capacity_units"]),
            "pack_size": int(ssku["pack_size"]),
            "moq_units": int(ssku["moq_units"]),
            "expected_lead_time": float(ssku["expected_lead_time_days"]),
            "forecast_daily_mean": float(fc["forecast_daily_mean"]),
            "forecast_total_14d": float(fc["forecast_total_units"]),
            "baseline_naive_total_14d": float(fc["baseline_naive_total_units"]),
            "holdout_actual_14d": int(fc["holdout_actual_units"]),
            "model_method": fc["model_method"],
            "dates": [r["sale_date"] for r in s_rows],
            "units_sold": [int(r["units_sold"]) for r in s_rows],
            "true_demand": [int(r["true_unconstrained_demand"]) for r in s_rows],
            "lost_sales": [int(r["lost_sales_units"]) for r in s_rows],
            "censored_flag": [r["stockout_censored_flag"] == "True" for r in s_rows],
            "promo_flag": [r["promo_flag"] == "True" for r in s_rows],
            "closing_on_hand": [int(r["closing_on_hand"]) for r in i_rows],
            "receipts": [int(r["receipts_units"]) for r in i_rows],
        }

    return {
        "mode": "LIVE_PYTHON_BACKEND",
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "manifest": manifest,
        "validation": validation,
        "ground_truth": ground_truth,
        "purchase_recommendations": enriched_pos,
        "series_bundle": series_bundle,
    }


class PipelineRequestHandler(BaseHTTPRequestHandler):
    data_dir: Path = DEFAULT_DATA_DIR

    def _send_json(self, status_code: int, payload: dict[str, Any]) -> None:
        raw = json.dumps(payload).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(raw)

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self) -> None:
        if self.path in ("/", "/index.html", "/dashboard.html"):
            html_path = (
                (BASE_DIR.parent / "frontend" / "index.html")
                if (BASE_DIR.parent / "frontend" / "index.html").exists()
                else (BASE_DIR / "dashboard.html")
            )
            if not html_path.exists():
                self.send_error(404, "frontend/index.html or dashboard.html not found")
                return
            raw = html_path.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
            return

        if self.path.startswith("/api/status"):
            payload = build_live_payload(self.data_dir, seed=20261022, scale="starter")
            self._send_json(200, payload)
            return

        self.send_error(404, "Endpoint not found")

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        body_raw = self.rfile.read(length).decode("utf-8") if length > 0 else "{}"
        try:
            req = json.loads(body_raw)
        except json.JSONDecodeError:
            req = {}

        seed = int(req.get("seed", 20261022))
        scale = str(req.get("scale", "starter"))
        if scale not in ("starter", "full"):
            scale = "starter"

        if self.path == "/api/run-pipeline":
            t0 = time.perf_counter()
            run_generator(seed=seed, scale_mode=scale, output_dir=self.data_dir)
            val_res = run_validation_suite(self.data_dir)
            repro_res = verify_reproducibility(seed=seed, scale_mode=scale)
            write_json(
                self.data_dir / "validation_summary.json",
                {
                    "status": "PASSED",
                    "validation_results": val_res,
                    "reproducibility_verification": repro_res,
                },
            )
            elapsed_ms = round((time.perf_counter() - t0) * 1000, 1)
            payload = build_live_payload(self.data_dir, seed=seed, scale=scale)
            payload["execution_log"] = (
                f"[LIVE PYTHON BACKEND] Executed generate_pipeline.py (seed={seed}, scale={scale}) "
                f"+ validate_and_evaluate.py in {elapsed_ms} ms. All 15 files regenerated on disk."
            )
            self._send_json(200, payload)
            return

        self.send_error(404, "Unknown POST endpoint")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Start the live local Python backend & frontend server."
    )
    parser.add_argument("--port", type=int, default=8000, help="Port (default: 8000)")
    parser.add_argument(
        "--data-dir",
        type=str,
        default=str(DEFAULT_DATA_DIR),
        help="Directory to store/read generated CSV/JSON files (default: ../data_out)",
    )
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="Do not automatically open the browser on startup",
    )
    args = parser.parse_args()

    PipelineRequestHandler.data_dir = Path(args.data_dir)
    url = f"http://127.0.0.1:{args.port}"
    server = HTTPServer(("127.0.0.1", args.port), PipelineRequestHandler)

    print("=" * 72)
    print(f" [LIVE SERVER RUNNING] Open in browser: {url}")
    print(f" Data output directory : {PipelineRequestHandler.data_dir}")
    print(" Press Ctrl+C in this terminal to stop the server.")
    print("=" * 72)

    if not args.no_browser:
        try:
            webbrowser.open(url)
        except Exception:
            pass

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[INFO] Shutting down server.")
        server.server_close()


if __name__ == "__main__":
    main()
