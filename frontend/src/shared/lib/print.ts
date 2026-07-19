/**
 * Печать реестра/списка передачи (спека13 §4). Реестр — печатная форма-
 * доказательство передачи в бухгалтерию: бухгалтерия расписывается в получении.
 * Серверного PDF реестра нет — строки приходят JSON'ом (GET .../registry), поэтому
 * рисуем чистую печатную HTML-форму в новом окне из РЕАЛЬНЫХ строк ответа и
 * зовём window.print(). Никаких выдуманных данных: только то, что отдал бэкенд.
 */

export interface PrintColumn<T> {
  header: string;
  value: (row: T) => string;
  align?: "left" | "right";
}

function escapeHtml(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

/**
 * Открыть печатную форму реестра в новом окне и вызвать печать.
 * @param title   Заголовок формы (напр. «Реестр передачи в бухгалтерию»).
 * @param subtitle Подзаголовок (номер реестра/дата) — опционально.
 * @param columns Колонки печатной таблицы.
 * @param rows    Строки (реальные данные ответа API).
 */
export function printRegistry<T>(
  title: string,
  subtitle: string | undefined,
  columns: PrintColumn<T>[],
  rows: T[],
): void {
  const win = window.open("", "_blank", "noopener,width=900,height=700");
  if (!win) return;

  const head = columns
    .map(
      (c) =>
        `<th style="text-align:${c.align ?? "left"}">${escapeHtml(c.header)}</th>`,
    )
    .join("");

  const body = rows
    .map(
      (r) =>
        "<tr>" +
        columns
          .map(
            (c) =>
              `<td style="text-align:${c.align ?? "left"}">${escapeHtml(c.value(r))}</td>`,
          )
          .join("") +
        "</tr>",
    )
    .join("");

  const printedAt = new Intl.DateTimeFormat("ru-RU", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date());

  win.document.write(`<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8" />
<title>${escapeHtml(title)}</title>
<style>
  * { box-sizing: border-box; }
  body { font-family: system-ui, "Segoe UI", Arial, sans-serif; color: #111; margin: 32px; }
  h1 { font-size: 18px; margin: 0 0 4px; }
  .sub { font-size: 12px; color: #555; margin: 0 0 16px; }
  table { width: 100%; border-collapse: collapse; font-size: 12px; }
  th, td { border: 1px solid #888; padding: 6px 8px; }
  th { background: #f0f0f0; }
  .meta { margin-top: 24px; font-size: 12px; color: #555; }
  .sign { margin-top: 40px; font-size: 12px; }
  .sign-line { display: inline-block; width: 260px; border-bottom: 1px solid #111; margin-left: 8px; }
  @media print { .noprint { display: none; } }
</style>
</head>
<body>
  <h1>${escapeHtml(title)}</h1>
  ${subtitle ? `<p class="sub">${escapeHtml(subtitle)}</p>` : ""}
  <table>
    <thead><tr>${head}</tr></thead>
    <tbody>${body || `<tr><td colspan="${columns.length}" style="text-align:center">Нет строк</td></tr>`}</tbody>
  </table>
  <p class="meta">Всего строк: ${rows.length}. Сформировано: ${escapeHtml(printedAt)}.</p>
  <p class="sign">Сдал: <span class="sign-line"></span>&nbsp;&nbsp;&nbsp;Принял (бухгалтерия): <span class="sign-line"></span></p>
</body>
</html>`);
  win.document.close();
  win.focus();
  // Дать окну отрисоваться перед печатью.
  setTimeout(() => win.print(), 300);
}
