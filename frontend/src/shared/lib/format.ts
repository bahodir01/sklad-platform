/**
 * Форматирование (§11). Локаль ru-RU, валюта UZS.
 *
 * money() заведён на этапе 1, хотя денежных экранов ещё нет: он должен
 * появиться РАНЬШЕ первого ручного toFixed(2), иначе округление расползётся.
 */

const dateFmt = new Intl.DateTimeFormat("ru-RU", {
  day: "2-digit",
  month: "2-digit",
  year: "numeric",
});

const dateTimeFmt = new Intl.DateTimeFormat("ru-RU", {
  day: "2-digit",
  month: "2-digit",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
});

const moneyFmt = new Intl.NumberFormat("ru-RU", {
  style: "currency",
  currency: "UZS",
  maximumFractionDigits: 2,
});

export function formatDate(value: string | Date | null | undefined): string {
  if (!value) return "—";
  const d = typeof value === "string" ? new Date(value) : value;
  if (Number.isNaN(d.getTime())) return "—";
  return dateFmt.format(d);
}

export function formatDateTime(value: string | Date | null | undefined): string {
  if (!value) return "—";
  const d = typeof value === "string" ? new Date(value) : value;
  if (Number.isNaN(d.getTime())) return "—";
  return dateTimeFmt.format(d);
}

export function formatMoney(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return "—";
  return moneyFmt.format(value);
}

/**
 * Деньги из строки-Decimal бэкенда (NUMERIC приходит строкой, К-I): парсим и
 * форматируем в UZS. Строка — а не number из JSON — чтобы не терять точность
 * до самого форматирования.
 */
export function formatMoneyStr(value: string | null | undefined): string {
  if (value == null || value === "") return "—";
  return formatMoney(Number(value));
}

const qtyFmt = new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 3 });

/** Количество из строки-Decimal (шт/кг/л) без валютного символа. */
export function formatQty(value: string | number | null | undefined): string {
  if (value == null || value === "") return "—";
  const n = typeof value === "string" ? Number(value) : value;
  if (Number.isNaN(n)) return "—";
  return qtyFmt.format(n);
}

/** Сегодняшняя дата в формате YYYY-MM-DD (значение по умолчанию для полей date). */
export function todayIso(): string {
  const d = new Date();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${d.getFullYear()}-${m}-${day}`;
}

/** true, если ISO-datetime приходится на сегодняшний день (для KPI «сегодня»). */
export function isToday(value: string | null | undefined): boolean {
  if (!value) return false;
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return false;
  const now = new Date();
  return (
    d.getFullYear() === now.getFullYear() &&
    d.getMonth() === now.getMonth() &&
    d.getDate() === now.getDate()
  );
}

/** Булево → текст (§11: цвет никогда не единственный сигнал). */
export function formatBool(value: boolean): string {
  return value ? "Да" : "Нет";
}
