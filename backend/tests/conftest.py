"""Pytest infrastructure for the sklad backend regression suite.

Architecture §9 ("Тестирование") prescribes pytest + testcontainers running
against a REAL PostgreSQL 16 — much of the domain logic in this codebase lives
inside `SELECT ... FOR UPDATE` row locks and *immediate* (non-DEFERRABLE)
CHECK constraints that a SQLite substitute cannot enforce (see
tests/test_issuance_flow.py::test_double_issue_race for the sharpest example:
it only proves anything against a database that actually serialises
concurrent transactions).

Docker is not available in this development environment, so this conftest
uses the documented fallback: it talks to an already-running, already
migrated + seeded PostgreSQL 16 via `DATABASE_URL`, exactly like the throwaway
verification scripts this suite formalises into permanent tests
(stage2_scenarios.py / stage3_scenarios.py / verify_stage45.py /
verify_reports.py — see .feature-dev/07-qa-tests.md for where they live and
how their scenarios map onto these test modules).

    CI must instead spin up testcontainers.postgres.PostgresContainer("postgres:16")
    (already a dev-dependency in pyproject.toml), run `alembic upgrade head`,
    seed the fixed rows tests/constants.py documents, export DATABASE_URL from
    the container, and only then invoke pytest. See .feature-dev/07-qa-tests.md
    §"CI" for the exact wiring.

Isolation strategy — read before adding a test
------------------------------------------------
Every service under test opens its OWN `AsyncSession` per call via
`app.core.database.SessionLocal()` — this mirrors "one HTTP request = one
transaction" (architecture §2) and is how `issue()` / `create_expense()` /
etc. are actually invoked in production; concurrency tests need this to open
genuinely independent connections anyway. Because sessions are created deep
inside the service layer rather than injected, wrapping each test in an
outer SAVEPOINT (the usual SQLAlchemy pytest pattern) is not viable here
without monkeypatching the sessionmaker — and the task brief for this suite
explicitly sanctions the fallback used below.

Instead: every test drives the real service layer with its own session(s),
and an autouse fixture truncates every TRANSACTIONAL table (movements,
balances, documents, requests, writeoffs, money) and resets both cash
balances to 0 — both BEFORE and AFTER each test — mirroring
`reset_state()`/`cleanup()` in the ad-hoc scripts. Seed data (see
tests/constants.py) is never touched. A test that needs a catalog row or user
beyond the seed (e.g. a worker, an extra expense category) MUST name it with
the `TEST_PREFIX`/`TEST_CATALOG_PREFIX` convention below so the same fixture
sweeps it up too — otherwise it leaks into the next test run.
"""

from __future__ import annotations

import os

# Same defaults the ad-hoc verification scripts used — set BEFORE importing
# anything under app.*, since app.core.config.Settings() reads the process
# environment once at import time (lru_cache'd).
os.environ.setdefault(
    "DATABASE_URL", "postgresql+asyncpg://postgres:postgres@127.0.0.1:5433/sklad"
)
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-key-for-local-verification-32b")
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-local-verification-only-32b")
os.environ.setdefault("PYTHONIOENCODING", "utf-8")

from collections.abc import AsyncIterator

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

import app.models  # noqa: F401 — registers cross-module relationships once
from app.core.database import SessionLocal, engine
from tests import constants as c

# Convention every test that needs extra rows beyond the fixed seed must
# follow — see module docstring.
TEST_PREFIX = "test_"  # usernames
TEST_CATALOG_PREFIX = "TEST_"  # product names / warehouse codes / expense_* names

# Every table populated by documents/issuance/cash flows. Order matters only
# in that FK-dependent children must not survive a partial failure — TRUNCATE
# ... CASCADE handles that regardless of listed order, but the explicit list
# documents exactly what "transactional" means in this suite.
_TRANSACTIONAL_TABLES = (
    "writeoff_items",
    "writeoffs",
    "request_items",
    "requests",
    "transfer_items",
    "transfers",
    "acquisition_items",
    "acquisitions",
    "notification_items",
    "notifications",
    "stock_movements",
    "stock_balances",
    "money_expense",
    "money_income",
    "audit_log",
)


