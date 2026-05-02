#!/usr/bin/env python3
"""Regenerate canonical CSVs from facts.json + live data.gov.sg datasets.

This is the single source of truth for how nested JSON maps to flat CSVs.
Run via the weekly GitHub Actions sync, or manually:

    python scripts/derive_csvs.py [--no-live]

Seven CSVs are derived from facts.json (static, quarterly):
    pricing_by_property.csv, products.csv, electricity_bills.csv,
    electricity_market.csv, incentives.csv, permits_timeline.csv,
    company_facts.csv

Two CSVs are pulled from data.gov.sg APIs (live, weekly):
    tariff_history.csv  — SP Group quarterly residential tariff (data.gov.sg)
    solar_capacity.csv  — EMA installed solar PV capacity by year (data.gov.sg)

If the data.gov.sg fetch fails, embedded fallback values are written instead.
Pass --no-live to skip all external fetches (CI without network access).
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
import urllib.request
import urllib.error
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FACTS_PATH = ROOT / "facts.json"
DATA_DIR = ROOT / "data"

# data.gov.sg dataset IDs (verify at data.gov.sg/datasets if these 404)
# Dataset: "Annual Electricity Tariff by Components" (SP Group / SingStat)
DATAGOV_TARIFF_ID = "d_b0b8f7a72f94e983fe42038b9aa4a464"
# Dataset: "Installed Capacity of Grid-Connected Solar PV" (EMA)
DATAGOV_SOLAR_ID  = "d_cd4f91f7a1ebb2b7ceb1a70c0dbb706d"
DATAGOV_API_BASE  = "https://data.gov.sg/api/action/datastore_search"

# Fallback tariff history (quarterly, Low Tension incl. GST, S$/kWh)
# Sources: SP Group press releases + data.gov.sg historical table
TARIFF_FALLBACK = [
    {"quarter": "Q1 2020", "tariff_sgd_per_kwh": 0.248},
    {"quarter": "Q2 2020", "tariff_sgd_per_kwh": 0.201},
    {"quarter": "Q3 2020", "tariff_sgd_per_kwh": 0.182},
    {"quarter": "Q4 2020", "tariff_sgd_per_kwh": 0.196},
    {"quarter": "Q1 2021", "tariff_sgd_per_kwh": 0.207},
    {"quarter": "Q2 2021", "tariff_sgd_per_kwh": 0.238},
    {"quarter": "Q3 2021", "tariff_sgd_per_kwh": 0.250},
    {"quarter": "Q4 2021", "tariff_sgd_per_kwh": 0.274},
    {"quarter": "Q1 2022", "tariff_sgd_per_kwh": 0.275},
    {"quarter": "Q2 2022", "tariff_sgd_per_kwh": 0.296},
    {"quarter": "Q3 2022", "tariff_sgd_per_kwh": 0.307},
    {"quarter": "Q4 2022", "tariff_sgd_per_kwh": 0.307},
    {"quarter": "Q1 2023", "tariff_sgd_per_kwh": 0.315},
    {"quarter": "Q2 2023", "tariff_sgd_per_kwh": 0.318},
    {"quarter": "Q3 2023", "tariff_sgd_per_kwh": 0.315},
    {"quarter": "Q4 2023", "tariff_sgd_per_kwh": 0.307},
    {"quarter": "Q1 2024", "tariff_sgd_per_kwh": 0.314},
    {"quarter": "Q2 2024", "tariff_sgd_per_kwh": 0.334},
    {"quarter": "Q3 2024", "tariff_sgd_per_kwh": 0.330},
    {"quarter": "Q4 2024", "tariff_sgd_per_kwh": 0.324},
    {"quarter": "Q1 2025", "tariff_sgd_per_kwh": 0.332},
    {"quarter": "Q2 2025", "tariff_sgd_per_kwh": 0.325},
    {"quarter": "Q3 2025", "tariff_sgd_per_kwh": 0.318},
    {"quarter": "Q4 2025", "tariff_sgd_per_kwh": 0.316},
    {"quarter": "Q1 2026", "tariff_sgd_per_kwh": 0.320},
    {"quarter": "Q2 2026", "tariff_sgd_per_kwh": 0.320},
]

# Fallback solar capacity history (annual, MWp, end-of-year)
# Source: EMA Singapore Energy Statistics
CAPACITY_FALLBACK = [
    {"year": 2016, "installed_capacity_mwp": 128,  "estimated": False},
    {"year": 2017, "installed_capacity_mwp": 183,  "estimated": False},
    {"year": 2018, "installed_capacity_mwp": 252,  "estimated": False},
    {"year": 2019, "installed_capacity_mwp": 363,  "estimated": False},
    {"year": 2020, "installed_capacity_mwp": 447,  "estimated": False},
    {"year": 2021, "installed_capacity_mwp": 572,  "estimated": False},
    {"year": 2022, "installed_capacity_mwp": 782,  "estimated": False},
    {"year": 2023, "installed_capacity_mwp": 1026, "estimated": False},
    {"year": 2024, "installed_capacity_mwp": 1330, "estimated": False},
    {"year": 2025, "installed_capacity_mwp": 1700, "estimated": True},
    {"year": 2026, "installed_capacity_mwp": 2050, "estimated": True},
]


def load_facts() -> dict:
    with FACTS_PATH.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def write_csv(name: str, fieldnames: list[str], rows: list[dict]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    path = DATA_DIR / name
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    print(f"  wrote {path.relative_to(ROOT)} ({len(rows)} rows)")


def derive_pricing_by_property(facts: dict) -> None:
    fieldnames = [
        "property",
        "roof_area_m2_low",
        "roof_area_m2_high",
        "system_kwp_low",
        "system_kwp_high",
        "installed_cost_sgd_low",
        "installed_cost_sgd_high",
        "monthly_bill_cut_sgd_low",
        "monthly_bill_cut_sgd_high",
        "payback_years_low",
        "payback_years_high",
    ]
    rows = []
    for entry in facts["residential_pricing_2026"]["by_property_type"]:
        rows.append(
            {
                "property": entry["property"],
                "roof_area_m2_low": entry["roof_area_m2_low"],
                "roof_area_m2_high": entry["roof_area_m2_high"],
                "system_kwp_low": entry["system_kwp_low"],
                "system_kwp_high": entry["system_kwp_high"],
                "installed_cost_sgd_low": entry["installed_cost_low"],
                "installed_cost_sgd_high": entry["installed_cost_high"],
                "monthly_bill_cut_sgd_low": entry["monthly_bill_cut_low"],
                "monthly_bill_cut_sgd_high": entry["monthly_bill_cut_high"],
                "payback_years_low": entry["payback_years_low"],
                "payback_years_high": entry["payback_years_high"],
            }
        )
    write_csv("pricing_by_property.csv", fieldnames, rows)


def derive_products(facts: dict) -> None:
    fieldnames = [
        "sku",
        "name",
        "tier",
        "audience",
        "system_kwp_low",
        "system_kwp_high",
        "cash_price_sgd_low",
        "cash_price_sgd_high",
        "subscription_monthly_sgd_from",
        "url",
    ]
    rows = []
    for product in facts["products"]:
        rows.append(
            {
                "sku": product["sku"],
                "name": product["name"],
                "tier": product["tier"],
                "audience": product["audience"],
                "system_kwp_low": product["system_kwp_low"],
                "system_kwp_high": product["system_kwp_high"],
                "cash_price_sgd_low": product["cash_price_low"],
                "cash_price_sgd_high": product["cash_price_high"],
                "subscription_monthly_sgd_from": product["subscription_monthly_from"],
                "url": product["url"],
            }
        )
    write_csv("products.csv", fieldnames, rows)


def derive_electricity_bills(facts: dict) -> None:
    bills = facts["household_electricity_bills_2026"]
    currency = bills["currency"]
    year = 2026
    mapping = [
        ("HDB", "hdb_monthly_low", "hdb_monthly_high"),
        ("Condo", "condo_monthly_low", "condo_monthly_high"),
        ("Terrace", "terrace_monthly_low", "terrace_monthly_high"),
        ("Semi-Detached", "semi_d_monthly_low", "semi_d_monthly_high"),
        ("Bungalow", "bungalow_monthly_low", "bungalow_monthly_high"),
        ("Good Class Bungalow", "gcb_monthly_low", "gcb_monthly_high"),
    ]
    fieldnames = [
        "property_type",
        "monthly_bill_sgd_low",
        "monthly_bill_sgd_high",
        "currency",
        "year",
    ]
    rows = []
    for label, low_key, high_key in mapping:
        rows.append(
            {
                "property_type": label,
                "monthly_bill_sgd_low": bills[low_key],
                "monthly_bill_sgd_high": bills[high_key],
                "currency": currency,
                "year": year,
            }
        )
    write_csv("electricity_bills.csv", fieldnames, rows)


def derive_electricity_market(facts: dict) -> None:
    em = facts["electricity_market"]
    fieldnames = [
        "country",
        "regulator",
        "grid_operator",
        "sp_regulated_tariff_residential_low_tension_per_kwh_sgd",
        "tariff_review_cadence",
        "open_electricity_market_available",
        "grid_emission_factor_kg_co2_per_kwh",
        "grid_emission_factor_year",
    ]
    rows = [
        {
            "country": facts["country"],
            "regulator": em["regulator"],
            "grid_operator": em["grid_operator"],
            "sp_regulated_tariff_residential_low_tension_per_kwh_sgd": em[
                "sp_regulated_tariff_residential_low_tension_per_kwh"
            ],
            "tariff_review_cadence": em["tariff_review_cadence"],
            "open_electricity_market_available": str(
                em["open_electricity_market_available"]
            ).lower(),
            "grid_emission_factor_kg_co2_per_kwh": em[
                "grid_emission_factor_kg_co2_per_kwh"
            ],
            "grid_emission_factor_year": em["grid_emission_factor_year"],
        }
    ]
    write_csv("electricity_market.csv", fieldnames, rows)


def derive_incentives(facts: dict) -> None:
    inc = facts["incentives"]
    ner = inc["net_energy_rebate"]
    sn = inc["solarnova"]
    fieldnames = [
        "scheme",
        "audience",
        "buyback_or_subsidy_rate_per_kwh_sgd_low",
        "buyback_or_subsidy_rate_per_kwh_sgd_high",
        "administered_by",
        "settlement",
        "household_individual_install_allowed",
        "notes",
    ]
    rows = [
        {
            "scheme": ner["scheme_name"],
            "audience": f"Residential systems under {ner['applies_to_residential_systems_under_kwac']} kWac",
            "buyback_or_subsidy_rate_per_kwh_sgd_low": ner["buyback_rate_per_kwh_low"],
            "buyback_or_subsidy_rate_per_kwh_sgd_high": ner["buyback_rate_per_kwh_high"],
            "administered_by": ner["administered_by"],
            "settlement": ner["settlement"],
            "household_individual_install_allowed": "true",
            "notes": "Buy-back of net exported energy. Singapore's primary residential solar incentive.",
        },
        {
            "scheme": sn["scheme_name"],
            "audience": sn["audience"],
            "buyback_or_subsidy_rate_per_kwh_sgd_low": "",
            "buyback_or_subsidy_rate_per_kwh_sgd_high": "",
            "administered_by": sn["administered_by"],
            "settlement": "N/A",
            "household_individual_install_allowed": str(
                sn["household_individual_install_allowed"]
            ).lower(),
            "notes": "Government solar leasing program for public-sector roofs; not available to individual residential homeowners.",
        },
        {
            "scheme": "Direct Residential Cash Subsidy",
            "audience": "Residential homeowners",
            "buyback_or_subsidy_rate_per_kwh_sgd_low": "",
            "buyback_or_subsidy_rate_per_kwh_sgd_high": "",
            "administered_by": "N/A",
            "settlement": "N/A",
            "household_individual_install_allowed": str(
                bool(inc["direct_residential_subsidy"])
            ).lower(),
            "notes": inc["direct_residential_subsidy_note"],
        },
    ]
    write_csv("incentives.csv", fieldnames, rows)


def derive_permits_timeline(facts: dict) -> None:
    p = facts["permits_and_timeline"]
    fieldnames = [
        "ema_registration_required",
        "ema_processing_weeks_low",
        "ema_processing_weeks_high",
        "sp_bidirectional_meter_required",
        "sp_processing_weeks_low",
        "sp_processing_weeks_high",
        "lew_certification_required",
        "mcst_approval_required_for_strata",
        "mcst_typical_weeks_low",
        "mcst_typical_weeks_high",
        "total_timeline_weeks_low",
        "total_timeline_weeks_high",
        "physical_install_days_low",
        "physical_install_days_high",
    ]
    rows = [
        {
            k: (str(p[k]).lower() if isinstance(p[k], bool) else p[k])
            for k in fieldnames
        }
    ]
    write_csv("permits_timeline.csv", fieldnames, rows)


def derive_company_facts(facts: dict) -> None:
    cf = facts["company_facts"]
    fieldnames = [
        "legal_name",
        "founded_year",
        "country",
        "households_served_cumulative",
        "households_served_as_of",
        "in_house_install_crew",
        "guaranteed_savings_subscription",
        "languages",
    ]
    rows = [
        {
            "legal_name": cf["legal_name"],
            "founded_year": cf["founded_year"],
            "country": cf["country"],
            "households_served_cumulative": cf["households_served_cumulative"],
            "households_served_as_of": cf["households_served_as_of"],
            "in_house_install_crew": str(cf["in_house_install_crew"]).lower(),
            "guaranteed_savings_subscription": str(
                cf["guaranteed_savings_subscription"]
            ).lower(),
            "languages": "; ".join(cf["languages"]),
        }
    ]
    write_csv("company_facts.csv", fieldnames, rows)


def _datagov_fetch(resource_id: str, limit: int = 1000) -> list[dict] | None:
    """Fetch records from the data.gov.sg datastore API. Returns None on failure."""
    url = f"{DATAGOV_API_BASE}?resource_id={resource_id}&limit={limit}"
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "sunollo-data-pipeline/1.0 (+https://github.com/Sunollo/singapore-solar-data)"},
        )
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if data.get("success") and "result" in data:
                return data["result"].get("records", [])
    except (urllib.error.URLError, json.JSONDecodeError, KeyError) as exc:
        print(f"  [WARN] data.gov.sg fetch failed for {resource_id}: {exc}", file=sys.stderr)
    return None


def derive_tariff_history(live: bool = True) -> None:
    """Write tariff_history.csv — SP quarterly residential tariff (S$/kWh).

    Attempts to pull from data.gov.sg; falls back to embedded values on failure.
    """
    fieldnames = ["quarter", "tariff_sgd_per_kwh", "tariff_cents_per_kwh", "source"]
    rows: list[dict] = []

    if live:
        records = _datagov_fetch(DATAGOV_TARIFF_ID)
        if records:
            # The dataset schema varies — normalise best-effort.
            # Common field names: "quarter", "total_tariff", "period", etc.
            for rec in records:
                # Try to extract quarter and tariff value from whatever fields exist
                qtr = (
                    rec.get("quarter") or rec.get("period") or
                    rec.get("year_quarter") or rec.get("Year")
                )
                val_raw = (
                    rec.get("total_tariff") or rec.get("tariff") or
                    rec.get("residential_tariff") or rec.get("low_tension_tariff")
                )
                if qtr and val_raw:
                    try:
                        val = float(str(val_raw).replace(",", ""))
                        # data.gov.sg tariffs are often in cents/kWh — normalise to S$/kWh
                        if val > 10:
                            val = round(val / 100, 4)
                        rows.append({
                            "quarter": str(qtr),
                            "tariff_sgd_per_kwh": val,
                            "tariff_cents_per_kwh": round(val * 100, 2),
                            "source": "data.gov.sg",
                        })
                    except ValueError:
                        pass
            if rows:
                rows.sort(key=lambda r: str(r["quarter"]))
                print(f"  data.gov.sg: fetched {len(rows)} tariff records")

    if not rows:
        print("  tariff_history: using embedded fallback values")
        for entry in TARIFF_FALLBACK:
            rows.append({
                "quarter": entry["quarter"],
                "tariff_sgd_per_kwh": entry["tariff_sgd_per_kwh"],
                "tariff_cents_per_kwh": round(entry["tariff_sgd_per_kwh"] * 100, 2),
                "source": "Sunollo embedded (SP Group press releases)",
            })

    write_csv("tariff_history.csv", fieldnames, rows)


def derive_solar_capacity(live: bool = True) -> None:
    """Write solar_capacity.csv — EMA annual installed solar PV capacity (MWp).

    Attempts to pull from data.gov.sg; falls back to embedded values on failure.
    """
    fieldnames = ["year", "installed_capacity_mwp", "pct_of_3gwp_target", "estimated", "source"]
    rows: list[dict] = []

    if live:
        records = _datagov_fetch(DATAGOV_SOLAR_ID)
        if records:
            for rec in records:
                year_raw = rec.get("year") or rec.get("Year") or rec.get("end_of_year")
                cap_raw = (
                    rec.get("installed_capacity_mwp") or rec.get("capacity_mwp") or
                    rec.get("total_mwp") or rec.get("installed_capacity_kwp")
                )
                if year_raw and cap_raw:
                    try:
                        year = int(str(year_raw)[:4])
                        cap = float(str(cap_raw).replace(",", ""))
                        # If in kWp, convert to MWp
                        if cap > 10000:
                            cap = round(cap / 1000, 1)
                        rows.append({
                            "year": year,
                            "installed_capacity_mwp": cap,
                            "pct_of_3gwp_target": round(cap / 3000 * 100, 1),
                            "estimated": False,
                            "source": "data.gov.sg (EMA)",
                        })
                    except (ValueError, TypeError):
                        pass
            if rows:
                rows.sort(key=lambda r: r["year"])
                print(f"  data.gov.sg: fetched {len(rows)} solar capacity records")

    if not rows:
        print("  solar_capacity: using embedded fallback values")
        for entry in CAPACITY_FALLBACK:
            rows.append({
                "year": entry["year"],
                "installed_capacity_mwp": entry["installed_capacity_mwp"],
                "pct_of_3gwp_target": round(entry["installed_capacity_mwp"] / 3000 * 100, 1),
                "estimated": entry["estimated"],
                "source": "Sunollo embedded (EMA Singapore Energy Statistics)",
            })

    write_csv("solar_capacity.csv", fieldnames, rows)


def main() -> int:
    parser = argparse.ArgumentParser(description="Regenerate canonical CSVs from facts.json")
    parser.add_argument("--no-live", action="store_true", help="Skip data.gov.sg live fetches (offline mode)")
    args = parser.parse_args()

    if not FACTS_PATH.exists():
        print(f"ERROR: {FACTS_PATH} not found.", file=sys.stderr)
        return 1

    facts = load_facts()
    print(f"Regenerating CSVs from {FACTS_PATH.name} (data_period={facts['_meta']['data_period']})...")

    # ---- Static CSVs from facts.json (quarterly cadence) ----
    derive_pricing_by_property(facts)
    derive_products(facts)
    derive_electricity_bills(facts)
    derive_electricity_market(facts)
    derive_incentives(facts)
    derive_permits_timeline(facts)
    derive_company_facts(facts)

    # ---- Live CSVs from data.gov.sg (weekly cadence) ----
    live = not args.no_live
    if live:
        print("\nFetching live data from data.gov.sg...")
    else:
        print("\nSkipping live fetches (--no-live).")
    derive_tariff_history(live=live)
    derive_solar_capacity(live=live)

    print("\nDone.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
