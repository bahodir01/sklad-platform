/**
 * Дескриптор поля (§4). Массив таких дескрипторов в entities/<x>/model/fields.ts
 * переписан из 02-contract.json ДОСЛОВНО и является единственным источником для:
 *   1. колонок таблицы  — filter(f => f.api.get_index && f.table_view)
 *   2. состава форм      — filter(f => f.api.create) / filter(f => f.api.update)
 *   3. ui_manifest.json  — генерируется scripts/build-ui-manifest.ts
 *
 * Дрейф между UI и контрактом становится невозможен по построению.
 */

export type InputType = "text" | "number" | "select" | "date" | "checkbox" | "email" | "password";

export interface ApiFlags {
  /** I — приходит в списке. */
  get_index: boolean;
  /** S — приходит в детали. */
  get_single: boolean;
  /** C — принимается на создании. */
  create: boolean;
  /** U — принимается на правке. */
  update: boolean;
}

export interface FieldDescriptor {
  /** Имя атрибута контракта — ДОСЛОВНО (в API и в манифесте). */
  name: string;
  /** Человекочитаемый label из контракта. */
  label: string;
  input_type: InputType;
  required: boolean;
  /** max length/value из контракта, если задан. */
  max?: number;
  /** disabled из frontend-блока (редко; чаще выражено через API-флаги). */
  disabled?: boolean;
  /** Текст правил валидации из контракта — справочно. */
  validations?: string;
  /** table_view '✓' → true, '—' → false. Колонка = get_index ∧ table_view (Ф-6). */
  table_view: boolean;
  api: ApiFlags;
}

/** Имена атрибутов, попадающих в список (колонки). */
export function listFieldNames(fields: FieldDescriptor[]): string[] {
  return fields.filter((f) => f.api.get_index && f.table_view).map((f) => f.name);
}

/** Имена атрибутов формы создания. */
export function createFieldNames(fields: FieldDescriptor[]): string[] {
  return fields.filter((f) => f.api.create).map((f) => f.name);
}

/** Имена атрибутов формы правки. */
export function updateFieldNames(fields: FieldDescriptor[]): string[] {
  return fields.filter((f) => f.api.update).map((f) => f.name);
}

export function fieldByName(fields: FieldDescriptor[], name: string): FieldDescriptor {
  const found = fields.find((f) => f.name === name);
  if (!found) throw new Error(`Дескриптор поля '${name}' не найден`);
  return found;
}
