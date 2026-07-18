"""Sanity check that the test infrastructure itself (DB connection, seed
verification, autouse cleanup fixture) works before the real suites rely on it.
"""

from sqlalchemy import text


async def test_can_query_seed_admin(session):
    row = await session.execute(text("SELECT role FROM users WHERE id = 3"))
    assert row.scalar_one() == "admin"


async def test_clean_db_leaves_no_stock_movements(session):
    row = await session.execute(text("SELECT count(*) FROM stock_movements"))
    assert row.scalar_one() == 0
