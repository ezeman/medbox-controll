import os
from io import StringIO
import csv
from datetime import datetime

import httpx
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .database import Base, engine, get_db
from .models import BottleScan, Mission, RelayLog, Slot, SlotBatch
from .schemas import MessageResponse, MissionResponse, RelayOpenResponse, RobotConfig, ScanRequest, SlotSelectResponse, SlotView
from .services import parse_qr

ROBOT_API_URL = os.getenv("ROBOT_API_URL", "")
RELAY_API_URL = os.getenv("RELAY_API_URL", "")
ROBOT_IP = os.getenv("ROBOT_IP", "")

app = FastAPI(title="Med Bottle Slot API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def ensure_default_slots(db: Session) -> None:
    existing = db.query(Slot).count()
    if existing >= 8:
        return
    ids = {slot.id for slot in db.query(Slot).all()}
    for i in range(1, 9):
        if i not in ids:
            db.add(Slot(id=i, status="empty", station_code=None, current_batch_id=None))
    db.commit()


def send_relay_open(slot_id: int) -> tuple[str, str | None]:
    if not RELAY_API_URL:
        return "simulated", "RELAY_API_URL not configured"

    payload = {"slot_id": slot_id, "action": "open"}
    try:
        with httpx.Client(timeout=5.0) as client:
            response = client.post(RELAY_API_URL, json=payload)
            response.raise_for_status()
        return "ok", None
    except Exception as exc:
        return "failed", str(exc)


def ensure_active_batch(slot: Slot, db: Session) -> SlotBatch:
    if slot.current_batch_id:
        existing = db.get(SlotBatch, slot.current_batch_id)
        if existing and existing.status in {"selected", "loading", "ready"}:
            return existing

    batch = SlotBatch(slot_id=slot.id, status="selected", station_code=None)
    db.add(batch)
    db.flush()

    slot.current_batch_id = batch.id
    slot.status = "selected"
    slot.station_code = None
    return batch


@app.on_event("startup")
def startup_event():
    Base.metadata.create_all(bind=engine)
    app.state.robot_ip = ROBOT_IP
    app.state.robot_api_url = ROBOT_API_URL
    with next(get_db()) as db:
        ensure_default_slots(db)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/")
def root():
    return {
        "name": "Med Bottle Slot API",
        "status": "ok",
        "health": "/health",
        "docs": "/docs",
    }


@app.get("/api/config/robot", response_model=RobotConfig)
def get_robot_config():
    return RobotConfig(
        robot_ip=getattr(app.state, "robot_ip", "") or None,
        robot_api_url=getattr(app.state, "robot_api_url", "") or None,
    )


@app.post("/api/config/robot", response_model=RobotConfig)
def set_robot_config(body: RobotConfig):
    robot_ip = (body.robot_ip or "").strip()
    robot_api_url = (body.robot_api_url or "").strip()

    app.state.robot_ip = robot_ip
    app.state.robot_api_url = robot_api_url

    return RobotConfig(
        robot_ip=robot_ip or None,
        robot_api_url=robot_api_url or None,
    )


@app.get("/api/slots", response_model=list[SlotView])
def get_slots(db: Session = Depends(get_db)):
    ensure_default_slots(db)
    rows = (
        db.query(
            Slot.id,
            Slot.status,
            Slot.station_code,
            func.count(BottleScan.id).label("item_count"),
        )
        .outerjoin(SlotBatch, Slot.current_batch_id == SlotBatch.id)
        .outerjoin(BottleScan, BottleScan.batch_id == SlotBatch.id)
        .group_by(Slot.id, Slot.status, Slot.station_code)
        .order_by(Slot.id)
        .all()
    )
    return [SlotView(id=r.id, status=r.status, station_code=r.station_code, item_count=r.item_count) for r in rows]


@app.post("/api/slots/{slot_id}/select", response_model=SlotSelectResponse)
def select_slot(slot_id: int, db: Session = Depends(get_db)):
    slot = db.get(Slot, slot_id)
    if not slot:
        raise HTTPException(status_code=404, detail="Slot not found")

    batch = ensure_active_batch(slot, db)
    db.commit()
    db.refresh(batch)

    return SlotSelectResponse(slot_id=slot.id, batch_id=batch.id, status=batch.status)


@app.post("/api/slots/{slot_id}/open", response_model=RelayOpenResponse)
def open_slot(slot_id: int, db: Session = Depends(get_db)):
    slot = db.get(Slot, slot_id)
    if not slot:
        raise HTTPException(status_code=404, detail="Slot not found")

    batch = ensure_active_batch(slot, db)
    relay_result, detail = send_relay_open(slot.id)
    db.add(RelayLog(slot_id=slot.id, action="open", result=relay_result, detail=detail))

    db.commit()
    db.refresh(batch)
    return RelayOpenResponse(slot_id=slot.id, status=batch.status, relay_result=relay_result)


@app.post("/api/slots/open-empty", response_model=RelayOpenResponse)
def open_empty_slot(db: Session = Depends(get_db)):
    ensure_default_slots(db)
    slot = db.scalar(select(Slot).where(Slot.status == "empty").order_by(Slot.id).limit(1))
    if not slot:
        raise HTTPException(status_code=409, detail="No empty slot available")

    batch = ensure_active_batch(slot, db)
    relay_result, detail = send_relay_open(slot.id)
    db.add(RelayLog(slot_id=slot.id, action="open", result=relay_result, detail=detail))

    db.commit()
    db.refresh(batch)
    return RelayOpenResponse(slot_id=slot.id, status=batch.status, relay_result=relay_result)


@app.post("/api/slots/{slot_id}/scan")
def scan_into_slot(slot_id: int, body: ScanRequest, db: Session = Depends(get_db)):
    slot = db.get(Slot, slot_id)
    if not slot:
        raise HTTPException(status_code=404, detail="Slot not found")

    if not slot.current_batch_id:
        raise HTTPException(status_code=400, detail="Select slot before scanning")

    batch = db.get(SlotBatch, slot.current_batch_id)
    if not batch or batch.status in {"dispatched", "closed"}:
        raise HTTPException(status_code=400, detail="Batch is already dispatched; reopen slot")

    parsed = parse_qr(body.qr_raw)

    if batch.station_code and batch.station_code != parsed.station_code:
        raise HTTPException(status_code=409, detail="Station code mismatch for this slot")

    exists = db.scalar(
        select(BottleScan).where(
            BottleScan.batch_id == batch.id,
            BottleScan.item_id == parsed.item_id,
        )
    )
    if exists:
        raise HTTPException(status_code=409, detail="Duplicate item in current slot batch")

    if not batch.station_code:
        batch.station_code = parsed.station_code
        slot.station_code = parsed.station_code

    item = BottleScan(
        batch_id=batch.id,
        qr_raw=body.qr_raw,
        item_id=parsed.item_id,
        patient_name=parsed.patient_name,
        drug_code=parsed.drug_code,
        strength=parsed.strength,
        qty=parsed.qty,
        rate=parsed.rate,
        diluent=parsed.diluent,
        administration=parsed.administration,
        order_date=parsed.order_date,
        hn=parsed.hn,
        station_code=parsed.station_code,
        bed_no=parsed.bed_no,
    )
    db.add(item)

    batch.status = "loading"
    slot.status = "loading"
    db.commit()
    db.refresh(item)

    return {
        "slot_id": slot.id,
        "batch_id": batch.id,
        "item_db_id": item.id,
        "item_id": item.item_id,
        "station_code": item.station_code,
        "status": batch.status,
    }


@app.get("/api/slots/{slot_id}/items")
def list_slot_items(slot_id: int, db: Session = Depends(get_db)):
    slot = db.get(Slot, slot_id)
    if not slot or not slot.current_batch_id:
        return []

    rows = (
        db.query(BottleScan)
        .filter(BottleScan.batch_id == slot.current_batch_id)
        .order_by(BottleScan.scanned_at.desc())
        .all()
    )

    return [
        {
            "id": r.id,
            "item_id": r.item_id,
            "drug_code": r.drug_code,
            "hn": r.hn,
            "station_code": r.station_code,
            "bed_no": r.bed_no,
            "scanned_at": r.scanned_at,
        }
        for r in rows
    ]


@app.delete("/api/slots/{slot_id}/items/{scan_id}", response_model=MessageResponse)
def delete_slot_item(slot_id: int, scan_id: int, db: Session = Depends(get_db)):
    slot = db.get(Slot, slot_id)
    if not slot or not slot.current_batch_id:
        raise HTTPException(status_code=404, detail="Slot or active batch not found")

    row = db.get(BottleScan, scan_id)
    if not row or row.batch_id != slot.current_batch_id:
        raise HTTPException(status_code=404, detail="Item not found in slot")

    db.delete(row)
    db.flush()

    remaining = db.scalar(select(func.count(BottleScan.id)).where(BottleScan.batch_id == slot.current_batch_id))
    if not remaining:
        slot.status = "selected"
        batch = db.get(SlotBatch, slot.current_batch_id)
        if batch:
            batch.status = "selected"
            batch.station_code = None
        slot.station_code = None

    db.commit()
    return MessageResponse(message="deleted")


@app.post("/api/slots/{slot_id}/start-mission", response_model=MissionResponse)
def start_mission(slot_id: int, db: Session = Depends(get_db)):
    slot = db.get(Slot, slot_id)
    if not slot or not slot.current_batch_id:
        raise HTTPException(status_code=404, detail="Slot or active batch not found")

    batch = db.get(SlotBatch, slot.current_batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")

    if batch.status in {"dispatched", "closed"}:
        raise HTTPException(status_code=409, detail="Batch already dispatched")

    item_count = db.scalar(select(func.count(BottleScan.id)).where(BottleScan.batch_id == batch.id))
    if not item_count:
        raise HTTPException(status_code=400, detail="No scanned items in this slot")

    robot_api_url = getattr(app.state, "robot_api_url", "") or ROBOT_API_URL
    robot_mission_id = None
    if robot_api_url:
        payload = {
            "station_code": batch.station_code,
            "slot_id": slot.id,
            "batch_id": batch.id,
            "item_count": item_count,
        }
        try:
            with httpx.Client(timeout=5.0) as client:
                resp = client.post(robot_api_url, json=payload)
                resp.raise_for_status()
                robot_mission_id = str(resp.json().get("mission_id", "")) or None
        except Exception:
            robot_mission_id = None

    mission = Mission(
        batch_id=batch.id,
        slot_id=slot.id,
        station_code=batch.station_code or "",
        status="sent",
        robot_mission_id=robot_mission_id,
    )
    db.add(mission)

    batch.status = "dispatched"
    slot.status = "dispatched"
    batch.closed_at = datetime.utcnow()

    db.commit()
    db.refresh(mission)
    return MissionResponse(
        mission_id=mission.id,
        batch_id=batch.id,
        slot_id=slot.id,
        station_code=mission.station_code,
        status=mission.status,
        robot_mission_id=mission.robot_mission_id,
        created_at=mission.created_at,
    )


@app.post("/api/slots/{slot_id}/reopen", response_model=SlotSelectResponse)
def reopen_slot(slot_id: int, db: Session = Depends(get_db)):
    slot = db.get(Slot, slot_id)
    if not slot:
        raise HTTPException(status_code=404, detail="Slot not found")

    batch = SlotBatch(slot_id=slot.id, status="selected", station_code=None)
    db.add(batch)
    db.flush()

    slot.current_batch_id = batch.id
    slot.status = "selected"
    slot.station_code = None

    db.commit()
    db.refresh(batch)

    return SlotSelectResponse(slot_id=slot.id, batch_id=batch.id, status=batch.status)


@app.get("/api/history/scans")
def get_scan_history(limit: int = 100, db: Session = Depends(get_db)):
    safe_limit = min(max(limit, 1), 1000)
    rows = (
        db.query(BottleScan, SlotBatch.slot_id)
        .join(SlotBatch, BottleScan.batch_id == SlotBatch.id)
        .order_by(BottleScan.scanned_at.desc())
        .limit(safe_limit)
        .all()
    )

    return [
        {
            "id": scan.id,
            "slot_id": slot_id,
            "batch_id": scan.batch_id,
            "item_id": scan.item_id,
            "drug_code": scan.drug_code,
            "hn": scan.hn,
            "station_code": scan.station_code,
            "bed_no": scan.bed_no,
            "qty": scan.qty,
            "scanned_at": scan.scanned_at,
        }
        for scan, slot_id in rows
    ]


@app.get("/api/history/missions")
def get_mission_history(limit: int = 100, db: Session = Depends(get_db)):
    safe_limit = min(max(limit, 1), 1000)
    rows = (
        db.query(Mission)
        .order_by(Mission.created_at.desc())
        .limit(safe_limit)
        .all()
    )

    return [
        {
            "id": mission.id,
            "slot_id": mission.slot_id,
            "batch_id": mission.batch_id,
            "station_code": mission.station_code,
            "status": mission.status,
            "robot_mission_id": mission.robot_mission_id,
            "created_at": mission.created_at,
        }
        for mission in rows
    ]


@app.get("/api/history/export/scans.csv")
def export_scan_history_csv(db: Session = Depends(get_db)):
    rows = (
        db.query(BottleScan, SlotBatch.slot_id)
        .join(SlotBatch, BottleScan.batch_id == SlotBatch.id)
        .order_by(BottleScan.scanned_at.desc())
        .all()
    )

    buffer = StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["id", "slot_id", "batch_id", "item_id", "drug_code", "hn", "station_code", "bed_no", "qty", "scanned_at"])
    for scan, slot_id in rows:
        writer.writerow([
            scan.id,
            slot_id,
            scan.batch_id,
            scan.item_id,
            scan.drug_code,
            scan.hn,
            scan.station_code,
            scan.bed_no or "",
            scan.qty,
            scan.scanned_at.isoformat(),
        ])

    buffer.seek(0)
    headers = {"Content-Disposition": 'attachment; filename="scan_history.csv"'}
    return StreamingResponse(buffer, media_type="text/csv", headers=headers)


@app.get("/api/history/export/missions.csv")
def export_mission_history_csv(db: Session = Depends(get_db)):
    rows = db.query(Mission).order_by(Mission.created_at.desc()).all()

    buffer = StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["id", "slot_id", "batch_id", "station_code", "status", "robot_mission_id", "created_at"])
    for mission in rows:
        writer.writerow([
            mission.id,
            mission.slot_id,
            mission.batch_id,
            mission.station_code,
            mission.status,
            mission.robot_mission_id or "",
            mission.created_at.isoformat(),
        ])

    buffer.seek(0)
    headers = {"Content-Disposition": 'attachment; filename="mission_history.csv"'}
    return StreamingResponse(buffer, media_type="text/csv", headers=headers)
