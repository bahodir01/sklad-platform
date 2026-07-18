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

/** Булево → текст (§11: цвет никогда не единственный сигнал). */
export function formatBool(value: boolean): string {
  return value ? "Да" : "Нет";
}
