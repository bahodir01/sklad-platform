import type { FieldDescriptor } from "@/shared/lib/field-descriptor";

/**
 * warehouses — из 02-contract.json ДОСЛОВНО (§8.3). Несущий экран этапа 1.
 * - allows_issuance «Склад списания» — требование SV-9, с поясняющим текстом.
 * - address: get_index=false → в списке НЕТ, есть в детали/формах → диалог
 *   правки ОБЯЗАН догрузить GET /warehouses/{id} (К-H).
 */
export const warehouseFields: FieldDescriptor[] = [
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
    label: "Код склада",
    input_type: "text",
    required: true,
    max: 32,
    validations: "required; unique",
    table_view: true,
    api: { get_index: true, get_single: true, create: true, update: true },
  },
  {
    name: "name",
    label: "Наименование склада",
    input_type: "text",
    required: true,
    max: 255,
    table_view: true,
    api: { get_index: true, get_single: true, create: true, update: true },
  },
  {
    name: "address",
    label: "Адрес",
    input_type: "text",
    required: false,
    max: 500,
    table_view: false,
    // get_index=false — в списке адреса нет; есть в детали, создании и правке.
    api: { get_index: false, get_single: true, create: true, update: true },
  },
  {
    name: "allows_issuance",
    label: "Склад списания",
    input_type: "checkbox",
    required: false,
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
