"""
generate_pipeline.py
--------------------
End-to-end synthetic data generator, demand forecaster, and replenishment
recommendation engine for SKU-location inventory planning.

Compatible with Python 3.10+ on Windows 10, macOS, and Linux.
Uses only the Python standard library so it runs out of the box without
external binary dependencies.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import math
import random
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Configuration & Constants
# ---------------------------------------------------------------------------

CATEGORIES = [
    "Beverages",
    "Dairy",
    "Dry_Grocery",
    "Household",
    "Personal_Care",
    "Produce",
]

DEMAND_PROFILES = ["SMOOTH", "SEASONAL", "INTERMITTENT"]
REGIONS = ["NORTH", "SOUTH", "EAST", "WEST", "CENTRAL"]
STORE_FORMATS = ["HYPERMARKET", "SUPERMARKET", "EXPRESS"]
COUNTRIES = ["US", "CA", "MX", "IN", "DE"]
PACK_SIZES = [6, 12, 24, 48]

SERVICE_LEVEL_Z = {
    0.90: 1.2816,
    0.95: 1.6449,
    0.98: 2.0537,
}

# 365-day simulation window: 2025-01-16 through 2026-01-15
# - Training window (351 days): 2025-01-16 through 2025-12-31 (CUTOFF_DATE)
# - Holdout evaluation window (14 days, forecast_period = '2026-01'): 2026-01-01 through 2026-01-14
SIM_START_DATE = dt.date(2025, 1, 16)
CUTOFF_DATE = dt.date(2025, 12, 31)      # Day 350 (351 training days: index 0..350)
HOLDOUT_START_DATE = dt.date(2026, 1, 1) # Day 351
HOLDOUT_END_DATE = dt.date(2026, 1, 14)  # Day 364 (14 holdout days: index 351..364)
SIM_END_DATE = dt.date(2026, 1, 14)


@dataclass
class ScaleConfig:
    mode: str
    num_skus: int
    num_stores: int
    num_suppliers: int
    num_days: int
    active_matrix_pairs: int


SCALE_PRESETS = {
    "starter": ScaleConfig(
        mode="starter",
        num_skus=2000,
        num_stores=100,
        num_suppliers=40,
        num_days=365,
        active_matrix_pairs=300,
    ),
    "full": ScaleConfig(
        mode="full",
        num_skus=2000,
        num_stores=100,
        num_suppliers=40,
        num_days=365,
        active_matrix_pairs=2500,
    ),
}


# ---------------------------------------------------------------------------
# Helper Functions
# ---------------------------------------------------------------------------

def sample_poisson(rng: random.Random, lam: float) -> int:
    """Knuth's algorithm for Poisson sampling using standard library random."""
    if lam <= 0.0:
        return 0
    if lam > 30.0:
        val = rng.gauss(lam, math.sqrt(lam))
        return max(0, int(round(val)))
    l_bound = math.exp(-lam)
    k = 0
    p = 1.0
    while p > l_bound:
        k += 1
        p *= rng.random()
    return k - 1


def compute_sha256(filepath: Path) -> str:
    """Compute SHA-256 hex digest of a file across platforms."""
    hasher = hashlib.sha256()
    with filepath.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def write_csv(filepath: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    """Write rows deterministically with LF line endings for cross-OS checksum stability."""
    filepath.parent.mkdir(parents=True, exist_ok=True)
    with filepath.open("w", encoding="utf-8", newline="\n") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def write_json(filepath: Path, payload: Any) -> None:
    """Write JSON with deterministic key ordering and LF line endings."""
    filepath.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2, sort_keys=False)
    with filepath.open("w", encoding="utf-8", newline="\n") as f:
        f.write(text + "\n")


# ---------------------------------------------------------------------------
# Step 1 & 2: Master Entity Generation
# ---------------------------------------------------------------------------

