#!/usr/bin/env python3
"""Regenerate the seven canonical CSVs from facts.json.

This is the single source of truth for how nested JSON maps to flat CSVs.
Run via the weekly GitHub Actions sync, or manually:

    python scripts/derive_csvs.py
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FACTS_PATH = ROOT / "facts.json"
DATA_DIR = ROOT / "data"


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


def main() -> int:
    if not FACTS_PATH.exists():
        print(f"ERROR: {FACTS_PATH} not found.", file=sys.stderr)
        return 1
    facts = load_facts()
    print(f"Regenerating CSVs from {FACTS_PATH.name} (data_period={facts['_meta']['data_period']})...")
    derive_pricing_by_property(facts)
    derive_products(facts)
    derive_electricity_bills(facts)
    derive_electricity_market(facts)
    derive_incentives(facts)
    derive_permits_timeline(facts)
    derive_company_facts(facts)
    print("Done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
