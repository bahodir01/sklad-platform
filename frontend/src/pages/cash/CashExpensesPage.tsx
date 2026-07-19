import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import { Send, Printer } from "lucide-react";
import { useExpenses, useCashDesks } from "@/entities/cash/api/queries";
import { useSubmitExpenses } from "@/entities/cash/api/mutations";
import { CASH_DESK_LABEL } from "@/entities/cash/model/types";
import type { MoneyExpenseListItem, ExpenseRegistryRow } from "@/entities/cash/model/types";
import { useActiveExpenseCategories } from "@/entities/expense-category/api/queries";
import { PageHeader } from "@/shared/ui/page-header";
import { DataTable, type Column } from "@/shared/ui/data-table";
import { TablePagination } from "@/shared/ui/table-pagination";
import { Button } from "@/shared/ui/button";
import { Badge } from "@/shared/ui/badge";
import { BoolFilter } from "@/shared/ui/status-filter";
import { ApiError } from "@/shared/api/errors";
import { api } from "@/shared/api/client";
import type { Page } from "@/shared/api/types";
import { usePageParams } from "@/shared/lib/use-page-params";
import { formatDate, formatMoneyStr } from "@/shared/lib/format";
import { printRegistry } from "@/shared/lib/print";

function errMsg(e: unknown, fallback: string): string {
  return e instanceof ApiError ? e.message : fallback;
}

/**
 * Передача расходов в бухгалтерию (М5, admin, спека13 §5). У денег НЕТ этапа
 * подписи — чек заменяет подпись, расход готов к передаче сразу после
 * проведения. Фильтр «Передано / Не передано»:
 *   Не передано → галочки + «Передать в бухгалтерию».
 *   Передано    → просмотр с № реестра + перепечать реестра.
 */
