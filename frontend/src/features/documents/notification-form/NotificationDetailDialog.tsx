import { useState } from "react";
import { toast } from "sonner";
import { Printer, Send, Pencil, Trash2 } from "lucide-react";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/shared/ui/dialog";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/shared/ui/alert-dialog";
import { Button } from "@/shared/ui/button";
import { Skeleton } from "@/shared/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/shared/ui/table";
import { NotificationStatusBadge } from "@/entities/notification/ui/NotificationStatusBadge";
import { useNotification } from "@/entities/notification/api/queries";
import {
  useSubmitNotification,
  useDeleteNotification,
} from "@/entities/notification/api/mutations";
import { useProductLookup } from "@/entities/product/lib/use-product-lookup";
import { useWarehouseLookup } from "@/entities/warehouse/lib/use-warehouse-lookup";
import { api } from "@/shared/api/client";
import { ApiError } from "@/shared/api/errors";
import { applyApiError } from "@/shared/lib/apply-api-error";
import { openBlobInNewTab } from "@/shared/lib/download";
import { formatDate, formatQty } from "@/shared/lib/format";
import { NotificationEditDialog } from "./NotificationEditDialog";

interface NotificationDetailDialogProps {
  id: number | null;
  onClose: () => void;
}

/**
 * Деталь уведомления (§6.1): шапка + строки с прогрессом закупки
 * (заявлено / приобретено / остаток к приобретению — расчётные поля AP-6) +
 * печать бланка PDF (GET /notifications/{id}/pdf, перепечатка безопасна).
 *
 * Действия ОВ-11:
 *   • «Отправить в работу» (POST /submit) — только для черновика.
 *   • «Редактировать» (PATCH) — для черновика и «в работе» (гейтинг в форме).
 *   • «Удалить» (DELETE) — только когда нет приобретений (SV-11).
 */
export function NotificationDetailDialog({ id, onClose }: NotificationDetailDialogProps) {
  const { data, isLoading, isError } = useNotification(id);
  const products = useProductLookup();
  const warehouses = useWarehouseLookup();
  const [printing, setPrinting] = useState(false);
  const [editId, setEditId] = useState<number | null>(null);
  const [confirmDelete, setConfirmDelete] = useState(false);

  const submit = useSubmitNotification();
  const del = useDeleteNotification();

  // Признак «есть приобретения» — по расчётному qty_purchased строк детали (AP-6).
  // Пустой список позиций трактуем как «нельзя удалить» — нечего проверять.
  const hasAcquisitions =
    (data?.items ?? []).some((it) => Number(it.qty_purchased ?? 0) > 0) ||
    (data != null && data.items.length === 0);
  const canDelete = data != null && !hasAcquisitions;

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

  function handleSubmit() {
    if (id == null) return;
    submit.mutate(id, {
      onSuccess: (n) => toast.success(`Уведомление ${n.number} отправлено в работу`),
      onError: (e) => applyApiError(e),
    });
  }

  function handleDelete() {
    if (id == null) return;
    del.mutate(id, {
      onSuccess: () => {
        toast.success("Уведомление удалено");
        setConfirmDelete(false);
        onClose();
      },
      onError: (e) => {
        setConfirmDelete(false);
        applyApiError(e);
      },
    });
  }

  return (
    <Dialog open={id != null} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-h-[90vh] max-w-2xl overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{data ? `Уведомление ${data.number}` : "Уведомление"}</DialogTitle>
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

            <div className="flex flex-wrap items-center justify-between gap-2 border-t pt-4">
              <Button variant="outline" onClick={handlePrint} disabled={printing}>
                <Printer className="h-4 w-4" />
                {printing ? "Формируется…" : "Печать бланка"}
              </Button>

              <div className="flex flex-wrap items-center gap-2">
                {data.status === "draft" ? (
                  <Button onClick={handleSubmit} disabled={submit.isPending}>
                    <Send className="h-4 w-4" />
                    {submit.isPending ? "Отправка…" : "Отправить в работу"}
                  </Button>
                ) : null}

                {data.status !== "closed" ? (
                  <Button variant="outline" onClick={() => setEditId(data.id)}>
                    <Pencil className="h-4 w-4" />
                    Редактировать
                  </Button>
                ) : null}

                <AlertDialog open={confirmDelete} onOpenChange={setConfirmDelete}>
                  <AlertDialogTrigger asChild>
                    <Button
                      variant="destructive"
                      disabled={!canDelete || del.isPending}
                      title={
                        canDelete
                          ? undefined
                          : "Удалить нельзя: у уведомления есть приобретения"
                      }
                    >
                      <Trash2 className="h-4 w-4" />
                      Удалить
                    </Button>
                  </AlertDialogTrigger>
                  <AlertDialogContent>
                    <AlertDialogHeader>
                      <AlertDialogTitle>Удалить уведомление?</AlertDialogTitle>
                      <AlertDialogDescription>
                        Уведомление {data.number} будет удалено вместе со своими позициями.
                        Действие необратимо. Разрешено только когда нет ни одного приобретения.
                      </AlertDialogDescription>
                    </AlertDialogHeader>
                    <AlertDialogFooter>
                      <AlertDialogCancel disabled={del.isPending}>Отмена</AlertDialogCancel>
                      <AlertDialogAction
                        onClick={(e) => {
                          e.preventDefault();
                          handleDelete();
                        }}
                        disabled={del.isPending}
                      >
                        {del.isPending ? "Удаление…" : "Удалить"}
                      </AlertDialogAction>
                    </AlertDialogFooter>
                  </AlertDialogContent>
                </AlertDialog>
              </div>
            </div>

            {!canDelete ? (
              <p className="text-right text-xs text-muted-foreground">
                Удалить нельзя: у уведомления есть приобретения.
              </p>
            ) : null}
          </div>
        )}
      </DialogContent>

      <NotificationEditDialog id={editId} onClose={() => setEditId(null)} />
    </Dialog>
  );
}
