"""Бизнес-правила М5: приход и расход денег. Транзакция открывается здесь
(архитектура §2). Единственный контроль, который эта система обязана дать по
деньгам, — не уйти в минус (INV-8, ОВ-2 жёсткая блокировка) и не провести
расход без чека (INV-7).

Контроль баланса кассы (§5.4, AP-9) — дословно по архитектуре:

    create_expense(...):
        BEGIN
        SELECT balance FROM cash_desks WHERE id = ? FOR UPDATE
        IF balance < amount: RAISE InsufficientFunds     # ОВ-2 жёсткая блокировка
        проверить наличие прикреплённого чека             # INV-7
        INSERT money_expense; UPDATE cash_desks SET balance = balance - amount
        COMMIT

Два места, где легко ошибиться и оба закрыты:
  * SV-6 — кассу берёт СЕРВЕР из users.category, клиент её не присылает. Иначе
    учитель списал бы из кассы работников, подделав тело запроса.
  * FOR UPDATE ОБЯЗАТЕЛЕН. Без него два параллельных расхода прочитают один и тот
    же баланс, оба пройдут проверку и оба спишут — уход в минус при гонке. CHECK
    (balance >= 0) в БД — последний рубеж, но пользователю нужен внятный текст, а
    не 500 из IntegrityError, поэтому проверка живёт в сервисе под блокировкой.
"""

import datetime as dt
import uuid
from decimal import Decimal

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import (
    DomainError,
    ForbiddenError,
    InsufficientFunds,
    NotFoundError,
    ValidationError,
)
from app.modules.auth.models import User
from app.modules.cash.models import CashDesk, MoneyExpense, MoneyIncome
from app.modules.cash.repository import CashRepository
from app.modules.cash.schemas import MoneyExpenseSubmission, MoneyIncomeCreate
from app.modules.catalog.models import ExpenseCategory
from app.shared.enums import CashDeskType, CatalogStatus
from app.shared.numbering import next_document_number
from app.shared.pagination import PageParams
from app.shared.storage import put_object, sniff_receipt

_ZERO = Decimal("0")
_REGISTER_PREFIX = "MREG-"  # реестр передачи денег (спека13 §4; отдельно от товара)


