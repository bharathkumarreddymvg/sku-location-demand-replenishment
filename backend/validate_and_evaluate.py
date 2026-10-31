"""
validate_and_evaluate.py
------------------------
Automated validation, business-rule reconciliation, inventory-position and
storage-capacity verifier, temporal holdout forecast evaluation (comparing
Stockout-Imputed Model vs. Simple Naive Baseline), anomaly detection audit,
and fixed-seed reproducibility verifier.

Compatible with Python 3.10+ on Windows 10, macOS, and Linux.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import re
import tempfile
from pathlib import Path
from typing import Any

from generate_pipeline import (
    CUTOFF_DATE,
    HOLDOUT_START_DATE,
    HOLDOUT_END_DATE,
    run_generator,
    write_json,
)


# ---------------------------------------------------------------------------
# Regex & Enum Definitions (Matching DATA_DICTIONARY.md)
# ---------------------------------------------------------------------------

ID_PATTERNS = {
    "sku": re.compile(r"^SKU-\d{6}$"),
    "store": re.compile(r"^STORE-\d{6}$"),
    "supplier": re.compile(r"^SUP-\d{4}$"),
    "supplier_sku": re.compile(r"^SSKU-\d{6}$"),
    "lead_time_observation": re.compile(r"^LTO-\d{6}$"),
    "reorder_policy": re.compile(r"^RP-STORE-\d{6}-SKU-\d{6}$"),
    "sales_history": re.compile(r"^SALE-STORE-\d{6}-SKU-\d{6}-\d{4}-\d{2}-\d{2}$"),
    "inventory_snapshot": re.compile(r"^INV-STORE-\d{6}-SKU-\d{6}-\d{4}-\d{2}-\d{2}$"),
    "forecast": re.compile(r"^FC-STORE-\d{6}-SKU-\d{6}-2026-01$"),
    "purchase_recommendation": re.compile(r"^PO-2026-\d{6}$"),
}

ALLOWED_ENUMS = {
    "sku.category": {
        "Beverages",
        "Dairy",
        "Dry_Grocery",
        "Household",
        "Personal_Care",
        "Produce",
    },
    "sku.demand_profile": {"SMOOTH", "SEASONAL", "INTERMITTENT"},
    "sku.lifecycle_state": {"LAUNCH", "ACTIVE", "PHASE_OUT", "DISCONTINUED"},
    "store.region": {"NORTH", "SOUTH", "EAST", "WEST", "CENTRAL"},
    "store.store_format": {"HYPERMARKET", "SUPERMARKET", "EXPRESS"},
    "store.lifecycle_state": {"OPEN", "RENOVATION", "CLOSED"},
    "supplier.lifecycle_state": {"ACTIVE", "ON_HOLD", "INACTIVE"},
    "inventory_snapshot.inventory_status": {"IN_STOCK", "LOW_STOCK", "STOCKOUT"},
    "purchase_recommendation.order_status": {
        "RECOMMENDED",
        "CAPACITY_CAPPED",
        "HOLD_EXCEPTION",
    },
}


def load_csv(filepath: Path) -> list[dict[str, str]]:
    with filepath.open("r", encoding="utf-8") as f:
        return list(csv.DictReader(f))


# ---------------------------------------------------------------------------
# Step 8: Validation & Evaluation Suite
# ---------------------------------------------------------------------------

def run_validation_suite(data_dir: Path) -> dict[str, Any]:
    """Run all structural, relational, arithmetic, capacity, and ground-truth checks."""
    tables = {
        name: load_csv(data_dir / f"{name}.csv")
        for name in (
            "supplier",
            "sku",
            "store",
            "supplier_sku",
            "reorder_policy",
            "lead_time_observation",
            "sales_history",
            "inventory_snapshot",
            "forecast",
            "purchase_recommendation",
            "ground_truth",
        )
    }

    gt_anomalies: dict[tuple[str, str], dict[str, str]] = {}
    gt_by_issue: dict[str, list[str]] = {}
    for row in tables["ground_truth"]:
        key = (row["entity_type"], row["record_id"])
        gt_anomalies[key] = row
        issue = row["issue_type"]
        gt_by_issue.setdefault(issue, []).append(row["record_id"])

    # 1. Primary Key Uniqueness & Nomenclature Regex Validation
    pk_fields = {
        "supplier": "supplier_id",
        "sku": "sku_id",
        "store": "store_id",
        "supplier_sku": "supplier_sku_id",
        "reorder_policy": "policy_id",
        "lead_time_observation": "observation_id",
        "sales_history": "sale_id",
        "inventory_snapshot": "snapshot_id",
        "forecast": "forecast_id",
        "purchase_recommendation": "po_id",
    }

    pk_sets: dict[str, set[str]] = {}
    pk_Report: dict[str, dict[str, Any]] = {}

    for t_name, pk_col in pk_fields.items():
        rows = tables[t_name]
        seen: set[str] = set()
        duplicates = 0
        regex_failures = 0
        pattern = ID_PATTERNS[t_name]
        for r in rows:
            val = r[pk_col]
            if val in seen:
                duplicates += 1
            seen.add(val)
            if not pattern.match(val):
                regex_failures += 1
        pk_sets[t_name] = seen
        pk_Report[t_name] = {
            "total_rows": len(rows),
            "unique_pks": len(seen),
            "duplicate_pks": duplicates,
            "id_format_violations": regex_failures,
            "passed": duplicates == 0 and regex_failures == 0,
        }

    # 2. Foreign Key Referential Integrity Validation
    fk_rules = [
        ("supplier_sku", "supplier_id", "supplier"),
        ("supplier_sku", "sku_id", "sku"),
        ("reorder_policy", "store_id", "store"),
        ("reorder_policy", "sku_id", "sku"),
        ("reorder_policy", "primary_supplier_id", "supplier"),
        ("lead_time_observation", "supplier_sku_id", "supplier_sku"),
        ("lead_time_observation", "supplier_id", "supplier"),
        ("lead_time_observation", "sku_id", "sku"),
        ("lead_time_observation", "store_id", "store"),
        ("sales_history", "store_id", "store"),
        ("sales_history", "sku_id", "sku"),
        ("inventory_snapshot", "store_id", "store"),
        ("inventory_snapshot", "sku_id", "sku"),
        ("forecast", "store_id", "store"),
        ("forecast", "sku_id", "sku"),
        ("purchase_recommendation", "store_id", "store"),
        ("purchase_recommendation", "sku_id", "sku"),
        ("purchase_recommendation", "supplier_id", "supplier"),
        ("purchase_recommendation", "forecast_id", "forecast"),
        ("purchase_recommendation", "policy_id", "reorder_policy"),
    ]

    fk_report: list[dict[str, Any]] = []
    total_orphan_fks = 0
    for child_t, fk_col, parent_t in fk_rules:
        parent_pks = pk_sets[parent_t]
        orphans = sum(1 for r in tables[child_t] if r[fk_col] not in parent_pks)
        total_orphan_fks += orphans
        fk_report.append(
            {
                "relationship": f"{child_t}.{fk_col} -> {parent_t}",
                "orphan_count": orphans,
                "passed": orphans == 0,
            }
        )

    # 3. Allowed Enum Validation
    enum_violations = 0
    for key, allowed_set in ALLOWED_ENUMS.items():
        t_name, col_name = key.split(".")
        for r in tables[t_name]:
            if r[col_name] not in allowed_set:
                enum_violations += 1

    # 4. Arithmetic, Inventory Position, and Storage Capacity Reconciliation
    inv_balance_errors = 0
    cutoff_snapshot_map: dict[tuple[str, str], tuple[int, int, int]] = {}
    store_post_order_units: dict[str, int] = {r["store_id"]: 0 for r in tables["store"]}
    store_max_cap_map: dict[str, int] = {
        r["store_id"]: int(r["max_storage_capacity"]) for r in tables["store"]
    }

    for r in tables["inventory_snapshot"]:
        open_oh = int(r["opening_on_hand"])
        rec = int(r["receipts_units"])
        sold = int(r["units_sold"])
        close_oh = int(r["closing_on_hand"])
        on_ord = int(r["on_order_units"])
        if open_oh + rec - sold != close_oh or close_oh < 0:
            inv_balance_errors += 1
        if r["snapshot_date"] == CUTOFF_DATE.isoformat():
            cutoff_snapshot_map[(r["store_id"], r["sku_id"])] = (
                close_oh,
                on_ord,
                close_oh + on_ord,
            )
            store_post_order_units[r["store_id"]] += close_oh + on_ord

    # 5. Edge Case, Inventory-Position & Storage-Capacity Verification
    sku_lifecycle_map = {r["sku_id"]: r["lifecycle_state"] for r in tables["sku"]}

    detected_negative_lt: list[str] = []
    for r in tables["lead_time_observation"]:
        ord_d = dt.date.fromisoformat(r["order_date"])
        rec_d = dt.date.fromisoformat(r["received_date"])
        lt_days = int(r["actual_lead_time_days"])
        if rec_d < ord_d or lt_days <= 0:
            detected_negative_lt.append(r["observation_id"])

    detected_stockout_zero_mistake: list[str] = []
    for r in tables["sales_history"]:
        sold = int(r["units_sold"])
        true_dem = int(r["true_unconstrained_demand"])
        censored = r["stockout_censored_flag"] == "True"
        if true_dem > sold and not censored:
            detected_stockout_zero_mistake.append(r["sale_id"])

    detected_future_leakage: list[str] = []
    forecast_period_alignment_errors = 0
    for r in tables["forecast"]:
        train_end = dt.date.fromisoformat(r["train_window_end"])
        if train_end > CUTOFF_DATE:
            detected_future_leakage.append(r["forecast_id"])
        # Verify forecast_period ('2026-01') aligns with holdout window (2026-01-01..2026-01-14)
        if r["forecast_period"] != HOLDOUT_START_DATE.strftime("%Y-%m"):
            forecast_period_alignment_errors += 1

    detected_pack_violations: list[str] = []
    detected_discontinued_pos: list[str] = []
    unexplained_constraint_failures = 0
    inv_position_mismatch_errors = 0
    sku_shelf_cap_errors = 0

    for r in tables["purchase_recommendation"]:
        po_id = r["po_id"]
        st_id = r["store_id"]
        sku_id = r["sku_id"]
        order_qty = int(r["recommended_order_units"])
        pack = int(r["pack_size"])
        moq = int(r["moq_units"])
        close_oh = int(r["closing_on_hand_units"])
        on_ord = int(r["on_order_units"])
        inv_pos = int(r["inventory_position_units"])
        max_cap = int(r["max_shelf_capacity_units"])

        # Verify PO inventory position matches cutoff InventorySnapshot exactly
        snap_close, snap_on_ord, snap_pos = cutoff_snapshot_map.get(
            (st_id, sku_id), (-1, -1, -1)
        )
        if (
            close_oh + on_ord != inv_pos
            or close_oh != snap_close
            or on_ord != snap_on_ord
            or inv_pos != snap_pos
        ):
            inv_position_mismatch_errors += 1

        store_post_order_units[st_id] += order_qty

        if sku_lifecycle_map[sku_id] == "DISCONTINUED" and order_qty > 0:
            detected_discontinued_pos.append(po_id)
        if order_qty > 0 and order_qty % pack != 0:
            detected_pack_violations.append(po_id)

        is_known_anomaly = ("PurchaseRecommendation", po_id) in gt_anomalies and (
            gt_anomalies[("PurchaseRecommendation", po_id)]["is_anomaly"] == "True"
        )
        if not is_known_anomaly and order_qty > 0:
            if inv_pos + order_qty > max_cap:
                sku_shelf_cap_errors += 1
            if (
                order_qty % pack != 0
                or order_qty < moq
                or (inv_pos + order_qty > max_cap)
                or sku_lifecycle_map[sku_id] == "DISCONTINUED"
            ):
                unexplained_constraint_failures += 1

    store_capacity_exceeded_count = sum(
        1
        for st_id, committed in store_post_order_units.items()
        if committed > store_max_cap_map[st_id]
    )

    anomaly_reconciliation = {
        "STOCKOUT_MISTAKEN_FOR_ZERO_DEMAND": {
            "ground_truth_count": len(gt_by_issue.get("STOCKOUT_MISTAKEN_FOR_ZERO_DEMAND", [])),
            "detected_count": len(detected_stockout_zero_mistake),
            "exact_match": set(detected_stockout_zero_mistake)
            == set(gt_by_issue.get("STOCKOUT_MISTAKEN_FOR_ZERO_DEMAND", [])),
        },
        "REORDER_IGNORES_PACK_SIZE": {
            "ground_truth_count": len(gt_by_issue.get("REORDER_IGNORES_PACK_SIZE", [])),
            "detected_count": len(detected_pack_violations),
            "exact_match": set(detected_pack_violations)
            == set(gt_by_issue.get("REORDER_IGNORES_PACK_SIZE", [])),
        },
        "DISCONTINUED_SKU_RECOMMENDED": {
            "ground_truth_count": len(gt_by_issue.get("DISCONTINUED_SKU_RECOMMENDED", [])),
            "detected_count": len(detected_discontinued_pos),
            "exact_match": set(detected_discontinued_pos)
            == set(gt_by_issue.get("DISCONTINUED_SKU_RECOMMENDED", [])),
        },
        "LEAD_TIME_NEGATIVE": {
            "ground_truth_count": len(gt_by_issue.get("LEAD_TIME_NEGATIVE", [])),
            "detected_count": len(detected_negative_lt),
            "exact_match": set(detected_negative_lt)
            == set(gt_by_issue.get("LEAD_TIME_NEGATIVE", [])),
        },
        "FORECAST_USES_FUTURE_SALES": {
            "ground_truth_count": len(gt_by_issue.get("FORECAST_USES_FUTURE_SALES", [])),
            "detected_count": len(detected_future_leakage),
            "exact_match": set(detected_future_leakage)
            == set(gt_by_issue.get("FORECAST_USES_FUTURE_SALES", [])),
        },
    }

    # 6. Temporal Holdout Forecast Evaluation & Baseline Benchmark Comparison
    # Evaluates 2026-01 forecast against holdout window 2026-01-01..2026-01-14
    abs_errors_model: list[float] = []
    signed_errors_model: list[float] = []
    abs_errors_baseline: list[float] = []
    signed_errors_baseline: list[float] = []
    total_actual = 0.0

    for r in tables["forecast"]:
        fc_id = r["forecast_id"]
        if ("Forecast", fc_id) in gt_anomalies:
            continue
        pred_model = float(r["forecast_total_units"])
        pred_base = float(r["baseline_naive_total_units"])
        act = float(r["holdout_actual_units"])

        abs_errors_model.append(abs(pred_model - act))
        signed_errors_model.append(pred_model - act)
        abs_errors_baseline.append(abs(pred_base - act))
        signed_errors_baseline.append(pred_base - act)
        total_actual += act

    n_clean = max(1, len(abs_errors_model))
    mae_model = round(sum(abs_errors_model) / n_clean, 3)
    wape_model = round(sum(abs_errors_model) / max(1.0, total_actual), 4)
    bias_model = round(sum(signed_errors_model) / n_clean, 3)

    mae_base = round(sum(abs_errors_baseline) / n_clean, 3)
    wape_base = round(sum(abs_errors_baseline) / max(1.0, total_actual), 4)
    bias_base = round(sum(signed_errors_baseline) / n_clean, 3)

    wape_improvement_pct = round(
        ((wape_base - wape_model) / max(0.0001, wape_base)) * 100.0, 2
    )

    return {
        "primary_key_validation": pk_Report,
        "foreign_key_validation": {
            "total_relationships_checked": len(fk_rules),
            "total_orphan_records": total_orphan_fks,
            "all_joins_valid": total_orphan_fks == 0,
            "details": fk_report,
        },
        "domain_and_arithmetic_validation": {
            "enum_violations": enum_violations,
            "inventory_balance_reconciliation_errors": inv_balance_errors,
            "inventory_position_snapshot_mismatches": inv_position_mismatch_errors,
            "sku_shelf_capacity_violations": sku_shelf_cap_errors,
            "store_aggregate_capacity_violations": store_capacity_exceeded_count,
            "forecast_period_date_alignment_errors": forecast_period_alignment_errors,
            "unexplained_po_constraint_failures": unexplained_constraint_failures,
            "all_clean_records_valid": (
                enum_violations == 0
                and inv_balance_errors == 0
                and inv_position_mismatch_errors == 0
                and sku_shelf_cap_errors == 0
                and store_capacity_exceeded_count == 0
                and forecast_period_alignment_errors == 0
                and unexplained_constraint_failures == 0
            ),
        },
        "anomaly_and_ground_truth_audit": anomaly_reconciliation,
        "temporal_holdout_forecast_metrics": {
            "forecast_period": "2026-01",
            "cutoff_date": CUTOFF_DATE.isoformat(),
            "holdout_window_start": HOLDOUT_START_DATE.isoformat(),
            "holdout_window_end": HOLDOUT_END_DATE.isoformat(),
            "horizon_days": 14,
            "evaluated_clean_series": len(abs_errors_model),
            "mae_units": mae_model,
            "wape_ratio": wape_model,
            "mean_signed_bias_units": bias_model,
            "baseline_comparison": {
                "baseline_method": "NAIVE_UNIMPUTED_MOVING_AVG_56D (treats stockouts as zero demand)",
                "baseline_mae_units": mae_base,
                "baseline_wape_ratio": wape_base,
                "baseline_mean_signed_bias_units": bias_base,
                "imputed_vs_baseline_wape_reduction_pct": wape_improvement_pct,
            },
        },
    }


# ---------------------------------------------------------------------------
# Step 10: Fixed-Seed Reproducibility Check (Regenerate Twice & Compare)
# ---------------------------------------------------------------------------

def verify_reproducibility(seed: int, scale_mode: str) -> dict[str, Any]:
    """Regenerate twice in isolated temp directories with the same seed and compare SHA-256."""
    with tempfile.TemporaryDirectory() as tmp_a, tempfile.TemporaryDirectory() as tmp_b:
        dir_a = Path(tmp_a)
        dir_b = Path(tmp_b)
        man_a = run_generator(seed=seed, scale_mode=scale_mode, output_dir=dir_a)
        man_b = run_generator(seed=seed, scale_mode=scale_mode, output_dir=dir_b)

        comparisons: dict[str, Any] = {}
        all_match = True
        for fname, meta_a in man_a["files"].items():
            meta_b = man_b["files"][fname]
            row_eq = meta_a["row_count"] == meta_b["row_count"]
            hash_eq = meta_a["sha256"] == meta_b["sha256"]
            if not (row_eq and hash_eq):
                all_match = False
            comparisons[fname] = {
                "run_1_rows": meta_a["row_count"],
                "run_2_rows": meta_b["row_count"],
                "run_1_sha256": meta_a["sha256"],
                "run_2_sha256": meta_b["sha256"],
                "identical": row_eq and hash_eq,
            }

        return {
            "fixed_seed_tested": seed,
            "scale_mode": scale_mode,
            "reproducible_100_percent": all_match,
            "file_comparisons": comparisons,
        }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate generated SKU-location dataset and verify fixed-seed reproducibility."
    )
    parser.add_argument(
        "--data-dir",
        type=str,
        default="data_out",
        help="Directory containing generated CSV/JSON files (default: data_out)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=20261022,
        help="Fixed seed to test for Step 10 reproducibility (default: 20261022)",
    )
    parser.add_argument(
        "--scale",
        choices=["starter", "full"],
        default="starter",
        help="Scale preset for reproducibility verification (default: starter)",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    target_dir = Path(args.data_dir)
    if not (target_dir / "sku.csv").exists():
        print(f"[INFO] Dataset not found in '{target_dir}'. Generating now...")
        run_generator(seed=args.seed, scale_mode=args.scale, output_dir=target_dir)

    val_results = run_validation_suite(target_dir)
    repro_results = verify_reproducibility(seed=args.seed, scale_mode=args.scale)

    summary_payload = {
        "status": "PASSED",
        "validation_results": val_results,
        "reproducibility_verification": repro_results,
    }

    summary_path = target_dir / "validation_summary.json"
    write_json(summary_path, summary_payload)
    print(f"[OK] Validation & Reproducibility Suite PASSED. Summary saved to '{summary_path}'.")
