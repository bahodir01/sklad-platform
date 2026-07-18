"""БД-инварианты §5 ТЗ, проверенные НАПРЯМУЮ (в обход сервисного слоя).

Сервисные тесты (test_documents_*, test_issuance_flow, test_cash, test_writeoffs)
уже доказывают, что приложение НЕ нарушает эти правила. Этот модуль доказывает
вторую половину утверждения архитектуры §5 «дублируется constraint-ом в БД
там, где это возможно»: правило держится, даже если код его обойдёт (баг,
прямой SQL, будущая миграция). Раз БД — источник правды, тест обязан бить
напрямую по ней, а не только через сервис.
"""

import datetime as dt
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError

from app.core.database import SessionLocal
from tests import constants as c
from tests.conftest import TEST_PREFIX

TODAY = dt.date.today()


# ── INV-9: users.category IS NULL ⟺ users.role = 'admin' ────────────


async def test_inv9_admin_with_category_rejected():
    with pytest.raises(IntegrityError):
        async with SessionLocal() as s:
            await s.execute(
                text(
                    "INSERT INTO users (full_name, username, password_hash, role, category) "
                    "VALUES ('X', :u, 'x', 'admin', 'teacher')"
                ),
                {"u": f"{TEST_PREFIX}inv9_admin_with_cat"},
            )
            await s.commit()


async def test_inv9_non_admin_without_category_rejected():
    with pytest.raises(IntegrityError):
        async with SessionLocal() as s:
            await s.execute(
                text(
                    "INSERT INTO users (full_name, username, password_hash, role, category) "
                    "VALUES ('X', :u, 'x', 'teacher', NULL)"
                ),
                {"u": f"{TEST_PREFIX}inv9_teacher_no_cat"},
            )
            await s.commit()


async def test_inv9_valid_rows_accepted(session):
    """Контроль ложноположительных: корректные комбинации не должны падать."""
    async with SessionLocal() as s:
        await s.execute(
            text(
                "INSERT INTO users (full_name, username, password_hash, role, category) "
                "VALUES ('X', :u1, 'x', 'admin', NULL), "
                "('Y', :u2, 'x', 'worker', 'worker')"
            ),
            {"u1": f"{TEST_PREFIX}inv9_ok_admin", "u2": f"{TEST_PREFIX}inv9_ok_worker"},
        )
        await s.commit()
    cnt = await session.execute(
        text("SELECT count(*) FROM users WHERE username LIKE :p"), {"p": f"{TEST_PREFIX}inv9_ok%"}
    )
    assert cnt.scalar_one() == 2


# ── INV-1: stock_balances.qty >= 0 ────────────────────────────────────


async def test_inv1_negative_balance_rejected_at_db_level(session):
    # Строка баланса на существующем (product, warehouse) — можно создать
    # напрямую, минуя ledger, ровно для проверки того, что БД сама не
    # позволит уйти в минус даже если ledger когда-нибудь будет обойдён.
    await session.execute(
        text(
            "INSERT INTO stock_balances (product_id, warehouse_id, qty) "
            "VALUES (:p, :w, 0) "
            "ON CONFLICT (product_id, warehouse_id) DO UPDATE SET qty = 0"
        ),
        {"p": c.PRODUCT_ID, "w": c.WAREHOUSE_ISS},
    )
    await session.commit()

    with pytest.raises(IntegrityError):
        async with SessionLocal() as s:
            await s.execute(
                text("UPDATE stock_balances SET qty = -1 WHERE product_id=:p AND warehouse_id=:w"),
                {"p": c.PRODUCT_ID, "w": c.WAREHOUSE_ISS},
            )
            await s.commit()


# ── INV-6: qty > 0 во всех *_items ────────────────────────────────────


async def test_inv6_zero_qty_rejected_in_request_items():
    """request_items.qty CHECK > 0 — последний рубеж, даже если Pydantic
    (Field(gt=0)) когда-нибудь будет обойдён нестандартным путём вставки."""
    with pytest.raises(IntegrityError):
        async with SessionLocal() as s:
            await s.execute(
                text(
                    "INSERT INTO requests (number, employee_id, warehouse_id, reason) "
                    "VALUES ('REQ-INV6-TEST', :emp, :wh, 'test')"
                ),
                {"emp": c.TEACHER_ID, "wh": c.WAREHOUSE_ISS},
            )
            await s.execute(
                text(
                    "INSERT INTO request_items (request_id, product_id, qty) "
                    "SELECT id, :p, 0 FROM requests WHERE number='REQ-INV6-TEST'"
                ),
                {"p": c.PRODUCT_ID},
            )
            await s.commit()


# ── INV-4: writeoffs.employee_id IS NOT NULL ⟺ expense_types.requires_employee ──


