import { useState } from "react";
import { PlusCircle } from "lucide-react";
import { useNotifications } from "@/entities/notification/api/queries";
import { NotificationStatusBadge } from "@/entities/notification/ui/NotificationStatusBadge";
import type { NotificationListItem } from "@/entities/notification/model/types";
import { useWarehouseLookup } from "@/entities/warehouse/lib/use-warehouse-lookup";
import { AcquisitionCreateDialog } from "@/features/documents/acquisition-form/AcquisitionCreateDialog";
import { PageHeader } from "@/shared/ui/page-header";
import { DataTable, type Column } from "@/shared/ui/data-table";
import { TablePagination } from "@/shared/ui/table-pagination";
import { Button } from "@/shared/ui/button";
import { Label } from "@/shared/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/shared/ui/select";
import { usePageParams } from "@/shared/lib/use-page-params";
import { formatDate } from "@/shared/lib/format";

// «Открытые» уведомления к приобретению = draft (ещё ни одной закупки) ИЛИ
// in_progress (частично закуплено). closed приобретать нельзя (остаток 0, SV-7).
const ALL = "__open__";

/**
 * Приобретения (М2, admin, §6.2). Приобретение всегда проводится НА ОСНОВАНИИ
 * уведомления, поэтому экран — это список уведомлений: из строки открывается
 * форма приобретения с остатком к приобретению. Списка самих приобретений в API
 * нет (только POST). По умолчанию показываем все, кроме закрытых.
 */
export function AcquisitionsPage() {
  const { page, size, setPage, get, setFilter } = usePageParams();
  // Уведомление создаётся как draft и становится in_progress лишь после первой
  // частичной закупки — поэтому «к приобретению» это НЕ только in_progress.
  const status = get("status");
  const query = useNotifications({ page, size, status });
  const wh = useWarehouseLookup();
  const [acqFor, setAcqFor] = useState<number | null>(null);
  const data = query.data;

  // Без явного статуса скрываем закрытые (по ним приобретать нечего).
  const rows = (data?.items ?? []).filter((n) => (status ? true : n.status !== "closed"));

  const columns: Column<NotificationListItem>[] = [
    {
      key: "number",
      header: "№ уведомления",
      render: (n) => <span className="font-mono text-[12.5px]">{n.number}</span>,
    },
    { key: "date", header: "Дата", render: (n) => formatDate(n.date) },
    { key: "warehouse", header: "Склад назначения", render: (n) => wh.name(n.warehouse_id) },
    { key: "status", header: "Статус", render: (n) => <NotificationStatusBadge status={n.status} /> },
  ];

  return (
    <section>
      <PageHeader
        breadcrumb="Документы › Приобретения"
        title="Приобретения"
        subtitle="Проведение закупки на основании уведомления (контроль перезакупки на сервере)"
      />

      <div className="mb-4 flex items-center gap-2">
        <Label htmlFor="acq-status" className="text-muted-foreground">
          Статус
        </Label>
        <Select
          value={status ?? ALL}
          onValueChange={(v) => setFilter("status", v === ALL ? undefined : v)}
        >
          <SelectTrigger id="acq-status" className="w-56">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL}>Открытые (кроме закрытых)</SelectItem>
            <SelectItem value="draft">Черновик</SelectItem>
            <SelectItem value="in_progress">В работе</SelectItem>
            <SelectItem value="closed">Закрыто</SelectItem>
          </SelectContent>
        </Select>
      </div>

      <div className="rounded-lg border">
        <DataTable
          caption="Уведомления к приобретению"
          columns={columns}
          rows={rows}
          rowKey={(n) => n.id}
          isLoading={query.isLoading}
          isError={query.isError}
          onRetry={() => query.refetch()}
          emptyText="Нет уведомлений к приобретению"
          rowActions={(n) => (
            <Button
              size="sm"
              onClick={() => setAcqFor(n.id)}
              disabled={n.status === "closed"}
              title={n.status === "closed" ? "Уведомление закрыто — приобретать нечего" : undefined}
            >
              <PlusCircle className="h-4 w-4" />
              Провести
            </Button>
          )}
        />
      </div>

      {data ? (
        <TablePagination
          page={data.page}
          size={data.size}
          total={data.total}
          pages={data.pages}
          onPageChange={setPage}
        />
      ) : null}

      <AcquisitionCreateDialog notificationId={acqFor} onClose={() => setAcqFor(null)} />
    </section>
  );
}