async def _reset_transactional_state() -> None:
    """Truncate everything a test could have written, reset cash balances to
    0, and delete TEST_-prefixed catalog rows / test_-prefixed users. Seed
    data (tests/constants.py) is never touched — see module docstring."""
    async with engine.begin() as conn:
        await conn.execute(
            text(f"TRUNCATE {', '.join(_TRANSACTIONAL_TABLES)} RESTART IDENTITY CASCADE")
        )
        await conn.execute(text("UPDATE cash_desks SET balance = 0"))
        await conn.execute(
            text("DELETE FROM users WHERE username LIKE :p"), {"p": f"{TEST_PREFIX}%"}
        )
        await conn.execute(
            text("DELETE FROM expense_categories WHERE name LIKE :p"),
            {"p": f"{TEST_CATALOG_PREFIX}%"},
        )
        await conn.execute(
            text("DELETE FROM expense_types WHERE name LIKE :p"),
            {"p": f"{TEST_CATALOG_PREFIX}%"},
        )
        await conn.execute(
            text("DELETE FROM warehouses WHERE code LIKE :p"),
            {"p": f"{TEST_CATALOG_PREFIX}%"},
        )
        await conn.execute(
            text("DELETE FROM products WHERE name LIKE :p"),
            {"p": f"{TEST_CATALOG_PREFIX}%"},
        )


@pytest.fixture(scope="session", autouse=True)
async def verify_seed_data() -> None:
    """Fail collection early and clearly if the fixed seed rows are missing,
    instead of letting every single test fail with a confusing NotFoundError.
    """
    async with SessionLocal() as session:
        users = dict(
            (row.id, (row.role, row.category))
            for row in (
                await session.execute(
                    text("SELECT id, role, category FROM users WHERE id IN (3, 4)")
                )
            )
        )
        warehouses = dict(
            (row.id, (row.code, row.allows_issuance))
            for row in (
                await session.execute(
                    text("SELECT id, code, allows_issuance FROM warehouses WHERE id IN (1, 2)")
                )
            )
        )
        desks = {
            row.id
            for row in (await session.execute(text("SELECT id FROM cash_desks")))
        }
    problems = []
    if users.get(c.ADMIN_ID, (None,))[0] != "admin":
        problems.append(f"users.id={c.ADMIN_ID} должен быть role=admin")
    if users.get(c.TEACHER_ID, (None,))[0] != "teacher":
        problems.append(f"users.id={c.TEACHER_ID} должен быть role=teacher")
    if warehouses.get(c.WAREHOUSE_ISS, (None, None)) != ("W-ISS", True):
        problems.append(f"warehouses.id={c.WAREHOUSE_ISS} должен быть W-ISS, allows_issuance=true")
    if warehouses.get(c.WAREHOUSE_NO, (None, None))[1] is not False:
        problems.append(f"warehouses.id={c.WAREHOUSE_NO} должен быть allows_issuance=false")
    if {c.CASH_DESK_TEACHER, c.CASH_DESK_WORKER} - desks:
        problems.append("cash_desks должны содержать id=1 (teacher) и id=2 (worker)")
    if problems:
        pytest.exit(
            "Сиды БД не соответствуют tests/constants.py — тесты не запущены:\n  "
            + "\n  ".join(problems)
        )


@pytest.fixture(autouse=True)
async def clean_db() -> AsyncIterator[None]:
    """Runs before AND after every test — see module docstring."""
    await _reset_transactional_state()
    yield
    await _reset_transactional_state()


@pytest.fixture
async def session() -> AsyncIterator[AsyncSession]:
    """One ad-hoc session for assertions / raw setup in a test body.

    Services under test open THEIR OWN sessions (see module docstring) — this
    fixture is only for the test's own reads/writes around those calls.
    """
    async with SessionLocal() as s:
        yield s


@pytest.fixture
def new_session():
    """Factory so a test can open several independent sessions explicitly,
    mirroring one-session-per-service-call/request like production does.
    Needed by every concurrency test (two `asyncio.gather`ed calls must not
    share a session, or they wouldn't actually race)."""
    return SessionLocal


# ── Shared cross-module fixtures (cash + reports both need these) ────────


@pytest.fixture
async def expense_category(session: AsyncSession) -> int:
    """A TEST_-prefixed expense_categories row (money-expense category, not
    to be confused with catalog.ExpenseType). Swept up by clean_db."""
    from app.modules.catalog.models import ExpenseCategory

    cat = ExpenseCategory(name=f"{TEST_CATALOG_PREFIX}Канцелярия")
    session.add(cat)
    await session.commit()
    await session.refresh(cat)
    return cat.id


@pytest.fixture
async def worker_user(session: AsyncSession) -> int:
    """The seed only has an admin (id=3) and a teacher (id=4) — no worker.
    Tests that need one create it with the `test_` username prefix so
    clean_db sweeps it up automatically."""
    from app.core.security import hash_password
    from app.modules.auth.models import User
    from app.shared.enums import UserCategory, UserRole

    worker = User(
        full_name="Тестовый Работник",
        username=f"{TEST_PREFIX}worker",
        password_hash=hash_password("x"),
        role=UserRole.worker,
        category=UserCategory.worker,
        is_active=True,
    )
    session.add(worker)
    await session.commit()
    await session.refresh(worker)
    return worker.id
