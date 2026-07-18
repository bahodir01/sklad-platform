"""Fixed seed identifiers this suite relies on — never created/edited by tests.

Seeded by the initial Alembic migration (cash_desks, warehouses, expense_types)
plus `python -m app.seed` / manual setup for the admin/teacher users used
during backend verification (см. .feature-dev/07-qa-tests.md «Как запустить»):

    unit id=1            (code=sht)
    product id=1          (Бумага, unit_id=1)
    warehouse id=1 = W-ISS  (allows_issuance=true,  status=active)
    warehouse id=2 = W-NO   (allows_issuance=false, status=active)
    expense_type id=1 = Выдача  (requires_employee=true,  status=active)
    expense_type id=2 = Порча   (requires_employee=false, status=active)
    user id=3 = admin     (role=admin,   category=NULL)
    user id=4 = teach1    (role=teacher, category=teacher)
    cash_desk id=1 = teacher (balance starts at 0.00 before/after every test)
    cash_desk id=2 = worker  (balance starts at 0.00 before/after every test)

If any of these is missing, tests/conftest.py's `verify_seed_data` fixture
fails collection early with a clear message instead of letting every test
fail confusingly against a half-empty database.
"""

UNIT_ID = 1
PRODUCT_ID = 1

WAREHOUSE_ISS = 1  # W-ISS, allows_issuance=true  — заявки МОЖНО подавать
WAREHOUSE_NO = 2  # W-NO,  allows_issuance=false — заявки НЕЛЬЗЯ подавать

EXPENSE_TYPE_ISSUANCE = 1  # «Выдача», requires_employee=true
EXPENSE_TYPE_SPOILAGE = 2  # «Порча»,  requires_employee=false

ADMIN_ID = 3
TEACHER_ID = 4

CASH_DESK_TEACHER = 1
CASH_DESK_WORKER = 2

# Прочие тестовые сущности (worker-пользователь, категории расходов денег)
# создаются фикстурами с префиксом TEST_PREFIX/TEST_CATALOG_PREFIX из conftest —
# автоочистка подметает всё, что начинается с этих префиксов.
