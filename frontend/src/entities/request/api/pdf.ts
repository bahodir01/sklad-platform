import { api } from "@/shared/api/client";
import { openBlobInNewTab } from "@/shared/lib/download";

/**
 * Открыть PDF пачки печати (спека13 §3): GET /requests/batches/{id}/pdf — один
 * документ, сгруппированный по сотрудникам. Blob'ом, потому что Authorization —
 * Bearer в памяти (window.open не отправил бы заголовок). Фолбэк бэка отдаёт
 * HTML, если WeasyPrint без нативных либ — вкладка всё равно печатается.
 */
export async function openBatchPdf(batchId: number): Promise<void> {
  const blob = await api.getBlob(`/requests/batches/${batchId}/pdf`);
  openBlobInNewTab(blob);
}

/** Перепечать копии одной заявки (спека13 §5): GET /requests/{id}/pdf. */
export async function openRequestPdf(requestId: number): Promise<void> {
  const blob = await api.getBlob(`/requests/${requestId}/pdf`);
  openBlobInNewTab(blob);
}
