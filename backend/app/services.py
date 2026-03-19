import re
from datetime import date

from fastapi import HTTPException

from .schemas import ScanResult

STATION_PATTERN = re.compile(r"^S\d{3}$")


def split_qr(raw: str) -> list[str]:
    if "\t" in raw:
        return raw.split("\t")
    if "|" in raw:
        return raw.split("|")
    if ";" in raw:
        return raw.split(";")
    return raw.split(",")


def parse_qr(raw: str) -> ScanResult:
    fields = [f.strip() for f in split_qr(raw)]
    if len(fields) <= 18:
        raise HTTPException(status_code=400, detail="QR data has insufficient fields; expected index 18")

    station = fields[17]
    if not STATION_PATTERN.match(station):
        raise HTTPException(status_code=400, detail="Invalid station code format")

    qty_raw = fields[6] or "0"
    try:
        qty = int(float(qty_raw))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid qty") from exc
    if qty <= 0:
        raise HTTPException(status_code=400, detail="qty must be > 0")

    rate_value = None
    if fields[9]:
        try:
            rate_value = float(fields[9])
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid rate")

    order_date = fields[15] or None
    if order_date:
        try:
            date.fromisoformat(order_date)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Invalid order date") from exc

    required = {
        "item_id": fields[0],
        "drug_code": fields[2],
        "hn": fields[16],
        "station_code": station,
    }
    for key, value in required.items():
        if not value:
            raise HTTPException(status_code=400, detail=f"Missing required field: {key}")

    return ScanResult(
        item_id=fields[0],
        patient_name=fields[1] or None,
        drug_code=fields[2],
        strength=fields[5] or None,
        qty=qty,
        rate=rate_value,
        diluent=fields[13] or None,
        administration=fields[14] or None,
        order_date=order_date,
        hn=fields[16],
        station_code=station,
        bed_no=fields[18] or None,
    )
