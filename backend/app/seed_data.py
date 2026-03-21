from datetime import datetime

from .database import Base, SessionLocal, engine
from .models import BottleScan, Mission, RelayLog, Slot, SlotBatch


def ensure_default_slots(db) -> None:
    existing_ids = {slot.id for slot in db.query(Slot).all()}
    for slot_id in range(1, 9):
        if slot_id not in existing_ids:
            db.add(Slot(id=slot_id, status="empty", station_code=None, current_batch_id=None))


def seed_sample_data(db) -> dict:
    """Create a minimal demo dataset if the system has no scan data yet."""
    ensure_default_slots(db)

    if db.query(BottleScan).count() > 0:
        db.commit()
        return {"seeded": False, "reason": "bottle_scans already has data"}

    slot = db.get(Slot, 1)
    if not slot:
        db.commit()
        return {"seeded": False, "reason": "slot 1 not found"}

    now = datetime.now()
    batch = SlotBatch(
        slot_id=slot.id,
        station_code="S101",
        status="ready",
        created_at=now,
    )
    db.add(batch)
    db.flush()

    slot.current_batch_id = batch.id
    slot.status = "ready"
    slot.station_code = "S101"

    demo_rows = [
        {
            "item_id": "DEMO-ITEM-001",
            "patient_name": "Demo Patient A",
            "drug_code": "DRUG-A",
            "strength": "500mg",
            "qty": 1,
            "rate": 1.0,
            "diluent": "NSS",
            "administration": "IV",
            "order_date": "2026-03-20",
            "hn": "HN-0001",
            "station_code": "S101",
            "bed_no": "A1",
        },
        {
            "item_id": "DEMO-ITEM-002",
            "patient_name": "Demo Patient B",
            "drug_code": "DRUG-B",
            "strength": "1g",
            "qty": 2,
            "rate": 2.0,
            "diluent": "D5W",
            "administration": "IV",
            "order_date": "2026-03-20",
            "hn": "HN-0002",
            "station_code": "S101",
            "bed_no": "A2",
        },
    ]

    for row in demo_rows:
        db.add(
            BottleScan(
                batch_id=batch.id,
                qr_raw=(
                    f"{row['item_id']}|{row['patient_name']}|{row['drug_code']}|||{row['strength']}|"
                    f"{row['qty']}|||{row['rate']}||||{row['diluent']}|{row['administration']}|"
                    f"{row['order_date']}|{row['hn']}|{row['station_code']}|{row['bed_no']}"
                ),
                item_id=row["item_id"],
                patient_name=row["patient_name"],
                drug_code=row["drug_code"],
                strength=row["strength"],
                qty=row["qty"],
                rate=row["rate"],
                diluent=row["diluent"],
                administration=row["administration"],
                order_date=row["order_date"],
                hn=row["hn"],
                station_code=row["station_code"],
                bed_no=row["bed_no"],
                scanned_at=now,
            )
        )

    db.add(
        Mission(
            batch_id=batch.id,
            slot_id=slot.id,
            station_code="S101",
            status="sent",
            robot_mission_id="DEMO-MISSION-001",
            created_at=now,
        )
    )

    db.add(
        RelayLog(
            slot_id=slot.id,
            action="open",
            result="simulated",
            detail="seeded demo data",
            created_at=now,
        )
    )

    db.commit()
    return {"seeded": True, "slot_id": slot.id, "batch_id": batch.id, "items": len(demo_rows)}


def main() -> None:
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        result = seed_sample_data(db)
    finally:
        db.close()

    if result.get("seeded"):
        print(
            f"Seed completed: slot={result['slot_id']} batch={result['batch_id']} items={result['items']}"
        )
    else:
        print(f"Seed skipped: {result['reason']}")


if __name__ == "__main__":
    main()