class CashService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = CashRepository(session)

    # ══════════════════ Балансы касс (AP-9) ═════════════════════════

    async def list_desks(self) -> list[CashDesk]:
        return await self._repo.list_desks()

    # ══════════════════ Приход — admin only (§7.2) ══════════════════

    async def create_income(
        self, *, author_id: int, payload: MoneyIncomeCreate
    ) -> MoneyIncome:
        """POST /cash/income. Пополнение кассы. +balance под FOR UPDATE.

        Блокировка строки кассы нужна и на приходе: без неё параллельный приход и
        расход (или два прихода) прочитают один баланс и один из апдейтов
        потеряется (lost update). FOR UPDATE сериализует изменения баланса.
        """
        desk = await self._session.scalar(
            select(CashDesk).where(CashDesk.id == payload.cash_desk_id).with_for_update()
        )
        if desk is None:
            raise NotFoundError("Касса", payload.cash_desk_id)

        income = MoneyIncome(
            cash_desk_id=desk.id,
            amount=payload.amount,
            date=payload.date,
            author_id=author_id,
            comment=payload.comment,
        )
        self._session.add(income)
        desk.balance = desk.balance + payload.amount
        await self._commit()
        await self._session.refresh(income)
        return income

    # ══════════════════ Расход — сотрудник (§5.4) ═══════════════════

    async def create_expense(
        self,
        *,
        user: User,
        payload: MoneyExpenseSubmission,
        receipt_bytes: bytes,
    ) -> MoneyExpense:
        """POST /cash/expenses. Порядок строго по §5.4 — переставлять нельзя.

        1. SV-6: касса — из user.category, НЕ с клиента.
        2. INV-7: чек обязателен — валидируем magic bytes/размер ДО любой записи.
        3. Вид расхода существует и активен (чистая ошибка + нет осиротевшего файла).
        4. SELECT ... FOR UPDATE по кассе.
        5. balance < amount → InsufficientFunds (файл ещё не сохранён, баланс цел).
        6. Сохранить чек в MinIO (фолбэк локальный) → receipt_url.
        7. INSERT money_expense; UPDATE balance = balance - amount.
        """
        # ── 1. SV-6: касса определяется сервером из категории сотрудника ──
        if user.category is None:
            # admin (category IS NULL, INV-9) кассы сотрудника не имеет — расход
            # проводит сотрудник teacher/worker. Роль отсекается и в роутере.
            raise ForbiddenError(
                "Расход из кассы доступен только сотрудникам категорий "
                "«teacher»/«worker» (SV-6)"
            )
        desk_type = CashDeskType(user.category.value)

        # ── 2. INV-7: чек обязателен, whitelist jpg/png/pdf по magic bytes ──
        content_type, ext = self._validate_receipt(receipt_bytes)

        # ── 3. Вид расхода денег существует и активен ──
        category = await self._session.get(ExpenseCategory, payload.expense_category_id)
        if category is None:
            raise NotFoundError("Вид расхода денег", payload.expense_category_id)
        if category.status != CatalogStatus.active:
            raise ValidationError(
                "Вид расхода денег архивирован — списание по нему невозможно",
                code="expense_category_archived",
            )

        # ── 4. FOR UPDATE по кассе (SV-3-аналог для денег, AP-9) ──
        desk = await self._session.scalar(
            select(CashDesk).where(CashDesk.type == desk_type).with_for_update()
        )
        if desk is None:  # pragma: no cover — кассы засижены начальной миграцией
            raise NotFoundError("Касса", desk_type.value)

        # ── 5. ОВ-2 жёсткая блокировка: не уходим в минус ──
        if desk.balance < payload.amount:
            # Файл ещё не сохранён, INSERT не сделан — баланс кассы не тронут.
            raise InsufficientFunds(
                available=desk.balance,
                requested=payload.amount,
                desk=desk_type.value,
            )

        # ── 6. Чек в MinIO (бакет receipts). Ключ одинаков и в фолбэке. ──
        key = f"expenses/{dt.date.today():%Y/%m}/{uuid.uuid4().hex}.{ext}"
        receipt_url = put_object(
            settings.s3_bucket_receipts, key, receipt_bytes, content_type=content_type
        )
        if not receipt_url or not receipt_url.strip():  # pragma: no cover
            # INV-7 в коде: put_object обязан вернуть непустой ключ. Пустой ключ
            # обошёл бы NOT NULL и чек стал бы фикцией — CHECK в БД это тоже ловит.
            raise ValidationError("Не удалось сохранить чек", code="receipt_store_failed")

        # ── 7. Проводка расхода + списание с баланса, одной транзакцией ──
        expense = MoneyExpense(
            cash_desk_id=desk.id,
            employee_id=user.id,
            expense_category_id=category.id,
            amount=payload.amount,
            description=payload.description,
            receipt_url=receipt_url,
            date=payload.date,
        )
        self._session.add(expense)
        desk.balance = desk.balance - payload.amount
        await self._commit()
        await self._session.refresh(expense)
        return expense

    # ══════════════════ «Мои расходы» (row-level, §1.3) ═════════════

    async def list_my_expenses(
        self, params: PageParams, *, employee_id: int
    ) -> tuple[list[MoneyExpense], int]:
        """GET /cash/expenses/my — ТОЛЬКО расходы текущего сотрудника (§1.3).

        Фильтр по employee_id живёт в сервисе, а не только в UI: сотрудник не
        должен видеть чужие расходы, даже обращаясь к эндпоинту напрямую.
        """
        return await self._repo.list_expenses(
            params, filters=[MoneyExpense.employee_id == employee_id]
        )

    # ══════════════════ Передача в бухгалтерию (admin, спека13 §4) ═══

    async def list_expenses(
        self, params: PageParams, *, submitted: bool | None = None
    ) -> tuple[list[MoneyExpense], int]:
        """GET /cash/expenses (admin) — все расходы, фильтр «Передано/Не передано».

        submitted=True → submitted_at IS NOT NULL; False → IS NULL (actionable-набор,
        частичный индекс ix_money_expense_not_submitted); None → все.
        """
        filters: list = []
        if submitted is True:
            filters.append(MoneyExpense.submitted_at.is_not(None))
        elif submitted is False:
            filters.append(MoneyExpense.submitted_at.is_(None))
        return await self._repo.list_expenses(params, filters=filters or None)

    async def submit_to_accounting(
        self, *, ids: list[int]
    ) -> tuple[str | None, list[int], list[int]]:
        """POST /cash/expenses/submit-to-accounting — bulk-передача (спека13 §4).

        У денег НЕТ этапа подписи (чек заменяет §7.3): расход готов к передаче
        сразу после проведения. Общий submitted_register_no на весь вызов;
        submitted_at = сегодня. Условие submitted_at IS NULL в UPDATE защищает от
        повторной передачи (исключённые/уже переданные → skipped).
        """
        if not ids:
            return None, [], []
        # FOR UPDATE по ещё не переданным расходам из списка.
        locked = await self._session.scalars(
            select(MoneyExpense)
            .where(
                MoneyExpense.id.in_(ids),
                MoneyExpense.submitted_at.is_(None),
            )
            .order_by(MoneyExpense.id)
            .with_for_update()
        )
        submit_ids = [e.id for e in locked]
        skipped_ids = [i for i in ids if i not in set(submit_ids)]
        if not submit_ids:
            return None, [], skipped_ids

        register_no = await next_document_number(
            self._session, MoneyExpense.submitted_register_no, prefix=_REGISTER_PREFIX
        )
        await self._session.execute(
            update(MoneyExpense)
            .where(
                MoneyExpense.id.in_(submit_ids),
                MoneyExpense.submitted_at.is_(None),
            )
            .values(submitted_at=dt.date.today(), submitted_register_no=register_no)
            .execution_options(synchronize_session=False)
        )
        await self._commit()
        return register_no, submit_ids, skipped_ids

    async def registry(
        self,
        params: PageParams,
        *,
        register_no: str | None = None,
        date: dt.date | None = None,
    ) -> tuple[list[MoneyExpense], int]:
        """Реестр передачи денег по register_no / дате (спека13 §4)."""
        filters: list = []
        if register_no:
            filters.append(MoneyExpense.submitted_register_no == register_no)
        if date:
            filters.append(MoneyExpense.submitted_at == date)
        return await self._repo.registry(params, filters=filters or None)

    # ══════════════════ Общее ═══════════════════════════════════════

    @staticmethod
    def _validate_receipt(data: bytes) -> tuple[str, str]:
        """INV-7 + ТЗ §7: чек обязателен, whitelist jpg/png/pdf по magic bytes,
        лимит 10 МБ. Возвращает (content_type, ext) или бросает ValidationError."""
        if not data:
            raise ValidationError(
                "Чек обязателен: файл не приложен (INV-7)", code="receipt_required"
            )
        limit = settings.s3_max_upload_bytes
        if len(data) > limit:
            raise ValidationError(
                f"Чек превышает лимит {limit // (1024 * 1024)} МБ",
                code="receipt_too_large",
            )
        sniffed = sniff_receipt(data)
        if sniffed is None:
            # Проверка по СОДЕРЖИМОМУ, не по расширению/Content-Type (ТЗ §7):
            # и то и другое клиент подделывает.
            raise ValidationError(
                "Недопустимый формат чека: разрешены JPG, PNG, PDF "
                "(проверка по содержимому файла)",
                code="receipt_bad_type",
            )
        return sniffed

    async def _commit(self) -> None:
        try:
            await self._session.commit()
        except IntegrityError as exc:
            await self._session.rollback()
            raise _translate_integrity_error(exc) from exc


def _translate_integrity_error(exc: IntegrityError) -> DomainError:
    """Отказ constraint-а → русский текст (архитектура §6), а не 500."""
    text = str(getattr(exc, "orig", exc)).lower()
    if "ck_cash_desks_balance_non_negative" in text:
        # INV-8, последний рубеж: сюда доходить не должны (сервис ловит раньше
        # под FOR UPDATE), но если гонка обошла проверку — это не 500.
        return ValidationError(
            "Операция увела бы баланс кассы в минус (INV-8)", code="negative_balance"
        )
    if "ck_money_expense_receipt_not_blank" in text:
        return ValidationError("Чек обязателен (INV-7)", code="receipt_required")
    if "ck_money_expense_description_not_blank" in text:
        return ValidationError("Описание расхода не может быть пустым")
    if "ck_money_expense_amount_positive" in text or "ck_money_income_amount_positive" in text:
        return ValidationError("Сумма должна быть больше нуля")
    if "foreign key" in text:
        return ValidationError(
            "Указана несуществующая связанная запись", code="fk_violation"
        )
    if "check constraint" in text:
        return ValidationError("Значения полей нарушают правила учёта")
    return ValidationError("Операция отклонена базой данных")
