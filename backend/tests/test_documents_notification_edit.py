"""М2 «Документооборот товаров» — редактирование, отправка в работу и
удаление уведомлений (ОВ-11, решение заказчика 19.07.2026).

Покрывает:
  * submit         — draft → in_progress (единственный путь, не приобретение);
  * SV-10 PATCH    — черновик: правится всё; в работе: только аддитивно
                     (тексты + добавление строк/увеличение qty), запрет на
                     смену date/warehouse_id, уменьшение qty ниже приобретённого
                     и удаление строк с приобретениями; закрыт: ничего;
  * SV-11 DELETE   — удаление ⟺ нет ни одного приобретения.
"""

import datetime as dt
from decimal import Decimal

import pytest

from app.core.database import SessionLocal
from app.core.exceptions import DomainError
from app.modules.documents.schemas import (
    AcquisitionCreate,
    AcquisitionItemCreate,
    NotificationCreate,
    NotificationItemCreate,
    NotificationItemUpdate,
    NotificationUpdate,
)
from app.modules.documents.service import DocumentsService
from tests import constants as c

TODAY = dt.date.today()
TOMORROW = TODAY + dt.timedelta(days=1)


# ── фикстуры / хелперы ──────────────────────────────────────────────


@pytest.fixture
async def second_product(session) -> int:
    """Второй товар (TEST_-префикс, подметается clean_db) — нужен там, где
    проверяется добавление/удаление СТРОК уведомления (сид даёт лишь product 1)."""
    from app.modules.catalog.models import Product

    p = Product(name=f"{c.TEST if hasattr(c, 'TEST') else 'TEST_'}Ручка", unit_id=c.UNIT_ID)
    # имя обязано начинаться с TEST_ — иначе clean_db не подметёт
    p.name = "TEST_Ручка шариковая"
    session.add(p)
    await session.commit()
    await session.refresh(p)
    return p.id


async def _create(items: list[tuple[int, str]], *, warehouse_id: int = c.WAREHOUSE_ISS) -> int:
    async with SessionLocal() as s:
        notif = await DocumentsService(s).create_notification(
            author_id=c.ADMIN_ID,
            payload=NotificationCreate(
                date=TODAY,
                warehouse_id=warehouse_id,
                body_text="Sizdan quyidagi tovarlarni ajratishingizni so'rayman:",
                division_name="Bo'lim A",
                comment="исходный комментарий",
                items=[
                    NotificationItemCreate(product_id=pid, qty_requested=Decimal(q))
                    for pid, q in items
                ],
            ),
        )
        return notif.id


async def _submit(nid: int):
    async with SessionLocal() as s:
        return await DocumentsService(s).submit_notification(nid)


async def _acquire(nid: int, items: list[tuple[int, str]], *, warehouse_id: int = c.WAREHOUSE_ISS):
    async with SessionLocal() as s:
        return await DocumentsService(s).create_acquisition(
            author_id=c.ADMIN_ID,
            payload=AcquisitionCreate(
                date=TODAY,
                notification_id=nid,
                warehouse_id=warehouse_id,
                supplier="ООО Поставки",
                items=[AcquisitionItemCreate(product_id=pid, qty=Decimal(q)) for pid, q in items],
            ),
        )


async def _patch(nid: int, **kwargs):
    async with SessionLocal() as s:
        return await DocumentsService(s).update_notification(nid, NotificationUpdate(**kwargs))


async def _delete(nid: int):
    async with SessionLocal() as s:
        await DocumentsService(s).delete_notification(nid)


async def _detail(nid: int):
    """{product_id: qty_requested} + сама шапка (для чтения текстовых полей)."""
    async with SessionLocal() as s:
        notif = await DocumentsService(s).get_notification_detail(nid)
        qmap = {it.product_id: it.qty_requested for it in notif.items}
        return notif, qmap


# ══════════════════ 1. Черновик: править всё ════════════════════════


async def test_draft_patch_edits_everything(second_product):
    """Черновик: PATCH меняет тексты, дату, склад, кол-во и состав строк."""
    nid = await _create([(c.PRODUCT_ID, "10")])

    await _patch(
        nid,
        date=TOMORROW,
        warehouse_id=c.WAREHOUSE_NO,
        body_text="Новый текст обращения",
        division_name="Bo'lim B",
        comment="новый комментарий",
        items=[
            NotificationItemUpdate(product_id=c.PRODUCT_ID, qty_requested=Decimal("5")),
            NotificationItemUpdate(product_id=second_product, qty_requested=Decimal("3")),
        ],
    )

    notif, qmap = await _detail(nid)
    assert notif.status.value == "draft"
    assert notif.date == TOMORROW
    assert notif.warehouse_id == c.WAREHOUSE_NO
    assert notif.body_text == "Новый текст обращения"
    assert notif.division_name == "Bo'lim B"
    assert notif.comment == "новый комментарий"
    assert qmap == {c.PRODUCT_ID: Decimal("5.000"), second_product: Decimal("3.000")}


