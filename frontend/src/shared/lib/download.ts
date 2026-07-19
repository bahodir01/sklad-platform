/**
 * Открыть/скачать бинарный ответ API. PDF и экспорт отчётов приходят blob'ом
 * через api.getBlob (Authorization: Bearer в памяти — window.open не отправил бы
 * заголовок, поэтому качаем клиентом и открываем object URL).
 */

/** Открыть blob (PDF/HTML-бланк) в новой вкладке. */
export function openBlobInNewTab(blob: Blob): void {
  const url = URL.createObjectURL(blob);
  window.open(url, "_blank", "noopener");
  // Отзываем URL позже — вкладке нужно успеть его прочитать.
  setTimeout(() => URL.revokeObjectURL(url), 60_000);
}

/** Скачать blob как файл с заданным именем (экспорт xlsx/pdf). */
export function downloadBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 60_000);
}
