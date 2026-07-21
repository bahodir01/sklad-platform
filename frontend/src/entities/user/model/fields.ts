import type { FieldDescriptor } from "@/shared/lib/field-descriptor";

/**
 * users — из 02-contract.json ДОСЛОВНО (М7, ОВ-12, backend §14). Экран только
 * admin (RequireRole). password_hash никогда не выходит наружу (все 4 API-флага
 * false) — присутствует здесь только для полноты словаря, ни в колонках, ни в
 * составе форм не участвует.
 *
 * `password` (создание) НЕ является атрибутом словаря — backend/app/modules/
 * auth/schemas.py:UserCreate помечает его `__contract_extra_fields__`, т.к. в
 * БД лежит только password_hash. Форма создания добавляет поле password вручную
 * (см. features/users/user-form), не через listFieldNames/createFieldNames.
 */
export const userFields: FieldDescriptor[] = [
  {
    name: "id",
    label: "ID",
    input_type: "number",
    required: false,
    disabled: true,
    table_view: false,
    api: { get_index: true, get_single: true, create: false, update: false },
  },
  {
    name: "full_name",
    label: "ФИО",
    input_type: "text",
    required: true,
    max: 255,
    validations: "required; trim; 1..255",
    table_view: true,
    api: { get_index: true, get_single: true, create: true, update: true },
  },
  {
    name: "username",
    label: "Логин",
    input_type: "text",
    required: true,
    max: 150,
    validations: "required; unique (async check); 3..150; без пробелов",
    table_view: true,
    // update=false — логин не меняется (учётная константа, §14 backend).
    api: { get_index: true, get_single: true, create: true, update: false },
  },
  {
    name: "email",
    label: "Email",
    input_type: "email",
    required: false,
    max: 255,
    validations: "формат email; домен @npuu.uz (конфигурируемый); поле опционально",
    table_view: true,
    api: { get_index: true, get_single: true, create: true, update: true },
  },
  {
    name: "password_hash",
    label: "Хеш пароля",
    input_type: "password",
    required: true,
    table_view: false,
    validations: "на вход принимается plain password, хеш считает сервер",
    // Все флаги false — колонка никогда не выходит наружу и не приходит с клиента.
    api: { get_index: false, get_single: false, create: false, update: false },
  },
  {
    name: "role",
    label: "Роль",
    input_type: "select",
    required: true,
    validations: "required; при role=admin поле category скрывается и обнуляется",
    table_view: true,
    api: { get_index: true, get_single: true, create: true, update: true },
  },
  {
    name: "category",
    label: "Категория (касса)",
    input_type: "select",
    required: false,
    validations: "обязательно, если role != admin; запрещено, если role = admin",
    table_view: true,
    api: { get_index: true, get_single: true, create: true, update: true },
  },
  {
    name: "is_active",
    label: "Активен",
    input_type: "checkbox",
    required: false,
    table_view: true,
    // create=false — новый пользователь всегда активен по умолчанию на сервере;
    // отключение только через PATCH is_active=false (DELETE нет, стиль SV-8).
    api: { get_index: true, get_single: true, create: false, update: true },
  },
  {
    name: "created_at",
    label: "Создан",
    input_type: "date",
    required: false,
    disabled: true,
    table_view: false,
    api: { get_index: false, get_single: true, create: false, update: false },
  },
];
