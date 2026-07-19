import { useState } from "react";
import { toast } from "sonner";
import { Printer } from "lucide-react";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/shared/ui/dialog";
import { Button } from "@/shared/ui/button";
import { Skeleton } from "@/shared/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/shared/ui/table";
import { NotificationStatusBadge } from "@/entities/notification/ui/NotificationStatusBadge";
import { useNotification } from "@/entities/notification/api/queries";
import { useProductLookup } from "@/entities/product/lib/use-product-lookup";
import { useWarehouseLookup } from "@/entities/warehouse/lib/use-warehouse-lookup";
import { api } from "@/shared/api/client";
import { ApiError } from "@/shared/api/errors";
import { openBlobInNewTab } from "@/shared/lib/download";
import { formatDate, formatQty } from "@/shared/lib/format";

interface NotificationDetailDialogProps {
  id: number | null;
  onClose: () => void;
}

/**
 * Деталь уведомления (§6.1): шапка + строки с прогрессом закупки
 * (заявлено / приобретено / остаток к приобретению — расчётные поля AP-6) +
 * печать бланка PDF (GET /notifications/{id}/pdf, перепечатка безопасна).
 */
export function NotificationDetailDialog({ id, onClose }: NotificationDetailDialogProps) {
  const { data, isLoading, isError } = useNotification(id);
  const products = useProductLookup();
  const warehouses = useWarehouseLookup();
  const [printing, setPrinting] = useState(false);

  async function handlePrint() {
    if (id == null) return;
    setPrinting(true);
    try {
      const blob = await api.getBlob(`/notifications/${id}/pdf`);
      openBlobInNewTab(blob);
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Не удалось сформировать бланк");
    } finally {
      setPrinting(false);
    }
  }

  return (
    <Dialog open={id != null} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-h-[90vh] max-w-2xl overflow-y-auto">
        <DialogHeader>
          <DialogTitle>
            {data ? `Уведомление ${data.number}` : "Уведомление"}
          </DialogTitle>
        </DialogHeader>

        {isLoading ? (
          <div className="space-y-3">
            <Skeleton className="h-5 w-2/3" />
            <Skeleton className="h-24 w-full" />
          </div>
        ) : isError || !data ? (
          <p className="py-6 text-center text-sm text-muted-foreground">
            Не удалось загрузить уведомление.
          </p>
        ) : (
          <div className="space-y-4">
            <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
              <dt className="text-muted-foreground">Дата</dt>
              <dd>{formatDate(data.date)}</dd>
              <dt className="text-muted-foreground">Склад назначения</dt>
              <dd>{warehouses.name(data.warehouse_id)}</dd>
              <dt className="text-muted-foreground">Подразделение</dt>
              <dd>{data.division_name}</dd>
              <dt className="text-muted-foreground">Статус</dt>
              <dd>
                <NotificationStatusBadge status={data.status} />
              </dd>
            </dl>

            <div>
              <p className="mb-1 text-xs font-medium text-muted-foreground">Текст обращения</p>
              <p className="whitespace-pre-wrap rounded-md border bg-muted/30 p-3 text-sm">
                {data.body_text}
              </p>
            </div>

            {data.comment ? (
              <div>
                <p className="mb-1 text-xs font-medium text-muted-foreground">Обоснование</p>
                <p className="whitespace-pre-wrap text-sm">{data.comment}</p>
              </div>
            ) : null}

            <div>
              <p className="mb-2 text-sm font-medium">Позиции</p>
              <div className="rounded-lg border">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Товар</TableHead>
                      <TableHead className="text-right">Заявлено</TableHead>
                      <TableHead className="text-right">Приобретено</TableHead>
                      <TableHead className="text-right">Остаток</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {data.items.map((it) => (
                      <TableRow key={it.id}>
                        <TableCell>{products.name(it.product_id)}</TableCell>
                        <TableCell className="text-right tabular-nums">
                          {formatQty(it.qty_requested)}
                        </TableCell>
                        <TableCell className="text-right tabular-nums">
                          {formatQty(it.qty_purchased)}
                        </TableCell>
                        <TableCell className="text-right font-medium tabular-nums">
                          {formatQty(it.qty_remaining)}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            </div>

            <div className="flex justify-end">
              <Button variant="outline" onClick={handlePrint} disabled={printing}>
                <Printer className="h-4 w-4" />
                {printing ? "Формируется…" : "Печать бланка"}
              </Button>
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
