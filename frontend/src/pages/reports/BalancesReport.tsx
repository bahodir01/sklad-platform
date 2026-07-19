import { useState } from "react";
import { X } from "lucide-react";
import { useBalancesReport } from "@/entities/report/api/queries";
import type { BalanceReportRow } from "@/entities/report/model/types";
import { WarehouseSelect } from "@/entities/warehouse/ui/WarehouseSelect";
import { DataTable, type Column } from "@/shared/ui/data-table";
import { TablePagination } from "@/shared/ui/table-pagination";
import { Button } from "@/shared/ui/button";
import { Label } from "@/shared/ui/label";
import { formatQty } from "@/shared/lib/format";
import { ExportButtons } from "./ExportButtons";

/** §8.1.1 Остатки в реальном времени (AP-10). Фильтр по складу + экспорт. */
export function BalancesReport() {
  const [page, setPage] = useState(1);
  const [warehouseId, setWarehouseId] = useState<number | undefined>(undefined);
  const size = 50;

  const params = { warehouse_id: warehouseId };
  const query = useBalancesReport({ page, size, ...params });
  const data = query.data;

  const columns: Column<BalanceReportRow>[] = [
    { key: "product", header: "Товар", render: (r) => r.product_name },
    { key: "sku", header: "Артикул", render: (r) => r.sku ?? "—" },
    {
      key: "warehouse",
      header: "Склад",
      render: (r) => `${r.warehouse_code} — ${r.warehouse_name}`,
    },
    { key: "unit", header: "Ед.", render: (r) => r.unit_code },
    { key: "qty", header: "Остаток", align: "right", render: (r) => formatQty(r.qty) },
  ];

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div className="flex items-end gap-2">
          <div className="w-64">
            <Label htmlFor="bal-wh" className="text-muted-foreground">
              Склад
            </Label>
            <WarehouseSelect
              source="active"
              value={warehouseId}
              onChange={(v) => {
                setWarehouseId(v);
                setPage(1);
              }}
              aria={{ id: "bal-wh" }}
              placeholder="Все склады"
            />
          </div>
          {warehouseId != null ? (
            <Button
              variant="ghost"
              size="sm"
              onClick={() => {
                setWarehouseId(undefined);
                setPage(1);
              }}
            >
              <X className="h-4 w-4" />
              Сбросить
            </Button>
          ) : null}
        </div>
        <ExportButtons path="/reports/balances" name="ostatki" params={params} />
      </div>

      <div className="rounded-lg border">
        <DataTable
          caption="Отчёт по остаткам"
          columns={columns}
          rows={data?.items ?? []}
          rowKey={(r) => `${r.product_id}-${r.warehouse_id}`}
          isLoading={query.isLoading}
          isError={query.isError}
          onRetry={() => query.refetch()}
          emptyText="Остатков нет"
        />
      </div>

      {data ? (
        <TablePagination page={data.page} size={data.size} total={data.total} pages={data.pages} onPageChange={setPage} />
      ) : null}
    </div>
  );
}
