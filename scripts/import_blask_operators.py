#!/usr/bin/env python3
"""Build the casino discovery registry from all country sheets in a Blask workbook."""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd


def load_existing(path: Path):
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = payload.get("operators", payload) if isinstance(payload, dict) else payload
    return {(row.get("country"), row.get("operator")): row for row in rows}


def build(workbook: Path, existing_path: Path):
    existing = load_existing(existing_path)
    excel = pd.ExcelFile(workbook)
    rows = []
    for country in excel.sheet_names:
        if country == "Blask Info":
            continue
        sheet = pd.read_excel(workbook, sheet_name=country, header=None)
        for values in sheet.iloc[3:].itertuples(index=False, name=None):
            rank, operator = values[0], values[1]
            if pd.isna(operator) or not str(operator).strip():
                continue
            operator = str(operator).strip()
            row = {
                "country": country,
                "rank": int(rank) if pd.notna(rank) and float(rank).is_integer() else rank,
                "operator": operator,
                "vertical": "" if len(values) < 3 or pd.isna(values[2]) else str(values[2]).strip(),
                "license": "" if len(values) < 4 or pd.isna(values[3]) else str(values[3]).strip(),
            }
            old = existing.get((country, operator), {})
            for key in ("homepage", "careers_url"):
                if old.get(key):
                    row[key] = old[key]
            rows.append(row)
    return {
        "source": {
            "file": workbook.name,
            "sheets": [sheet for sheet in excel.sheet_names if sheet != "Blask Info"],
            "generated_at": datetime.now(timezone.utc).date().isoformat(),
        },
        "operators": rows,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("workbook", type=Path)
    parser.add_argument("--output", type=Path, default=Path("data/casino-operators.json"))
    parser.add_argument("--existing", type=Path, default=Path("data/casino-operators-ua-uk.json"))
    args = parser.parse_args()
    payload = build(args.workbook, args.existing)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{len(payload['operators'])} operators from {len(payload['source']['sheets'])} countries")


if __name__ == "__main__":
    main()
