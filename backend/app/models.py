from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


class Slot(Base):
    __tablename__ = "slots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    status: Mapped[str] = mapped_column(String(32), default="empty")
    station_code: Mapped[str | None] = mapped_column(String(16), nullable=True)
    current_batch_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class SlotBatch(Base):
    __tablename__ = "slot_batches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    slot_id: Mapped[int] = mapped_column(ForeignKey("slots.id"), nullable=False)
    station_code: Mapped[str | None] = mapped_column(String(16), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="selected")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    items = relationship("BottleScan", back_populates="batch", cascade="all,delete-orphan")


class BottleScan(Base):
    __tablename__ = "bottle_scans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey("slot_batches.id"), nullable=False)
    qr_raw: Mapped[str] = mapped_column(String(1024), nullable=False)
    item_id: Mapped[str] = mapped_column(String(64), nullable=False)
    patient_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    drug_code: Mapped[str] = mapped_column(String(64), nullable=False)
    strength: Mapped[str | None] = mapped_column(String(128), nullable=True)
    qty: Mapped[int] = mapped_column(Integer, nullable=False)
    rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    diluent: Mapped[str | None] = mapped_column(String(128), nullable=True)
    administration: Mapped[str | None] = mapped_column(String(64), nullable=True)
    order_date: Mapped[str | None] = mapped_column(String(32), nullable=True)
    hn: Mapped[str] = mapped_column(String(64), nullable=False)
    station_code: Mapped[str] = mapped_column(String(16), nullable=False)
    bed_no: Mapped[str | None] = mapped_column(String(64), nullable=True)
    scanned_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    batch = relationship("SlotBatch", back_populates="items")

    __table_args__ = (UniqueConstraint("batch_id", "item_id", name="uq_batch_item"),)


class RemovalLog(Base):
    __tablename__ = "removal_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    slot_id: Mapped[int] = mapped_column(Integer, nullable=False)
    batch_id: Mapped[int] = mapped_column(Integer, nullable=False)
    item_id: Mapped[str] = mapped_column(String(64), nullable=False)
    drug_code: Mapped[str] = mapped_column(String(64), nullable=False)
    hn: Mapped[str] = mapped_column(String(64), nullable=False)
    station_code: Mapped[str] = mapped_column(String(16), nullable=False)
    removed_by: Mapped[str] = mapped_column(String(32), default="scan")
    removed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Mission(Base):
    __tablename__ = "missions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey("slot_batches.id"), nullable=False)
    slot_id: Mapped[int] = mapped_column(Integer, nullable=False)
    station_code: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="sent")
    robot_mission_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class RelayLog(Base):
    __tablename__ = "relay_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    slot_id: Mapped[int] = mapped_column(Integer, nullable=False)
    action: Mapped[str] = mapped_column(String(32), default="open")
    result: Mapped[str] = mapped_column(String(32), default="ok")
    detail: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
