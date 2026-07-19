import { useState } from "react";
import { useUnpurchasedReport } from "@/entities/report/api/queries";
import type { UnpurchasedReportRow } from "@/entities/report/model/types";
import { DataTable, type Column } from "@/shared/ui/data-table";
import { TablePagination } from "@/shared/ui/table-pagination";
import { Input } from "@/shared/ui/input";
import { Label } from "@/shared/ui/label";
import { formatDate, formatQty } from "@/shared/lib/format";
import { ExportButtons } from "./ExportButtons";

/** §8.1.2 Недокупленное по уведомлениям (AP-6). Фильтр по датам + экспорт. */
export function UnpurchasedReport() {
  const [page, setPage] = useState(1);
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const size = 50;

  const params = { date_from: dateFrom || undefined, date_to: dateTo || undefined };
  const query = useUnpurchasedReport({ page, size, ...params });
  const data = query.data;

  const columns: Column<UnpurchasedReportRow>[] = [
    {
      key: "number",
      header: "№ уведомления",
      render: (r) => <span className="font-mono text-[12.5px]">{r.notification_number}</span>,
    },
    { key: "date", header: "Дата", render: (r) => formatDate(r.notification_date) },
    { key: "product", header: "Товар", render: (r) => r.product_name },
    { key: "unit", header: "Ед.", render: (r) => r.unit_code },
    { key: "req", header: "Заявлено", align: "right", render: (r) => formatQty(r.qty_requested) },
    { key: "pur", header: "Приобретено", align: "right", render: (r) => formatQty(r.qty_purchased) },
    { key: "rem", header: "Остаток", align: "right", render: (r) => formatQty(r.qty_remaining) },
  ];

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div className="flex items-end gap-3">
          <div>
            <Label htmlFor="unp-from" className="text-muted-foreground">
              Дата с
            </Label>
            <Input
              id="unp-from"
              type="date"
              value={dateFrom}
              onChange={(e) => {
                setDateFrom(e.target.value);
                setPage(1);
              }}
              className="w-40"
            />
          </div>
          <div>
            <Label htmlFor="unp-to" className="text-muted-foreground">
              Дата по
            </Label>
            <Input
              id="unp-to"
              type="date"
              value={dateTo}
              onChange={(e) => {
                setDateTo(e.target.value);
                setPage(1);
              }}
              className="w-40"
            />
          </div>
        </div>
        <ExportButtons path="/reports/unpurchased" name="nedokup" params={params} />
      </div>

      <div className="rounded-lg border">
        <DataTable
          caption="Отчёт по недокупленному"
          columns={columns}
          rows={data?.items ?? []}
          rowKey={(r) => `${r.notification_id}-${r.product_id}`}
          isLoading={query.isLoading}
          isError={query.isError}
          onRetry={() => query.refetch()}
          emptyText="Недокупленных позиций нет — всё закрыто"
        />
      </div>

      {data ? (
        <TablePagination page={data.page} size={data.size} total={data.total} pages={data.pages} onPageChange={setPage} />
      ) : null}
    </div>
  );
}
