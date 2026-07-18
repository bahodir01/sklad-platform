import type { FieldDescriptor } from "@/shared/lib/field-descriptor";

/**
 * expense_types (расход ТОВАРА) — из 02-contract.json ДОСЛОВНО (§8.4).
 * НЕ путать с expense_categories (расход денег).
 * - requires_employee: required здесь = «обязано присутствовать в payload», НЕ
 *   «галочка должна быть отмечена» (для «Порчи»/«Брака» значение false). Zod:
 *   z.boolean() без .refine(v=>v===true) (К-B).
 * - подсказка disabled «при update, если есть проводки» нереализуема на этапе 1
 *   (нет признака в API) — чекбокс активен, запрет обеспечивает бэкенд (К-A).
 */
export const expenseTypeFields: FieldDescriptor[] = [
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
    name: "name",
    label: "Тип расхода товара",
    input_type: "text",
    required: true,
    max: 100,
    table_view: true,
    api: { get_index: true, get_single: true, create: true, update: true },
  },
  {
    name: "requires_employee",
    label: "Требует сотрудника",
    input_type: "checkbox",
    required: true,
    table_view: true,
    api: { get_index: true, get_single: true, create: true, update: true },
  },
  {
    name: "status",
    label: "Статус",
    input_type: "select",
    required: false,
    table_view: true,
    api: { get_index: true, get_single: true, create: false, update: true },
  },
];