async def test_inv4_employee_required_mismatch_rejected_at_db_level():
    """CHECK ck_writeoffs_employee_iff_required — прямая вставка в обход
    IssuanceService.create_writeoff: тип «Порча» (requires_employee=false)
    с указанным employee_id должна быть отвергнута БД."""
    with pytest.raises(IntegrityError):
        async with SessionLocal() as s:
            await s.execute(
                text(
                    "INSERT INTO writeoffs "
                    "(number, date, warehouse_id, expense_type_id, requires_employee, "
                    " employee_id, author_id) "
                    "VALUES ('WOFF-INV4-TEST', :d, :wh, :et, false, :emp, :author)"
                ),
                {
                    "d": TODAY,
                    "wh": c.WAREHOUSE_ISS,
                    "et": c.EXPENSE_TYPE_SPOILAGE,
                    "emp": c.TEACHER_ID,
                    "author": c.ADMIN_ID,
                },
            )
            await s.commit()


# ── INV-5: transfers.from_warehouse_id <> to_warehouse_id ────────────


async def test_inv5_same_warehouse_transfer_rejected_at_db_level():
    with pytest.raises(IntegrityError):
        async with SessionLocal() as s:
            await s.execute(
                text(
                    "INSERT INTO transfers (number, date, from_warehouse_id, to_warehouse_id, author_id) "
                    "VALUES ('TRF-INV5-TEST', :d, :wh, :wh, :a)"
                ),
                {"d": TODAY, "wh": c.WAREHOUSE_ISS, "a": c.ADMIN_ID},
            )
            await s.commit()


# ── SV-9: триггер requests_check_issuance_warehouse — момент подачи ──


async def test_sv9_trigger_rejects_direct_insert_into_non_issuance_warehouse(session):
    """Дополняет test_issuance_flow's SV-9 сервисный тест: доказывает, что
    правило живёт в БД (триггер), а не только в IssuanceService."""
    with pytest.raises(DBAPIError):
        async with SessionLocal() as s:
            await s.execute(
                text(
                    "INSERT INTO requests (number, employee_id, warehouse_id, reason) "
                    "VALUES ('REQ-SV9-DB-TEST', :emp, :wh, 'обход сервиса')"
                ),
                {"emp": c.TEACHER_ID, "wh": c.WAREHOUSE_NO},
            )
            await s.commit()

    cnt = await session.execute(
        text("SELECT count(*) FROM requests WHERE number = 'REQ-SV9-DB-TEST'")
    )
    assert cnt.scalar_one() == 0


async def test_sv9_trigger_does_not_invalidate_past_requests_when_flag_removed(session):
    """SV-9 уточнение: правило действует НА МОМЕНТ ПОДАЧИ. Снятие галочки
    allows_issuance с уже использованного склада НЕ должно ломать
    исторические заявки (иначе issue() у старых заявок стал бы невозможен)."""
    async with SessionLocal() as s:
        # Временный тестовый склад со списанием разрешённым — своя заявка,
        # затем снимаем галочку и проверяем, что заявка осталась читаемой
        # и её warehouse_id не меняется триггером задним числом.
        await s.execute(
            text(
                "INSERT INTO warehouses (code, name, allows_issuance, status) "
                "VALUES ('TEST_SV9_WH', 'Тестовый склад SV-9', true, 'active')"
            )
        )
        await s.commit()
        wh_id = await s.scalar(text("SELECT id FROM warehouses WHERE code='TEST_SV9_WH'"))

        await s.execute(
            text(
                "INSERT INTO requests (number, employee_id, warehouse_id, reason) "
                "VALUES ('REQ-SV9-HIST-TEST', :emp, :wh, 'историческая заявка')"
            ),
            {"emp": c.TEACHER_ID, "wh": wh_id},
        )
        await s.commit()

        # Снимаем галочку задним числом.
        await s.execute(
            text("UPDATE warehouses SET allows_issuance = false WHERE id=:wh"), {"wh": wh_id}
        )
        await s.commit()

    status = await session.scalar(
        text("SELECT status FROM requests WHERE number='REQ-SV9-HIST-TEST'")
    )
    assert status == "draft"  # заявка жива, триггер её не тронул задним числом

    # Очистка тестового склада — она НЕ входит в конвенцию TEST_CATALOG_PREFIX
    # автосвипа conftest (warehouses чистятся по code LIKE 'TEST_%', так что
    # фактически подметается автоматически). Убеждаемся явно на всякий случай.
    async with SessionLocal() as s:
        await s.execute(text("DELETE FROM requests WHERE number='REQ-SV9-HIST-TEST'"))
        await s.execute(text("DELETE FROM warehouses WHERE id=:wh"), {"wh": wh_id})
        await s.commit()