async def test_draft_patch_removes_row(second_product):
    """Черновик: строку можно удалить (передав желаемое состояние без неё)."""
    nid = await _create([(c.PRODUCT_ID, "10"), (second_product, "4")])
    await _patch(nid, items=[NotificationItemUpdate(product_id=second_product, qty_requested=Decimal("4"))])

    _, qmap = await _detail(nid)
    assert qmap == {second_product: Decimal("4.000")}


async def test_draft_patch_partial_touches_only_provided():
    """PATCH частичный: не переданные поля остаются нетронутыми."""
    nid = await _create([(c.PRODUCT_ID, "10")])
    await _patch(nid, comment="только комментарий")

    notif, qmap = await _detail(nid)
    assert notif.comment == "только комментарий"
    assert notif.division_name == "Bo'lim A"  # не тронуто
    assert qmap == {c.PRODUCT_ID: Decimal("10.000")}  # строки не тронуты


# ══════════════════ 2. submit + гейт приобретений ═══════════════════


async def test_submit_then_acquire_ok():
    """draft→submit→in_progress; приобретение против in_progress проходит."""
    nid = await _create([(c.PRODUCT_ID, "10")])
    notif = await _submit(nid)
    assert notif.status.value == "in_progress"
    acq = await _acquire(nid, [(c.PRODUCT_ID, "4")])
    assert acq.number.startswith("ACQ-")


async def test_submit_rejects_non_draft():
    """submit возможен только из черновика; повторный submit → отказ."""
    nid = await _create([(c.PRODUCT_ID, "10")])
    await _submit(nid)
    with pytest.raises(DomainError) as exc:
        await _submit(nid)
    assert exc.value.code == "notification_not_draft"


# ══════════════════ 3. В работе: только аддитивно (SV-10) ═══════════


async def test_in_progress_increase_qty_and_add_row(second_product):
    """В работе: увеличить qty и добавить новую строку — успех."""
    nid = await _create([(c.PRODUCT_ID, "10")])
    await _submit(nid)
    await _acquire(nid, [(c.PRODUCT_ID, "4")])  # приобретено 4

    await _patch(nid, items=[
        NotificationItemUpdate(product_id=c.PRODUCT_ID, qty_requested=Decimal("20")),
        NotificationItemUpdate(product_id=second_product, qty_requested=Decimal("5")),
    ])
    _, qmap = await _detail(nid)
    assert qmap == {c.PRODUCT_ID: Decimal("20.000"), second_product: Decimal("5.000")}


async def test_in_progress_reduce_qty_below_purchased_rejected():
    """В работе: qty ниже уже приобретённого — отказ (qty_below_purchased)."""
    nid = await _create([(c.PRODUCT_ID, "10")])
    await _submit(nid)
    await _acquire(nid, [(c.PRODUCT_ID, "4")])  # приобретено 4

    with pytest.raises(DomainError) as exc:
        await _patch(nid, items=[NotificationItemUpdate(product_id=c.PRODUCT_ID, qty_requested=Decimal("3"))])
    assert exc.value.code == "qty_below_purchased"

    _, qmap = await _detail(nid)
    assert qmap == {c.PRODUCT_ID: Decimal("10.000")}  # отказ ничего не изменил


async def test_in_progress_reduce_qty_to_purchased_floor_ok():
    """В работе: снизить qty ровно до приобретённого (не НИЖЕ) — допустимо."""
    nid = await _create([(c.PRODUCT_ID, "10")])
    await _submit(nid)
    await _acquire(nid, [(c.PRODUCT_ID, "4")])

    await _patch(nid, items=[NotificationItemUpdate(product_id=c.PRODUCT_ID, qty_requested=Decimal("4"))])
    _, qmap = await _detail(nid)
    assert qmap == {c.PRODUCT_ID: Decimal("4.000")}


