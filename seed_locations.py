import os
import json

from app import create_app
from transport.models import db, Location


def load_stations_from_json(json_path: str):
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Expecting a list of objects with keys:
    # "station_code", "station_name", "region_code"
    added = 0
    skipped_existing = 0
    skipped_invalid = 0

    for row in data:
        code = (row.get("station_code") or "").strip()
        name = (row.get("station_name") or "").strip()
        # region_code = (row.get("region_code") or "").strip()  # not used yet

        if not code or not name:
            skipped_invalid += 1
            continue

        # Check if we already have this location by code
        existing = Location.query.filter_by(code=code).first()
        if existing:
            skipped_existing += 1
            continue

        loc = Location(
            code=code,
            name=name,
            address=None,  # we don't have a proper address in this dataset
        )
        db.session.add(loc)
        added += 1

    db.session.commit()
    print(f"✅ Locations seeding complete.")
    print(f"   Added: {added}")
    print(f"   Skipped existing: {skipped_existing}")
    print(f"   Skipped invalid rows: {skipped_invalid}")


def main():
    base_dir = os.path.abspath(os.path.dirname(__file__))
    json_path = os.path.join(base_dir, "data", "ir_stations.json")

    if not os.path.exists(json_path):
        raise FileNotFoundError(f"JSON file not found: {json_path}")

    app = create_app()

    with app.app_context():
        load_stations_from_json(json_path)


if __name__ == "__main__":
    main()
