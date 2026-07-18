import type { FieldDescriptor } from "@/shared/lib/field-descriptor";

/**
 * products — из 02-contract.json ДОСЛОВНО (§8.2).
 * - unit_id: update=false → в правке поля НЕТ, ЕИ показывается статикой (К-E).
 * - колонка ЕИ резолвится из кэша units (К-F): в списке приходит только число.
 */
export const productFields: FieldDescriptor[] = [
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
    label: "Номенклатура",
    input_type: "text",
    required: true,
    max: 255,
    table_view: true,
    api: { get_index: true, get_single: true, create: true, update: true },
  },
  {
    name: "unit_id",
    label: "Единица измерения",
    input_type: "select",
    required: true,
    validations: "required; выбор только из активных ЕИ",
    table_view: true,
    // create=true, update=false — ЕИ товара после создания не меняется.
    api: { get_index: true, get_single: true, create: true, update: false },
  },
  {
    name: "sku",
    label: "Артикул",
    input_type: "text",
    required: false,
    max: 64,
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