async def test_in_progress_delete_row_with_acquisitions_rejected(second_product):
    """В работе: удалить строку, по которой есть приобретения — отказ."""
    nid = await _create([(c.PRODUCT_ID, "10"), (second_product, "5")])
    await _submit(nid)
    await _acquire(nid, [(c.PRODUCT_ID, "4")])  # у product1 есть закупка

    # Желаемое состояние без product1 = попытка удалить строку с приобретением.
    with pytest.raises(DomainError) as exc:
        await _patch(nid, items=[NotificationItemUpdate(product_id=second_product, qty_requested=Decimal("5"))])
    assert exc.value.code == "item_has_acquisitions"


async def test_in_progress_delete_row_without_acquisitions_ok(second_product):
    """В работе: строку БЕЗ приобретений удалить можно."""
    nid = await _create([(c.PRODUCT_ID, "10"), (second_product, "5")])
    await _submit(nid)
    await _acquire(nid, [(c.PRODUCT_ID, "4")])  # закупка только по product1

    # Убираем second_product (по нему закупок нет) — оставляем product1.
    await _patch(nid, items=[NotificationItemUpdate(product_id=c.PRODUCT_ID, qty_requested=Decimal("10"))])
    _, qmap = await _detail(nid)
    assert qmap == {c.PRODUCT_ID: Decimal("10.000")}


async def test_in_progress_change_warehouse_rejected():
    """В работе: сменить склад назначения — отказ (notification_field_locked)."""
    nid = await _create([(c.PRODUCT_ID, "10")])
    await _submit(nid)
    with pytest.raises(DomainError) as exc:
        await _patch(nid, warehouse_id=c.WAREHOUSE_NO)
    assert exc.value.code == "notification_field_locked"


async def test_in_progress_change_date_rejected():
    """В работе: сменить дату — отказ (в allow-list SV-10 её нет)."""
    nid = await _create([(c.PRODUCT_ID, "10")])
    await _submit(nid)
    with pytest.raises(DomainError) as exc:
        await _patch(nid, date=TOMORROW)
    assert exc.value.code == "notification_field_locked"


async def test_in_progress_edit_texts_ok():
    """В работе: тексты (comment/body_text/division_name) правятся свободно."""
    nid = await _create([(c.PRODUCT_ID, "10")])
    await _submit(nid)
    await _patch(nid, comment="upd", body_text="upd body", division_name="upd div")
    notif, _ = await _detail(nid)
    assert (notif.comment, notif.body_text, notif.division_name) == ("upd", "upd body", "upd div")


# ══════════════════ 4. Удаление (SV-11) ════════════════════════════


async def test_delete_draft():
    """Черновик удаляется (приобретений нет по определению)."""
    nid = await _create([(c.PRODUCT_ID, "10")])
    await _delete(nid)
    with pytest.raises(DomainError) as exc:
        await _detail(nid)
    assert exc.value.code == "not_found"


async def test_delete_in_progress_without_acquisitions():
    """В работе без приобретений — документ инертен, удаляется."""
    nid = await _create([(c.PRODUCT_ID, "10")])
    await _submit(nid)
    await _delete(nid)
    with pytest.raises(DomainError) as exc:
        await _detail(nid)
    assert exc.value.code == "not_found"


async def test_delete_in_progress_with_acquisitions_rejected(session):
    """В работе с приобретением — удалять нельзя (движения склада append-only)."""
    nid = await _create([(c.PRODUCT_ID, "10")])
    await _submit(nid)
    await _acquire(nid, [(c.PRODUCT_ID, "4")])

    with pytest.raises(DomainError) as exc:
        await _delete(nid)
    assert exc.value.code == "notification_has_acquisitions"

    # Уведомление на месте.
    notif, _ = await _detail(nid)
    assert notif.id == nid


async def test_delete_cascades_items(session):
    """Удаление уведомления уносит его notification_items (CASCADE)."""
    from sqlalchemy import text

    nid = await _create([(c.PRODUCT_ID, "10")])
    await _delete(nid)
    left = await session.execute(
        text("SELECT count(*) FROM notification_items WHERE notification_id=:n"), {"n": nid}
    )
    assert left.scalar_one() == 0


# ══════════════════ 5. Закрыт: правки запрещены ════════════════════


async def test_closed_patch_rejected():
    """Закрытое уведомление (всё приобретено, SV-7) — любые правки отклоняются."""
    nid = await _create([(c.PRODUCT_ID, "10")])
    await _submit(nid)
    await _acquire(nid, [(c.PRODUCT_ID, "10")])  # SV-7 → closed

    notif, _ = await _detail(nid)
    assert notif.status.value == "closed"

    with pytest.raises(DomainError) as exc:
        await _patch(nid, comment="поздно")
    assert exc.value.code == "notification_closed"
