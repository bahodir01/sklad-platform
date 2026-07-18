import type { FieldDescriptor } from "@/shared/lib/field-descriptor";

/**
 * units — переписано из 02-contract.json ДОСЛОВНО (§8.1). Таблица контракта:
 * units. UnitRead == UnitList → отдельного экрана детали нет, деталь = диалог
 * правки. `code` unique — проверки-эндпоинта нет, полагаемся на 422 duplicate.
 */
export const unitFields: FieldDescriptor[] = [
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
    name: "code",
    label: "Код ЕИ",
    input_type: "text",
    required: true,
    max: 16,
    validations: "required; unique; 1..16",
    table_view: true,
    api: { get_index: true, get_single: true, create: true, update: true },
  },
  {
    name: "name",
    label: "Наименование ЕИ",
    input_type: "text",
    required: true,
    max: 100,
    table_view: true,
    api: { get_index: true, get_single: true, create: true, update: true },
  },
  {
    name: "is_active",
    label: "Активна",
    input_type: "checkbox",
    required: false,
    table_view: true,
    // create=false: новая ЕИ активна по server_default. Архивация — через update.
    api: { get_index: true, get_single: true, create: false, update: true },
  },
];