export function CashExpensesPage() {
  const { page, size, setPage, get, setFilter } = usePageParams();
  // По умолчанию показываем непереданные (с ними работают).
  const submittedParam = get("submitted");
  const submitted = submittedParam === "true";

  const list = useExpenses({ submitted, page, size });
  const categories = useActiveExpenseCategories();
  const desks = useCashDesks();
  const submitMut = useSubmitExpenses();

  const catName = useMemo(() => {
    const m = new Map<number, string>();
    for (const c of categories.data?.items ?? []) m.set(c.id, c.name);
    return (id: number) => m.get(id) ?? `Вид #${id}`;
  }, [categories.data]);

  const deskLabel = useMemo(() => {
    const m = new Map<number, string>();
    for (const d of desks.data ?? []) m.set(d.id, CASH_DESK_LABEL[d.type]);
    return (id: number) => m.get(id) ?? `Касса #${id}`;
  }, [desks.data]);

  const rows = list.data?.items ?? [];

  const [selected, setSelected] = useState<Set<number>>(new Set());
  useEffect(() => setSelected(new Set()), [submitted, page]);

  function toggleRow(r: MoneyExpenseListItem) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(r.id)) next.delete(r.id);
      else next.add(r.id);
      return next;
    });
  }
  function toggleAll(checked: boolean) {
    setSelected(checked ? new Set(rows.map((r) => r.id)) : new Set());
  }
  const selectedIds = useMemo(() => rows.filter((r) => selected.has(r.id)).map((r) => r.id), [rows, selected]);

  function handleSubmit() {
    if (selectedIds.length === 0) {
      toast.info("Отметьте расходы для передачи");
      return;
    }
    submitMut.mutate(selectedIds, {
      onSuccess: (res) => {
        setSelected(new Set());
        toast.success(`Передано: ${res.submitted.length}. Реестр ${res.register_no ?? "—"}`, {
          action: res.register_no
            ? { label: "Печать реестра", onClick: () => printExpenseRegistry(res.register_no!) }
            : undefined,
        });
      },
      onError: (e) => toast.error(errMsg(e, "Не удалось передать в бухгалтерию")),
    });
  }

  /** Печать официального реестра передачи денег по его номеру. */
  async function printExpenseRegistry(registerNo: string) {
    try {
      const res = await api.get<Page<ExpenseRegistryRow>>("/cash/expenses/registry", {
        register_no: registerNo,
        page: 1,
        size: 200,
      });
      printRegistry<ExpenseRegistryRow>(
        "Реестр передачи в бухгалтерию (деньги)",
        `Реестр № ${registerNo}`,
        [
          { header: "Дата", value: (r) => formatDate(r.date) },
          { header: "Вид расхода", value: (r) => catName(r.expense_category_id) },
          { header: "Сумма", value: (r) => formatMoneyStr(r.amount), align: "right" },
          { header: "Сотрудник", value: (r) => `#${r.employee_id}` },
          { header: "Передано", value: (r) => formatDate(r.submitted_at) },
        ],
        res.items,
      );
    } catch (e) {
      toast.error(errMsg(e, "Не удалось загрузить реестр"));
    }
  }

  const columns: Column<MoneyExpenseListItem>[] = [
    { key: "date", header: "Дата", render: (e) => formatDate(e.date) },
    { key: "desk", header: "Касса", render: (e) => deskLabel(e.cash_desk_id) },
    { key: "category", header: "Вид расхода", render: (e) => catName(e.expense_category_id) },
    { key: "amount", header: "Сумма", align: "right", render: (e) => formatMoneyStr(e.amount) },
    ...(submitted
      ? ([
          { key: "register", header: "№ реестра", render: (e) => (
            <span className="font-mono text-[12.5px]">{e.submitted_register_no ?? "—"}</span>
          ) },
          { key: "submitted_at", header: "Передано", render: (e) => formatDate(e.submitted_at) },
        ] as Column<MoneyExpenseListItem>[])
      : ([
          { key: "state", header: "Статус", render: () => <Badge variant="warning">Не передано</Badge> },
        ] as Column<MoneyExpenseListItem>[])),
  ];

  return (
    <section>
      <PageHeader
        breadcrumb="Деньги › Передача расходов"
        title="Передача расходов"
        subtitle="Учёт передачи расходов денег в бухгалтерию (у денег нет этапа подписи — чек заменяет подпись)"
        actions={
          !submitted ? (
            <Button onClick={handleSubmit} disabled={submitMut.isPending || selectedIds.length === 0}>
              <Send className="h-4 w-4" />
              Передать в бухгалтерию{selectedIds.length ? ` (${selectedIds.length})` : ""}
            </Button>
          ) : null
        }
      />

      <div className="mb-4">
        <BoolFilter
          id="filter-submitted"
          label="Передача"
          value={submittedParam}
          onChange={(v) => setFilter("submitted", v)}
          trueLabel="Передано"
          falseLabel="Не передано"
        />
      </div>

      <div className="rounded-lg border">
        <DataTable
          caption="Расходы денег для передачи в бухгалтерию"
          columns={columns}
          rows={rows}
          rowKey={(e) => e.id}
          isLoading={list.isLoading}
          isError={list.isError}
          onRetry={() => list.refetch()}
          emptyText={submitted ? "Переданных расходов пока нет" : "Нет непереданных расходов"}
          selectedKeys={!submitted ? selected : undefined}
          onToggleRow={!submitted ? toggleRow : undefined}
          onToggleAll={!submitted ? toggleAll : undefined}
          rowActions={
            submitted
              ? (e) =>
                  e.submitted_register_no ? (
                    <Button size="sm" variant="outline" onClick={() => printExpenseRegistry(e.submitted_register_no!)}>
                      <Printer className="h-4 w-4" />
                      Реестр
                    </Button>
                  ) : (
                    <span className="text-xs text-muted-foreground">—</span>
                  )
              : undefined
          }
        />
      </div>

      {list.data ? (
        <TablePagination
          page={list.data.page}
          size={list.data.size}
          total={list.data.total}
          pages={list.data.pages}
          onPageChange={setPage}
        />
      ) : null}
    </section>
  );
}
