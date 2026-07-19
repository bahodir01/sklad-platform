import { useState } from "react";
import { Eye } from "lucide-react";
import { useNotifications } from "@/entities/notification/api/queries";
import { NotificationStatusBadge } from "@/entities/notification/ui/NotificationStatusBadge";
import type { NotificationListItem } from "@/entities/notification/model/types";
import { useWarehouseLookup } from "@/entities/warehouse/lib/use-warehouse-lookup";
import { NotificationCreateDialog } from "@/features/documents/notification-form/NotificationCreateDialog";
import { NotificationDetailDialog } from "@/features/documents/notification-form/NotificationDetailDialog";
import { PageHeader } from "@/shared/ui/page-header";
import { DataTable, type Column } from "@/shared/ui/data-table";
import { TablePagination } from "@/shared/ui/table-pagination";
import { Button } from "@/shared/ui/button";
import { Label } from "@/shared/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/shared/ui/select";
import { usePageParams } from "@/shared/lib/use-page-params";
import { formatDate } from "@/shared/lib/format";

const ALL = "__all__";

/**
 * Список уведомлений (М2, admin, §6.1). Фильтр по статусу, создание бланка,
 * просмотр детали со строками (остаток к приобретению) и печатью PDF.
 */
export function NotificationsPage() {
  const { page, size, setPage, get, setFilter } = usePageParams();
  const status = get("status");
  const query = useNotifications({ page, size, status });
  const wh = useWarehouseLookup();
  const [detailId, setDetailId] = useState<number | null>(null);
  const data = query.data;

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
        breadcrumb="Документы › Уведомления"
        title="Уведомления"
        subtitle="Заявки на закупку (BILDIRISHNOMA) — основание для приобретений"
        actions={<NotificationCreateDialog />}
      />

      <div className="mb-4 flex items-center gap-2">
        <Label htmlFor="filter-status" className="text-muted-foreground">
          Статус
        </Label>
        <Select
          value={status ?? ALL}
          onValueChange={(v) => setFilter("status", v === ALL ? undefined : v)}
        >
          <SelectTrigger id="filter-status" className="w-48">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL}>Все</SelectItem>
            <SelectItem value="draft">Черновик</SelectItem>
            <SelectItem value="in_progress">В работе</SelectItem>
            <SelectItem value="closed">Закрыто</SelectItem>
          </SelectContent>
        </Select>
      </div>

      <div className="rounded-lg border">
        <DataTable
          caption="Список уведомлений о потребности"
          columns={columns}
          rows={data?.items ?? []}
          rowKey={(n) => n.id}
          isLoading={query.isLoading}
          isError={query.isError}
          onRetry={() => query.refetch()}
          emptyText="Уведомлений пока нет"
          emptyAction={<NotificationCreateDialog />}
          rowActions={(n) => (
            <Button size="sm" variant="outline" onClick={() => setDetailId(n.id)}>
              <Eye className="h-4 w-4" />
              Открыть
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

      <NotificationDetailDialog id={detailId} onClose={() => setDetailId(null)} />
    </section>
  );
}
