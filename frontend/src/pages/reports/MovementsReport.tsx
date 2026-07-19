import { useState } from "react";
import { useMovementsReport } from "@/entities/report/api/queries";
import { MOVEMENT_DOC_LABEL, type MovementReportRow, type MovementDocType } from "@/entities/report/model/types";
import { DataTable, type Column } from "@/shared/ui/data-table";
import { Button } from "@/shared/ui/button";
import { Input } from "@/shared/ui/input";
import { Label } from "@/shared/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/shared/ui/select";
import { formatDateTime, formatQty } from "@/shared/lib/format";
import { ExportButtons } from "./ExportButtons";

const ALL = "__all__";
const LIMIT = 50;

/**
 * §8.1.3 История движений (AP-5, keyset). Пагинация вперёд/назад по курсору
 * (offset запрещён на длинной истории). Экспорт отдаёт весь отфильтрованный набор.
 */
export function MovementsReport() {
  const [docType, setDocType] = useState<MovementDocType | undefined>(undefined);
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [cursor, setCursor] = useState<string | undefined>(undefined);
  const [prev, setPrev] = useState<(string | undefined)[]>([]);

  const filters = {
    doc_type: docType,
    date_from: dateFrom || undefined,
    date_to: dateTo || undefined,
  };
  const query = useMovementsReport({ limit: LIMIT, cursor, ...filters });
  const data = query.data;

  function resetPaging() {
    setCursor(undefined);
    setPrev([]);
  }

  const columns: Column<MovementReportRow>[] = [
    { key: "date", header: "Дата/время", render: (r) => formatDateTime(r.created_at) },
    { key: "doc", header: "Документ", render: (r) => r.doc_type_label },
    { key: "product", header: "Товар", render: (r) => r.product_name },
    { key: "warehouse", header: "Склад", render: (r) => r.warehouse_code },
    {
      key: "qty",
      header: "Кол-во",
      align: "right",
      render: (r) => {
        const n = Number(r.qty);
        return (
          <span className={n < 0 ? "text-destructive" : "text-success-soft-foreground"}>
            {n > 0 ? "+" : ""}
            {formatQty(r.qty)} {r.unit_code}
          </span>
        );
      },
    },
  ];

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div className="flex flex-wrap items-end gap-3">
          <div>
            <Label htmlFor="mv-type" className="text-muted-foreground">
              Тип документа
            </Label>
            <Select
              value={docType ?? ALL}
              onValueChange={(v) => {
                setDocType(v === ALL ? undefined : (v as MovementDocType));
                resetPaging();
              }}
            >
              <SelectTrigger id="mv-type" className="w-44">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={ALL}>Все</SelectItem>
                <SelectItem value="acquisition">{MOVEMENT_DOC_LABEL.acquisition}</SelectItem>
                <SelectItem value="transfer">{MOVEMENT_DOC_LABEL.transfer}</SelectItem>
                <SelectItem value="writeoff">{MOVEMENT_DOC_LABEL.writeoff}</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div>
            <Label htmlFor="mv-from" className="text-muted-foreground">
              Дата с
            </Label>
            <Input
              id="mv-from"
              type="date"
              value={dateFrom}
              onChange={(e) => {
                setDateFrom(e.target.value);
                resetPaging();
              }}
              className="w-40"
            />
          </div>
          <div>
            <Label htmlFor="mv-to" className="text-muted-foreground">
              Дата по
            </Label>
            <Input
              id="mv-to"
              type="date"
              value={dateTo}
              onChange={(e) => {
                setDateTo(e.target.value);
                resetPaging();
              }}
              className="w-40"
            />
          </div>
        </div>
        <ExportButtons path="/reports/movements" name="istoriya-dvizhenii" params={filters} />
      </div>

      <div className="rounded-lg border">
        <DataTable
          caption="История движений товара"
          columns={columns}
          rows={data?.items ?? []}
          rowKey={(r) => r.id}
          isLoading={query.isLoading}
          isError={query.isError}
          onRetry={() => query.refetch()}
          emptyText="Движений за период нет"
        />
      </div>

      <div className="flex items-center justify-end gap-2">
        <Button
          variant="outline"
          size="sm"
          disabled={prev.length === 0}
          onClick={() => {
            setPrev((p) => {
              const copy = [...p];
              const back = copy.pop();
              setCursor(back);
              return copy;
            });
          }}
        >
          Назад
        </Button>
        <Button
          variant="outline"
          size="sm"
          disabled={!data?.next_cursor}
          onClick={() => {
            setPrev((p) => [...p, cursor]);
            setCursor(data?.next_cursor ?? undefined);
          }}
        >
          Дальше
        </Button>
      </div>
    </div>
  );
}
