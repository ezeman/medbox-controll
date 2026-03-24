import re
from datetime import date

from fastapi import HTTPException

from .schemas import ScanResult

STATION_PATTERN = re.compile(r"^S\d{3}$")
TIMESTAMP_NOISE_PATTERN = re.compile(r"\d{1,2}:\d{2}|\d{1,2}/\d{1,2}/\d{2,4}|\*-")

BARCODE_IDX = 0
DRUG_NAME_IDX = 1
DRUG_STRENGTH_IDX = 4
DRUG_AMOUNT_IDX = 5
RATE_IDX = 8
DILUENT_IDX = 12
ADMINISTRATION_IDX = 13
PRODUCE_DATE_IDX = 14
HN_IDX = 15
DESTINATION_IDX = 16
BED_NO_IDX = 17


def split_qr(raw: str) -> list[str]:
    normalized_raw = raw.replace("\n", " ").replace("\r", " ").strip()
    # Production scanner payloads are comma-delimited and may include tab chars
    # inside one field, so comma must be the first delimiter we try.
    if "," in normalized_raw:
        return normalized_raw.split(",")
    if "\t" in normalized_raw:
        return normalized_raw.split("\t")
    if "|" in raw:
        return normalized_raw.split("|")
    if ";" in raw:
        return normalized_raw.split(";")
    return [normalized_raw]


def clean_field(value: str) -> str:
    return value.strip().strip('"').strip("'")


def should_drop_field_one(fields: list[str]) -> bool:
    if len(fields) <= 1:
        return False

    candidate = fields[1]
    return bool(candidate and TIMESTAMP_NOISE_PATTERN.search(candidate))


def normalize_fields(raw: str) -> list[str]:
    fields = [clean_field(f) for f in split_qr(raw)]
    if should_drop_field_one(fields):
        return [fields[0], *fields[2:]]
    return fields


def get_field(fields: list[str], index: int) -> str:
    if index >= len(fields):
        return ""
    return fields[index]


def parse_qr(raw: str) -> ScanResult:
    fields = normalize_fields(raw)
    if len(fields) <= DESTINATION_IDX:
        raise HTTPException(status_code=400, detail="QR data has insufficient fields after cleanup; expected destination field")

    station = get_field(fields, DESTINATION_IDX).upper()
    if not STATION_PATTERN.match(station):
        raise HTTPException(status_code=400, detail="Invalid station code format")

    qty_raw = get_field(fields, DRUG_AMOUNT_IDX) or "0"
    try:
        qty = int(float(qty_raw))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid qty") from exc
    if qty <= 0:
        raise HTTPException(status_code=400, detail="qty must be > 0")

    rate_value = None
    if get_field(fields, RATE_IDX):
        try:
            rate_value = float(get_field(fields, RATE_IDX))
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid rate")

    order_date = get_field(fields, PRODUCE_DATE_IDX) or None
    if order_date:
        try:
            date.fromisoformat(order_date)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Invalid order date") from exc

    barcode = get_field(fields, BARCODE_IDX)
    drug_name = get_field(fields, DRUG_NAME_IDX)
    hn = get_field(fields, HN_IDX).upper()

    required = {
        "item_id": barcode,
        "drug_code": drug_name,
        "hn": hn,
        "station_code": station,
    }
    for key, value in required.items():
        if not value:
            raise HTTPException(status_code=400, detail=f"Missing required field: {key}")

    return ScanResult(
        item_id=barcode,
        patient_name=None,
        drug_code=drug_name,
        strength=get_field(fields, DRUG_STRENGTH_IDX) or None,
        qty=qty,
        rate=rate_value,
        diluent=get_field(fields, DILUENT_IDX) or None,
        administration=get_field(fields, ADMINISTRATION_IDX) or None,
        order_date=order_date,
        hn=hn,
        station_code=station,
        bed_no=get_field(fields, BED_NO_IDX) or None,
    )