def generate_master_entities(
    rng: random.Random, cfg: ScaleConfig
) -> tuple[
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
]:
    """Generate Supplier, SKU, Store, and SupplierSKU master tables."""
    # 1. Suppliers
    suppliers: list[dict[str, Any]] = []
    for i in range(1, cfg.num_suppliers + 1):
        sup_id = f"SUP-{i:04d}"
        country = COUNTRIES[(i - 1) % len(COUNTRIES)]
        rel_score = round(rng.uniform(0.78, 0.99), 3)
        state = "ACTIVE" if i <= int(cfg.num_suppliers * 0.92) else "ON_HOLD"
        suppliers.append(
            {
                "supplier_id": sup_id,
                "supplier_name": f"Global_Vendor_{country}_{i:04d}",
                "country_code": country,
                "reliability_score": rel_score,
                "lifecycle_state": state,
                "effective_date": "2023-01-15",
            }
        )

    # 2. SKUs (2,000 SKUs)
    skus: list[dict[str, Any]] = []
    for i in range(1, cfg.num_skus + 1):
        sku_id = f"SKU-{i:06d}"
        cat = CATEGORIES[(i - 1) % len(CATEGORIES)]
        r_prof = rng.random()
        if r_prof < 0.55:
            profile = "SMOOTH"
        elif r_prof < 0.80:
            profile = "SEASONAL"
        else:
            profile = "INTERMITTENT"

        cost = round(rng.uniform(1.50, 45.00), 2)
        margin = rng.uniform(1.25, 1.85)
        price = round(cost * margin, 2)

        if i <= 40:
            lifecycle = "DISCONTINUED"
            start_date = "2023-06-01"
            end_date = "2025-10-31"
        elif i <= 120:
            lifecycle = "LAUNCH"
            launch_offset = rng.randint(60, 180)
            start_date = (SIM_START_DATE + dt.timedelta(days=launch_offset)).isoformat()
            end_date = ""
        elif i <= 160:
            lifecycle = "PHASE_OUT"
            start_date = "2024-01-01"
            end_date = "2026-03-31"
        else:
            lifecycle = "ACTIVE"
            start_date = "2024-01-01"
            end_date = ""

        skus.append(
            {
                "sku_id": sku_id,
                "sku_name": f"{cat}_Item_{i:06d}",
                "category": cat,
                "demand_profile": profile,
                "unit_cost": cost,
                "unit_price": price,
                "lifecycle_state": lifecycle,
                "effective_start_date": start_date,
                "effective_end_date": end_date,
            }
        )

    # 3. Stores (100 Stores)
    stores: list[dict[str, Any]] = []
    for i in range(1, cfg.num_stores + 1):
        store_id = f"STORE-{i:06d}"
        region = REGIONS[(i - 1) % len(REGIONS)]
        if i % 5 == 0:
            fmt = "HYPERMARKET"
            cap = rng.randint(15000, 30000)
        elif i % 3 == 0:
            fmt = "EXPRESS"
            cap = rng.randint(2500, 5000)
        else:
            fmt = "SUPERMARKET"
            cap = rng.randint(7000, 14000)

        stores.append(
            {
                "store_id": store_id,
                "store_name": f"{region}_{fmt.title()}_{i:03d}",
                "region": region,
                "store_format": fmt,
                "max_storage_capacity": cap,
                "lifecycle_state": "OPEN" if i <= 98 else "RENOVATION",
                "opened_date": f"202{rng.randint(0, 4)}-0{rng.randint(1, 9)}-15",
            }
        )

    # 4. SupplierSKU Bridge Table (N:M between Supplier and SKU)
    active_suppliers = [s for s in suppliers if s["lifecycle_state"] == "ACTIVE"]
    supplier_skus: list[dict[str, Any]] = []
    ssku_counter = 1

    for sku in skus:
        primary_sup = rng.choice(active_suppliers)
        pack = rng.choice(PACK_SIZES)
        moq_mult = rng.choice([2, 3, 4, 5])
        moq = pack * moq_mult
        mean_lt = round(rng.uniform(4.0, 14.0), 2)
        std_lt = round(mean_lt * rng.uniform(0.15, 0.35), 2)

        supplier_skus.append(
            {
                "supplier_sku_id": f"SSKU-{ssku_counter:06d}",
                "supplier_id": primary_sup["supplier_id"],
                "sku_id": sku["sku_id"],
                "is_primary_supplier": True,
                "pack_size": pack,
                "moq_units": moq,
                "expected_lead_time_days": mean_lt,
                "lead_time_std_days": std_lt,
                "effective_start_date": sku["effective_start_date"],
            }
        )
        ssku_counter += 1

        if rng.random() < 0.25:
            sec_candidates = [
                s for s in active_suppliers if s["supplier_id"] != primary_sup["supplier_id"]
            ]
            sec_sup = rng.choice(sec_candidates)
            sec_pack = rng.choice(PACK_SIZES)
            supplier_skus.append(
                {
                    "supplier_sku_id": f"SSKU-{ssku_counter:06d}",
                    "supplier_id": sec_sup["supplier_id"],
                    "sku_id": sku["sku_id"],
                    "is_primary_supplier": False,
                    "pack_size": sec_pack,
                    "moq_units": sec_pack * rng.choice([2, 4]),
                    "expected_lead_time_days": round(mean_lt * 1.15, 2),
                    "lead_time_std_days": round(std_lt * 1.20, 2),
                    "effective_start_date": sku["effective_start_date"],
                }
            )
            ssku_counter += 1

    return suppliers, skus, stores, supplier_skus


# ---------------------------------------------------------------------------
# Step 3, 4, 5, 6: Matrix Simulation, Forecasting, Replenishment & Anomalies
# ---------------------------------------------------------------------------

