"""Pydantic v2-схемы М2. Состав задают API-флаги 02-contract.json, ДОСЛОВНО.

Правило: поле в XxxCreate ⟺ api.create=true, в XxxRead ⟺ api.get_single=true,
в XxxList ⟺ api.get_index=true. Вложенные строки (`items`) и вычисляемые
величины («остаток к приобретению») колонками не являются — они разрешены
валидатору контракта явным `__contract_extra_fields__`.

Карта флагов (перенос из контракта):

  notifications      id  number date author_id warehouse_id status  → List
                     + comment body_text division_name pdf_url created_at → Read
                     create: date, warehouse_id, comment, body_text, division_name
                     update: — (нет ни одного update=true → схемы Update нет)
  notification_items create: product_id, qty_requested
                     read:   id, notification_id, product_id, qty_requested
  acquisitions       read:   id number date notification_id warehouse_id supplier author_id
                     create: date, notification_id, warehouse_id, supplier
  acquisition_items  create: product_id, qty, price
                     read:   id, acquisition_id, product_id, qty, price
  transfers          read:   id number date from_warehouse_id to_warehouse_id author_id
                     create: date, from_warehouse_id, to_warehouse_id
  transfer_items     create: product_id, qty
                     read:   id, transfer_id, product_id, qty
"""

import datetime as dt
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.shared.enums import NotificationStatus

# ── notification_items ──────────────────────────────────────────────


class NotificationItemCreate(BaseModel):
    product_id: int
    qty_requested: Decimal = Field(gt=0, description="Заявлено, > 0 (INV-6)")


class NotificationItemRead(BaseModel):
    """get_single-поля строки + вычисляемый прогресс закупки.

    qty_purchased/qty_remaining НЕ хранятся (ТЗ §3): считаются из
    acquisition_items и проставляются сервисом на инстанс перед сериализацией.
    Колонками они не являются → в whitelist контракта.
    """

    model_config = ConfigDict(from_attributes=True)
    __contract_extra_fields__ = {"qty_purchased", "qty_remaining"}

    id: int
    notification_id: int
    product_id: int
    qty_requested: Decimal
    qty_purchased: Decimal | None = None
    qty_remaining: Decimal | None = None


# ── notifications ───────────────────────────────────────────────────


class NotificationCreate(BaseModel):
    __contract_extra_fields__ = {"items"}

    date: dt.date
    warehouse_id: int
    body_text: str = Field(min_length=1, description="Абзац-обращение бланка")
    division_name: str = Field(min_length=1, max_length=255, description="Bo‘linma nomi")
    comment: str | None = Field(default=None, description="Ehtiyojning asoslanishi")
    items: list[NotificationItemCreate] = Field(min_length=1)


class NotificationList(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    number: str
    date: dt.date
    author_id: int
    warehouse_id: int
    status: NotificationStatus


class NotificationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    __contract_extra_fields__ = {"items"}

    id: int
    number: str
    date: dt.date
    author_id: int
    warehouse_id: int
    status: NotificationStatus
    comment: str | None
    body_text: str
    division_name: str
    pdf_url: str | None
    created_at: dt.datetime
    items: list[NotificationItemRead] = []


# ── acquisition_items ───────────────────────────────────────────────


class AcquisitionItemCreate(BaseModel):
    product_id: int
    qty: Decimal = Field(gt=0, description="Приобретено, > 0 (INV-6)")
    price: Decimal | None = Field(default=None, ge=0, description="Цена за ед., UZS")


class AcquisitionItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    acquisition_id: int
    product_id: int
    qty: Decimal
    price: Decimal | None


# ── acquisitions ────────────────────────────────────────────────────


class AcquisitionCreate(BaseModel):
    __contract_extra_fields__ = {"items"}

    date: dt.date
    notification_id: int
    warehouse_id: int
    supplier: str | None = Field(default=None, max_length=255)
    items: list[AcquisitionItemCreate] = Field(min_length=1)


class AcquisitionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    __contract_extra_fields__ = {"items"}

    id: int
    number: str
    date: dt.date
    notification_id: int
    warehouse_id: int
    supplier: str | None
    author_id: int
    items: list[AcquisitionItemRead] = []


# ── transfer_items ──────────────────────────────────────────────────


class TransferItemCreate(BaseModel):
    product_id: int
    qty: Decimal = Field(gt=0, description="Перемещено, > 0 (INV-6)")


class TransferItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    transfer_id: int
    product_id: int
    qty: Decimal


# ── transfers ───────────────────────────────────────────────────────


class TransferCreate(BaseModel):
    __contract_extra_fields__ = {"items"}

    date: dt.date
    from_warehouse_id: int
    to_warehouse_id: int
    items: list[TransferItemCreate] = Field(min_length=1)


class TransferRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    __contract_extra_fields__ = {"items"}

    id: int
    number: str
    date: dt.date
    from_warehouse_id: int
    to_warehouse_id: int
    author_id: int
    items: list[TransferItemRead] = []
