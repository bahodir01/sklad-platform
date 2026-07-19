import { useState } from "react";
import { useCashflowReport } from "@/entities/report/api/queries";
import type { CashflowReportRow } from "@/entities/report/model/types";
import { CASH_DESK_LABEL } from "@/entities/cash/model/types";
import { ExpenseCategorySelect } from "@/entities/expense-category/ui/ExpenseCategorySelect";
import { DataTable, type Column } from "@/shared/ui/data-table";
import { TablePagination } from "@/shared/ui/table-pagination";
import { KpiCard } from "@/shared/ui/kpi-card";
import { Card } from "@/shared/ui/card";
import { Input } from "@/shared/ui/input";
import { Label } from "@/shared/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/shared/ui/select";
import { formatDate, formatMoneyStr } from "@/shared/lib/format";
import { ExportButtons } from "./ExportButtons";

type Category = "teacher" | "worker";

/**
 * §8.2 ДДС — движение денежных средств (AP-8). Фильтр по КАТЕГОРИИ (кассе)
 * ОБЯЗАТЕЛЕН: без него отчёт не запрашивается и не выгружается. Показывает итоги
 * прихода/расхода, баланс обеих касс и постраничный список расходов.
 */
export function CashflowReport() {
  const [page, setPage] = useState(1);
  const [category, setCategory] = useState<Category | undefined>(undefined);
  const [expenseCategoryId, setExpenseCategoryId] = useState<number | undefined>(undefined);
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const size = 50;

  const params = {
    category,
    expense_category_id: expenseCategoryId,
    date_from: dateFrom || undefined,
    date_to: dateTo || undefined,
  };
  const query = useCashflowReport({ page, size, ...params });
  const data = query.data;
  const summary = data?.summary;

  const columns: Column<CashflowReportRow>[] = [
    { key: "date", header: "Дата", render: (r) => formatDate(r.date) },
    { key: "employee", header: "Сотрудник", render: (r) => r.employee_name },
    { key: "cat", header: "Вид расхода", render: (r) => r.expense_category_name },
    { key: "amount", header: "Сумма", align: "right", render: (r) => formatMoneyStr(r.amount) },
    { key: "desc", header: "Описание", render: (r) => r.description },
  ];

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div className="flex flex-wrap items-end gap-3">
          <div>
            <Label htmlFor="cf-cat" className="text-muted-foreground">
              Касса (категория) <span className="text-destructive">*</span>
            </Label>
            <Select
              value={category ?? ""}
              onValueChange={(v) => {
                setCategory(v as Category);
                setPage(1);
              }}
            >
              <SelectTrigger id="cf-cat" className="w-52" aria-required>
                <SelectValue placeholder="Обязательно выберите" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="teacher">{CASH_DESK_LABEL.teacher}</SelectItem>
                <SelectItem value="worker">{CASH_DESK_LABEL.worker}</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="w-52">
            <Label htmlFor="cf-exp" className="text-muted-foreground">
              Вид расхода
            </Label>
            <ExpenseCategorySelect
              value={expenseCategoryId}
              onChange={(v) => {
                setExpenseCategoryId(v || undefined);
                setPage(1);
              }}
              aria={{ id: "cf-exp" }}
              allowEmpty
            />
          </div>
          <div>
            <Label htmlFor="cf-from" className="text-muted-foreground">
              Дата с
            </Label>
            <Input
              id="cf-from"
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
            <Label htmlFor="cf-to" className="text-muted-foreground">
              Дата по
            </Label>
            <Input
              id="cf-to"
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
        <ExportButtons path="/reports/cashflow" name="dds" params={params} disabled={!category} />
      </div>

      {!category ? (
        <Card className="p-8 text-center text-sm text-muted-foreground">
          Выберите кассу (категорию) — это обязательный фильтр отчёта ДДС.
        </Card>
      ) : (
        <>
          {summary ? (
            <div className="grid grid-cols-1 gap-3.5 sm:grid-cols-2 lg:grid-cols-4">
              <KpiCard label="Приход за период" value={formatMoneyStr(summary.total_income)} dot="success" />
              <KpiCard label="Расход за период" value={formatMoneyStr(summary.total_expense)} dot="warning" />
              <KpiCard label="Итог (приход − расход)" value={formatMoneyStr(summary.net)} dot="accent" accent />
              <KpiCard
                label="Балансы касс"
                value={
                  <span className="text-base font-semibold">
                    {summary.desk_balances
                      .map((b) => `${CASH_DESK_LABEL[b.cash_desk_type]}: ${formatMoneyStr(b.balance)}`)
                      .join(" · ")}
                  </span>
                }
                dot="info"
              />
            </div>
          ) : null}

          <div className="rounded-lg border">
            <DataTable
              caption="Отчёт ДДС по кассе"
              columns={columns}
              rows={data?.items ?? []}
              rowKey={(r) => r.id}
              isLoading={query.isLoading}
              isError={query.isError}
              onRetry={() => query.refetch()}
              emptyText="Расходов за период нет"
            />
          </div>

          {data ? (
            <TablePagination page={data.page} size={data.size} total={data.total} pages={data.pages} onPageChange={setPage} />
          ) : null}
        </>
      )}
    </div>
  );
}