def run_simulation_and_planning(
    rng: random.Random,
    cfg: ScaleConfig,
    suppliers: list[dict[str, Any]],
    skus: list[dict[str, Any]],
    stores: list[dict[str, Any]],
    supplier_skus: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    """
    Simulate 365 days of daily sales and inventory snapshots (2025-01-16 to
    2026-01-14), record lead time observations, compute temporal holdout
    forecasts at cutoff 2025-12-31 for period 2026-01 (evaluated against
    2026-01-01..2026-01-14 alongside a naive unimputed baseline), apply reorder
    policies, generate purchase recommendations with decision traces, and
    inject documented ground-truth anomalies.
    """
    sku_map = {s["sku_id"]: s for s in skus}
    store_map = {st["store_id"]: st for st in stores}
    primary_ssku_by_sku = {
        row["sku_id"]: row for row in supplier_skus if row["is_primary_supplier"]
    }

    open_stores = [st for st in stores if st["lifecycle_state"] == "OPEN"]
    eligible_skus = (
        skus[120:420]   # ACTIVE & PHASE_OUT
        + skus[40:80]   # LAUNCH SKUs
        + skus[0:15]    # DISCONTINUED SKUs (for lifecycle/edge case coverage)
    )

    matrix_pairs: list[tuple[str, str]] = []
    seen_pairs: set[tuple[str, str]] = set()
    while len(matrix_pairs) < cfg.active_matrix_pairs:
        st = rng.choice(open_stores)
        sk = rng.choice(eligible_skus)
        pair = (st["store_id"], sk["sku_id"])
        if pair not in seen_pairs:
            seen_pairs.add(pair)
            matrix_pairs.append(pair)

    matrix_pairs.sort()

    sales_history: list[dict[str, Any]] = []
    inventory_snapshots: list[dict[str, Any]] = []
    lead_time_observations: list[dict[str, Any]] = []
    reorder_policies: list[dict[str, Any]] = []
    forecasts: list[dict[str, Any]] = []
    purchase_recommendations: list[dict[str, Any]] = []
    ground_truth: list[dict[str, Any]] = []

    lto_counter = 1
    po_counter = 1
    gt_counter = 1

    injected_counts = {
        "STOCKOUT_MISTAKEN_FOR_ZERO_DEMAND": 0,
        "REORDER_IGNORES_PACK_SIZE": 0,
        "DISCONTINUED_SKU_RECOMMENDED": 0,
        "LEAD_TIME_NEGATIVE": 0,
        "FORECAST_USES_FUTURE_SALES": 0,
        "CAPACITY_CONSTRAINED_ORDER": 0,
    }

    store_committed_units: dict[str, int] = {st["store_id"]: 0 for st in stores}
    pending_po_candidates: list[dict[str, Any]] = []

    for pair_idx, (store_id, sku_id) in enumerate(matrix_pairs):
        sku = sku_map[sku_id]
        store = store_map[store_id]
        ssku = primary_ssku_by_sku[sku_id]
        supplier_id = ssku["supplier_id"]
        pack_size = int(ssku["pack_size"])
        moq_units = int(ssku["moq_units"])
        mean_lt = float(ssku["expected_lead_time_days"])
        std_lt = float(ssku["lead_time_std_days"])

        fmt_mult = 1.6 if store["store_format"] == "HYPERMARKET" else (
            1.0 if store["store_format"] == "SUPERMARKET" else 0.55
        )
        base_rate = rng.uniform(4.5, 16.0) * fmt_mult
        if sku["demand_profile"] == "INTERMITTENT":
            base_rate = rng.uniform(1.2, 4.0) * fmt_mult

        sl_target = rng.choice([0.90, 0.95, 0.98])
        z_val = SERVICE_LEVEL_Z[sl_target]
        est_sigma_d = max(1.0, base_rate * 0.35)

        ss_variance = (mean_lt * (est_sigma_d ** 2)) + ((base_rate ** 2) * (std_lt ** 2))
        safety_stock = int(math.ceil(z_val * math.sqrt(ss_variance)))
        reorder_point = int(math.ceil(base_rate * mean_lt)) + safety_stock

        if pair_idx % 12 == 0:
            max_shelf_cap = min(
                int(store["max_storage_capacity"]),
                reorder_point + int(max(moq_units, pack_size * 2)),
            )
        else:
            max_shelf_cap = min(
                int(store["max_storage_capacity"]),
                reorder_point + int(max(moq_units * 3, round(base_rate * 28))),
            )

        policy_id = f"RP-{store_id}-{sku_id}"
        reorder_policies.append(
            {
                "policy_id": policy_id,
                "store_id": store_id,
                "sku_id": sku_id,
                "primary_supplier_id": supplier_id,
                "service_level_target": sl_target,
                "z_score": z_val,
                "safety_stock_units": safety_stock,
                "reorder_point_units": reorder_point,
                "max_shelf_capacity_units": max_shelf_cap,
                "review_cycle_days": 14,
            }
        )

        eff_start = dt.date.fromisoformat(sku["effective_start_date"])
        eff_end = (
            dt.date.fromisoformat(sku["effective_end_date"])
            if sku["effective_end_date"]
            else dt.date(2099, 12, 31)
        )

        current_on_hand = reorder_point + moq_units if eff_start <= SIM_START_DATE else 0
        in_transit: list[tuple[dt.date, int, dt.date]] = []

        pair_sales_rows: list[dict[str, Any]] = []
        cutoff_closing_oh = 0
        cutoff_on_order = 0
        cutoff_inventory_pos = 0

        for day_offset in range(cfg.num_days):
            cur_date = SIM_START_DATE + dt.timedelta(days=day_offset)
            date_str = cur_date.isoformat()
            is_active_day = eff_start <= cur_date <= eff_end

            # 1. Receive in-transit orders arriving today
            arriving_today = [o for o in in_transit if o[0] == cur_date]
            in_transit = [o for o in in_transit if o[0] != cur_date]
            receipts_today = sum(o[1] for o in arriving_today)

            if cur_date == eff_start and eff_start > SIM_START_DATE:
                receipts_today += reorder_point + moq_units

            opening_oh = current_on_hand
            available_stock = opening_oh + receipts_today

            for arr_date, _qty, ord_date in arriving_today:
                actual_lt = (arr_date - ord_date).days
                delay = max(0, actual_lt - int(round(mean_lt)))
                obs_id = f"LTO-{lto_counter:06d}"
                lto_counter += 1

                if (
                    injected_counts["LEAD_TIME_NEGATIVE"] < 8
                    and pair_idx >= 5
                    and day_offset > 120
                    and lto_counter % 45 == 0
                ):
                    corrupted_recv = ord_date - dt.timedelta(days=3)
                    corrupted_lt = -3
                    lead_time_observations.append(
                        {
                            "observation_id": obs_id,
                            "supplier_sku_id": ssku["supplier_sku_id"],
                            "supplier_id": supplier_id,
                            "sku_id": sku_id,
                            "store_id": store_id,
                            "order_date": ord_date.isoformat(),
                            "received_date": corrupted_recv.isoformat(),
                            "actual_lead_time_days": corrupted_lt,
                            "delay_days": 0,
                        }
                    )
                    ground_truth.append(
                        {
                            "ground_truth_id": f"GT-{gt_counter:06d}",
                            "entity_type": "LeadTimeObservation",
                            "record_id": obs_id,
                            "issue_type": "LEAD_TIME_NEGATIVE",
                            "is_anomaly": True,
                            "expected_decision": "REJECT_INVALID_LEAD_TIME",
                            "expected_value": float(actual_lt),
                            "observed_value": float(corrupted_lt),
                            "rule_reference": "Rule 5 & 8: received_date must be >= order_date and actual_lead_time_days > 0",
                        }
                    )
                    gt_counter += 1
                    injected_counts["LEAD_TIME_NEGATIVE"] += 1
                else:
                    lead_time_observations.append(
                        {
                            "observation_id": obs_id,
                            "supplier_sku_id": ssku["supplier_sku_id"],
                            "supplier_id": supplier_id,
                            "sku_id": sku_id,
                            "store_id": store_id,
                            "order_date": ord_date.isoformat(),
                            "received_date": arr_date.isoformat(),
                            "actual_lead_time_days": actual_lt,
                            "delay_days": delay,
                        }
                    )

            # 2. Generate Daily Demand
            if not is_active_day:
                true_demand = 0
                promo_flag = False
                discount_pct = 0.0
            else:
                dow_mult = 1.22 if cur_date.weekday() in (4, 5, 6) else 0.92
                if sku["demand_profile"] == "SEASONAL":
                    season_mult = 1.0 + 0.55 * math.sin(
                        2.0 * math.pi * (day_offset - 60) / 365.0
                    )
                else:
                    season_mult = 1.0 + 0.12 * math.sin(
                        2.0 * math.pi * day_offset / 365.0
                    )

                promo_flag = rng.random() < 0.08
                discount_pct = round(rng.choice([0.10, 0.15, 0.20, 0.25]), 2) if promo_flag else 0.0
                promo_lift = 1.0 + (discount_pct * 2.4) if promo_flag else 1.0

                lam = base_rate * dow_mult * season_mult * promo_lift
                if sku["demand_profile"] == "INTERMITTENT":
                    if rng.random() < 0.65:
                        true_demand = 0
                    else:
                        true_demand = sample_poisson(rng, lam * 2.2)
                else:
                    true_demand = sample_poisson(rng, lam)

            # 3. Fulfill sales from available stock
            units_sold = min(available_stock, true_demand)
            lost_sales = true_demand - units_sold
            closing_oh = available_stock - units_sold
            current_on_hand = closing_oh

            stockout_censored = lost_sales > 0
            sale_id = f"SALE-{store_id}-{sku_id}-{date_str}"

            if (
                stockout_censored
                and units_sold == 0
                and true_demand > 0
                and injected_counts["STOCKOUT_MISTAKEN_FOR_ZERO_DEMAND"] < 15
                and day_offset < 340
            ):
                recorded_censored_flag = False
                ground_truth.append(
                    {
                        "ground_truth_id": f"GT-{gt_counter:06d}",
                        "entity_type": "SalesHistory",
                        "record_id": sale_id,
                        "issue_type": "STOCKOUT_MISTAKEN_FOR_ZERO_DEMAND",
                        "is_anomaly": True,
                        "expected_decision": "IMPUTE_CENSORED_DEMAND",
                        "expected_value": float(true_demand),
                        "observed_value": 0.0,
                        "rule_reference": "Rule 3 & 5: Record stockouts separately from zero demand; do not mistake zero-inventory days for zero true demand",
                    }
                )
                gt_counter += 1
                injected_counts["STOCKOUT_MISTAKEN_FOR_ZERO_DEMAND"] += 1
            else:
                recorded_censored_flag = stockout_censored

            gross_rev = round(units_sold * float(sku["unit_price"]) * (1.0 - discount_pct), 2)

            sale_row = {
                "sale_id": sale_id,
                "store_id": store_id,
                "sku_id": sku_id,
                "sale_date": date_str,
                "units_sold": units_sold,
                "true_unconstrained_demand": true_demand,
                "lost_sales_units": lost_sales,
                "promo_flag": promo_flag,
                "discount_pct": discount_pct,
                "stockout_censored_flag": recorded_censored_flag,
                "gross_revenue": gross_rev,
            }
            sales_history.append(sale_row)
            pair_sales_rows.append(sale_row)

            # 4. Replenishment trigger during daily simulation
            on_order_qty = sum(o[1] for o in in_transit)
            inv_position = closing_oh + on_order_qty

            if (
                cur_date != CUTOFF_DATE
                and is_active_day
                and inv_position <= reorder_point
                and len(in_transit) == 0
            ):
                needed = max(moq_units, (reorder_point + moq_units) - inv_position)
                order_qty = int(math.ceil(needed / pack_size) * pack_size)
                if inv_position + order_qty > max_shelf_cap:
                    order_qty = max(
                        0,
                        int(math.floor((max_shelf_cap - inv_position) / pack_size) * pack_size),
                    )
                if order_qty >= moq_units:
                    lt_draw = max(1, int(round(rng.gauss(mean_lt, std_lt))))
                    if rng.random() < 0.15:
                        lt_draw += rng.randint(4, 10)
                    arrival_date = cur_date + dt.timedelta(days=lt_draw)
                    in_transit.append((arrival_date, order_qty, cur_date))
                    on_order_qty += order_qty
                    inv_position = closing_oh + on_order_qty

            stockout_flag = closing_oh == 0 and is_active_day
            if stockout_flag:
                inv_status = "STOCKOUT"
            elif closing_oh <= safety_stock:
                inv_status = "LOW_STOCK"
            else:
                inv_status = "IN_STOCK"

            inventory_snapshots.append(
                {
                    "snapshot_id": f"INV-{store_id}-{sku_id}-{date_str}",
                    "store_id": store_id,
                    "sku_id": sku_id,
                    "snapshot_date": date_str,
                    "opening_on_hand": opening_oh,
                    "receipts_units": receipts_today,
                    "units_sold": units_sold,
                    "closing_on_hand": closing_oh,
                    "on_order_units": on_order_qty,
                    "stockout_flag": stockout_flag,
                    "inventory_status": inv_status,
                }
            )

            if cur_date == CUTOFF_DATE:
                cutoff_closing_oh = closing_oh
                cutoff_on_order = on_order_qty
                cutoff_inventory_pos = closing_oh + on_order_qty
                store_committed_units[store_id] += cutoff_inventory_pos

        # -------------------------------------------------------------------
        # Step 3 & 6: Temporal Holdout Forecast Computation + Naive Baseline
        # Train window: [2025-01-16 .. 2025-12-31] (351 days)
        # Holdout evaluation window ('2026-01'): [2026-01-01 .. 2026-01-14] (14 days)
        # -------------------------------------------------------------------
        train_rows = pair_sales_rows[:351]
        holdout_rows = pair_sales_rows[351:]
        horizon_days = 14

        raw_recent = [r["units_sold"] for r in train_rows[-56:]]
        baseline_daily_mean = round(sum(raw_recent) / max(1, len(raw_recent)), 2)
        baseline_total = round(baseline_daily_mean * horizon_days, 2)

        uncensored_recent = [
            r["units_sold"]
            for r in train_rows[-56:]
            if not r["stockout_censored_flag"]
        ]
        if uncensored_recent:
            fc_daily_mean = round(sum(uncensored_recent) / len(uncensored_recent), 2)
        else:
            fc_daily_mean = round(base_rate, 2)

        fc_id = f"FC-{store_id}-{sku_id}-2026-01"
        holdout_actual = sum(r["true_unconstrained_demand"] for r in holdout_rows)

        if (
            injected_counts["FORECAST_USES_FUTURE_SALES"] < 8
            and pair_idx >= 20
            and pair_idx % 31 == 0
        ):
            leaked_daily = round(holdout_actual / float(horizon_days), 2)
            leaked_total = round(leaked_daily * horizon_days, 2)
            clean_total = round(fc_daily_mean * horizon_days, 2)
            forecasts.append(
                {
                    "forecast_id": fc_id,
                    "store_id": store_id,
                    "sku_id": sku_id,
                    "forecast_period": "2026-01",
                    "train_window_start": SIM_START_DATE.isoformat(),
                    "train_window_end": HOLDOUT_END_DATE.isoformat(),  # Future leakage into 2026-01!
                    "horizon_days": horizon_days,
                    "forecast_daily_mean": leaked_daily,
                    "forecast_total_units": leaked_total,
                    "baseline_naive_total_units": baseline_total,
                    "holdout_actual_units": holdout_actual,
                    "model_method": "LEAKED_FUTURE_LOOKAHEAD",
                }
            )
            ground_truth.append(
                {
                    "ground_truth_id": f"GT-{gt_counter:06d}",
                    "entity_type": "Forecast",
                    "record_id": fc_id,
                    "issue_type": "FORECAST_USES_FUTURE_SALES",
                    "is_anomaly": True,
                    "expected_decision": "REJECT_DATA_LEAKAGE",
                    "expected_value": clean_total,
                    "observed_value": leaked_total,
                    "rule_reference": "Rule 5 & Temporal Holdout: train_window_end must not exceed cutoff date 2025-12-31",
                }
            )
            gt_counter += 1
            injected_counts["FORECAST_USES_FUTURE_SALES"] += 1
            fc_total_for_po = clean_total
        else:
            model_name = (
                "CROSTON_SBA"
                if sku["demand_profile"] == "INTERMITTENT"
                else "SEASONAL_MOVING_AVG_IMPUTED"
            )
            fc_total = round(fc_daily_mean * horizon_days, 2)
            forecasts.append(
                {
                    "forecast_id": fc_id,
                    "store_id": store_id,
                    "sku_id": sku_id,
                    "forecast_period": "2026-01",
                    "train_window_start": SIM_START_DATE.isoformat(),
                    "train_window_end": CUTOFF_DATE.isoformat(),
                    "horizon_days": horizon_days,
                    "forecast_daily_mean": fc_daily_mean,
                    "forecast_total_units": fc_total,
                    "baseline_naive_total_units": baseline_total,
                    "holdout_actual_units": holdout_actual,
                    "model_method": model_name,
                }
            )
            fc_total_for_po = fc_total

        pending_po_candidates.append(
            {
                "store_id": store_id,
                "sku_id": sku_id,
                "supplier_id": supplier_id,
                "fc_id": fc_id,
                "policy_id": policy_id,
                "cutoff_closing_oh": cutoff_closing_oh,
                "cutoff_on_order": cutoff_on_order,
                "cutoff_inventory_pos": cutoff_inventory_pos,
                "reorder_point": reorder_point,
                "safety_stock": safety_stock,
                "fc_total_for_po": fc_total_for_po,
                "pack_size": pack_size,
                "moq_units": moq_units,
                "max_shelf_cap": max_shelf_cap,
            }
        )

    # -------------------------------------------------------------------
    # Step 3, 5, 6: Replenishment Purchase Recommendation Engine
    # -------------------------------------------------------------------
    for cand in pending_po_candidates:
        store_id = cand["store_id"]
        sku_id = cand["sku_id"]
        supplier_id = cand["supplier_id"]
        fc_id = cand["fc_id"]
        policy_id = cand["policy_id"]
        closing_oh = cand["cutoff_closing_oh"]
        on_order = cand["cutoff_on_order"]
        inv_pos = cand["cutoff_inventory_pos"]
        reorder_point = cand["reorder_point"]
        fc_total_for_po = cand["fc_total_for_po"]
        pack_size = cand["pack_size"]
        moq_units = cand["moq_units"]
        max_shelf_cap = cand["max_shelf_cap"]

        sku = sku_map[sku_id]
        store = store_map[store_id]
        store_max_cap = int(store["max_storage_capacity"])

        target_stock = reorder_point + int(math.ceil(fc_total_for_po))
        raw_needed = max(0, target_stock - inv_pos)

        if sku["lifecycle_state"] == "DISCONTINUED":
            if injected_counts["DISCONTINUED_SKU_RECOMMENDED"] < 6:
                po_id = f"PO-2026-{po_counter:06d}"
                po_counter += 1
                bad_order_qty = moq_units
                purchase_recommendations.append(
                    {
                        "po_id": po_id,
                        "store_id": store_id,
                        "sku_id": sku_id,
                        "supplier_id": supplier_id,
                        "forecast_id": fc_id,
                        "policy_id": policy_id,
                        "recommendation_date": CUTOFF_DATE.isoformat(),
                        "closing_on_hand_units": closing_oh,
                        "on_order_units": on_order,
                        "inventory_position_units": inv_pos,
                        "target_stock_level_units": target_stock,
                        "raw_needed_units": raw_needed,
                        "pack_size": pack_size,
                        "moq_units": moq_units,
                        "max_shelf_capacity_units": max_shelf_cap,
                        "recommended_order_units": bad_order_qty,
                        "order_status": "HOLD_EXCEPTION",
                        "decision_trace": (
                            f"EXCEPTION [DISCONTINUED_SKU_RECOMMENDED]: SKU {sku_id} is DISCONTINUED "
                            f"(ended {sku['effective_end_date']}), but {bad_order_qty}u was requested. "
                            f"Expected action: REJECT_DISCONTINUED_SKU (0u)."
                        ),
                    }
                )
                ground_truth.append(
                    {
                        "ground_truth_id": f"GT-{gt_counter:06d}",
                        "entity_type": "PurchaseRecommendation",
                        "record_id": po_id,
                        "issue_type": "DISCONTINUED_SKU_RECOMMENDED",
                        "is_anomaly": True,
                        "expected_decision": "REJECT_DISCONTINUED_SKU",
                        "expected_value": 0.0,
                        "observed_value": float(bad_order_qty),
                        "rule_reference": "Rule 5 & Lifecycle: SKUs in DISCONTINUED state must have 0 recommended replenishment",
                    }
                )
                gt_counter += 1
                injected_counts["DISCONTINUED_SKU_RECOMMENDED"] += 1
            continue

        if raw_needed > 0 or inv_pos <= reorder_point:
            po_id = f"PO-2026-{po_counter:06d}"
            po_counter += 1

            base_order = max(moq_units, raw_needed)
            rounded_order = int(math.ceil(base_order / pack_size) * pack_size)

            sku_headroom = max(0, max_shelf_cap - inv_pos)
            store_headroom = max(0, store_max_cap - store_committed_units[store_id])
            effective_headroom = min(sku_headroom, store_headroom)
            capped_order = int(math.floor(effective_headroom / pack_size) * pack_size)

            if rounded_order > capped_order:
                if capped_order >= moq_units:
                    valid_order_qty = capped_order
                    status = "CAPACITY_CAPPED"
                    cap_reason = (
                        f"Capped from {rounded_order}u to {valid_order_qty}u by shelf limit "
                        f"({max_shelf_cap}u, inv_pos={inv_pos}u, post-order={inv_pos + valid_order_qty}u)."
                    )
                else:
                    po_counter -= 1
                    continue
            else:
                valid_order_qty = rounded_order
                status = "RECOMMENDED"
                cap_reason = (
                    f"Standard order: InvPos ({inv_pos}u = {closing_oh}u OH + {on_order}u OnOrder) "
                    f"below Target ({target_stock}u). Needed {raw_needed}u -> rounded to {valid_order_qty}u "
                    f"(MOQ={moq_units}u, Pack={pack_size}u)."
                )

            if (
                injected_counts["REORDER_IGNORES_PACK_SIZE"] < 7
                and valid_order_qty > 0
                and pack_size >= 6
                and po_counter % 19 == 0
                and (inv_pos + valid_order_qty + 3 <= max_shelf_cap)
            ):
                unrounded_qty = valid_order_qty + 3
                store_committed_units[store_id] += unrounded_qty
                purchase_recommendations.append(
                    {
                        "po_id": po_id,
                        "store_id": store_id,
                        "sku_id": sku_id,
                        "supplier_id": supplier_id,
                        "forecast_id": fc_id,
                        "policy_id": policy_id,
                        "recommendation_date": CUTOFF_DATE.isoformat(),
                        "closing_on_hand_units": closing_oh,
                        "on_order_units": on_order,
                        "inventory_position_units": inv_pos,
                        "target_stock_level_units": target_stock,
                        "raw_needed_units": raw_needed,
                        "pack_size": pack_size,
                        "moq_units": moq_units,
                        "max_shelf_capacity_units": max_shelf_cap,
                        "recommended_order_units": unrounded_qty,
                        "order_status": "HOLD_EXCEPTION",
                        "decision_trace": (
                            f"EXCEPTION [REORDER_IGNORES_PACK_SIZE]: Order {unrounded_qty}u is not "
                            f"a multiple of pack_size={pack_size}u. Expected action: ROUND_TO_PACK_SIZE ({valid_order_qty}u)."
                        ),
                    }
                )
                ground_truth.append(
                    {
                        "ground_truth_id": f"GT-{gt_counter:06d}",
                        "entity_type": "PurchaseRecommendation",
                        "record_id": po_id,
                        "issue_type": "REORDER_IGNORES_PACK_SIZE",
                        "is_anomaly": True,
                        "expected_decision": "ROUND_TO_PACK_SIZE",
                        "expected_value": float(valid_order_qty),
                        "observed_value": float(unrounded_qty),
                        "rule_reference": "Rule 3 & 5: recommended_order_units must be an exact multiple of SupplierSKU.pack_size",
                    }
                )
                gt_counter += 1
                injected_counts["REORDER_IGNORES_PACK_SIZE"] += 1
            else:
                store_committed_units[store_id] += valid_order_qty
                purchase_recommendations.append(
                    {
                        "po_id": po_id,
                        "store_id": store_id,
                        "sku_id": sku_id,
                        "supplier_id": supplier_id,
                        "forecast_id": fc_id,
                        "policy_id": policy_id,
                        "recommendation_date": CUTOFF_DATE.isoformat(),
                        "closing_on_hand_units": closing_oh,
                        "on_order_units": on_order,
                        "inventory_position_units": inv_pos,
                        "target_stock_level_units": target_stock,
                        "raw_needed_units": raw_needed,
                        "pack_size": pack_size,
                        "moq_units": moq_units,
                        "max_shelf_capacity_units": max_shelf_cap,
                        "recommended_order_units": valid_order_qty,
                        "order_status": status,
                        "decision_trace": cap_reason,
                    }
                )
                if (
                    status == "CAPACITY_CAPPED"
                    and injected_counts["CAPACITY_CONSTRAINED_ORDER"] < 10
                ):
                    ground_truth.append(
                        {
                            "ground_truth_id": f"GT-{gt_counter:06d}",
                            "entity_type": "PurchaseRecommendation",
                            "record_id": po_id,
                            "issue_type": "CAPACITY_CONSTRAINED_ORDER",
                            "is_anomaly": False,
                            "expected_decision": "CAP_AT_STORAGE_LIMIT",
                            "expected_value": float(valid_order_qty),
                            "observed_value": float(valid_order_qty),
                            "rule_reference": "Rule 3: Order capped so inventory_position + order <= max_shelf_capacity_units",
                        }
                    )
                    gt_counter += 1
                    injected_counts["CAPACITY_CONSTRAINED_ORDER"] += 1

    return {
        "supplier": suppliers,
        "sku": skus,
        "store": stores,
        "supplier_sku": supplier_skus,
        "reorder_policy": reorder_policies,
        "lead_time_observation": lead_time_observations,
        "sales_history": sales_history,
        "inventory_snapshot": inventory_snapshots,
        "forecast": forecasts,
        "purchase_recommendation": purchase_recommendations,
        "ground_truth": ground_truth,
    }


# ---------------------------------------------------------------------------
# Step 9: SQL Seed Export & Source Manifest Generation
# ---------------------------------------------------------------------------

def export_sql_seed(output_dir: Path, tables: dict[str, list[dict[str, Any]]]) -> Path:
    """Export deterministic ANSI SQL seed file covering master and planning tables."""
    seed_path = output_dir / "seed_data.sql"
    sql_tables = [
        "supplier",
        "sku",
        "store",
        "supplier_sku",
        "reorder_policy",
        "lead_time_observation",
        "forecast",
        "purchase_recommendation",
    ]
    with seed_path.open("w", encoding="utf-8", newline="\n") as f:
        f.write("-- Deterministic ANSI SQL Seed Data (Generated with fixed seed)\n")
        f.write("BEGIN;\n\n")
        for t_name in sql_tables:
            rows = tables[t_name]
            if not rows:
                continue
            cols = list(rows[0].keys())
            col_list = ", ".join(cols)
            for r in rows[:250]:
                vals: list[str] = []
                for c in cols:
                    v = r[c]
                    if v is None or v == "":
                        vals.append("NULL")
                    elif isinstance(v, bool):
                        vals.append("TRUE" if v else "FALSE")
                    elif isinstance(v, (int, float)):
                        vals.append(str(v))
                    else:
                        escaped = str(v).replace("'", "''")
                        vals.append(f"'{escaped}'")
                val_str = ", ".join(vals)
                f.write(f"INSERT INTO {t_name} ({col_list}) VALUES ({val_str});\n")
            f.write("\n")
        f.write("COMMIT;\n")
    return seed_path


def run_generator(seed: int, scale_mode: str, output_dir: Path) -> dict[str, Any]:
    """Main entry point to generate all datasets, ground truth, and source manifest."""
    rng = random.Random(seed)
    cfg = SCALE_PRESETS[scale_mode]

    suppliers, skus, stores, supplier_skus = generate_master_entities(rng, cfg)
    tables = run_simulation_and_planning(
        rng, cfg, suppliers, skus, stores, supplier_skus
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    file_Inventory: dict[str, dict[str, Any]] = {}

    for table_name, rows in tables.items():
        if not rows:
            continue
        csv_path = output_dir / f"{table_name}.csv"
        fieldnames = list(rows[0].keys())
        write_csv(csv_path, rows, fieldnames)
        file_Inventory[f"{table_name}.csv"] = {
            "row_count": len(rows),
            "sha256": compute_sha256(csv_path),
        }

    for json_table in ("ground_truth", "forecast", "purchase_recommendation"):
        json_path = output_dir / f"{json_table}.json"
        write_json(json_path, tables[json_table])
        file_Inventory[f"{json_table}.json"] = {
            "row_count": len(tables[json_table]),
            "sha256": compute_sha256(json_path),
        }

    seed_sql_path = export_sql_seed(output_dir, tables)
    file_Inventory["seed_data.sql"] = {
        "row_count": sum(min(250, len(tables[t])) for t in (
            "supplier", "sku", "store", "supplier_sku",
            "reorder_policy", "lead_time_observation",
            "forecast", "purchase_recommendation"
        )),
        "sha256": compute_sha256(seed_sql_path),
    }

    manifest = {
        "project": "SKU-Location Demand Forecasting & Replenishment Engine",
        "generator_script": "backend/generate_pipeline.py",
        "python_compatibility": "Python 3.10+ (Windows 10 / Linux / macOS)",
        "fixed_seed": seed,
        "scale_mode": scale_mode,
        "parameters": asdict(cfg),
        "simulation_window": {
            "start_date": SIM_START_DATE.isoformat(),
            "cutoff_date": CUTOFF_DATE.isoformat(),
            "holdout_start_date": HOLDOUT_START_DATE.isoformat(),
            "end_date": SIM_END_DATE.isoformat(),
            "forecast_period": "2026-01",
            "train_days": 351,
            "holdout_days": 14,
        },
        "provenance": {
            "data_origin": "100% synthetic data generated deterministically from domain rules",
            "external_data_used": False,
            "license": "MIT / Permissive Open Synthetic Benchmark",
        },
        "files": file_Inventory,
    }

    manifest_path = output_dir / "source_manifest.json"
    write_json(manifest_path, manifest)
    return manifest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate synthetic SKU-location demand & replenishment datasets."
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=20261022,
        help="Fixed random seed for deterministic generation (default: 20261022)",
    )
    parser.add_argument(
        "--scale",
        choices=["starter", "full"],
        default="starter",
        help="Dataset scale preset: 'starter' (fast verification) or 'full' (default: starter)",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="data_out",
        help="Directory to write CSV/JSON/SQL outputs (default: data_out)",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    out_path = Path(args.output_dir)
    manifest_data = run_generator(seed=args.seed, scale_mode=args.scale, output_dir=out_path)
    print(
        f"[OK] Generated {len(manifest_data['files'])} dataset files in '{out_path}' "
        f"(seed={args.seed}, scale={args.scale})."
    )
