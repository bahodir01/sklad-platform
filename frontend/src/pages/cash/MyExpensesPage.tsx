import { useMemo } from "react";
import { useMyExpenses } from "@/entities/cash/api/queries";
import type { MoneyExpenseListItem } from "@/entities/cash/model/types";
import { useActiveExpenseCategories } from "@/entities/expense-category/api/queries";
import { ExpenseForm } from "@/features/cash/expense-form/ExpenseForm";
import { PageHeader } from "@/shared/ui/page-header";
import { Card } from "@/shared/ui/card";
import { DataTable, type Column } from "@/shared/ui/data-table";
import { TablePagination } from "@/shared/ui/table-pagination";
import { usePageParams } from "@/shared/lib/use-page-params";
import { formatDate, formatMoneyStr } from "@/shared/lib/format";

/**
 * «Мои расходы» (teacher/worker, §5.4). Форма расхода с чеком + список своих
 * расходов (row-level: только свои). Кассу не показываем — сервер определяет её
 * по категории сотрудника (SV-6); в истории отображаем вид расхода и сумму.
 */
export function MyExpensesPage() {
  const { page, size, setPage } = usePageParams();
  const query = useMyExpenses({ page, size });
  const categories = useActiveExpenseCategories();
  const data = query.data;

  const catName = useMemo(() => {
    const m = new Map<number, string>();
    for (const c of categories.data?.items ?? []) m.set(c.id, c.name);
    return (id: number) => m.get(id) ?? `Вид #${id}`;
  }, [categories.data]);

  const columns: Column<MoneyExpenseListItem>[] = [
    { key: "date", header: "Дата", render: (e) => formatDate(e.date) },
    { key: "category", header: "Вид расхода", render: (e) => catName(e.expense_category_id) },
    {
      key: "amount",
      header: "Сумма",
      align: "right",
      render: (e) => formatMoneyStr(e.amount),
    },
  ];

  return (
    <section>
      <PageHeader
        breadcrumb="Деньги › Мои расходы"
        title="Мои расходы"
        subtitle="Проведение расхода денег с чеком и история ваших расходов"
      />

      <Card className="mb-6 max-w-3xl p-5">
        <h2 className="mb-4 text-sm font-semibold">Новый расход</h2>
        <ExpenseForm />
      </Card>

      <div className="rounded-lg border">
        <DataTable
          caption="История моих расходов"
          columns={columns}
          rows={data?.items ?? []}
          rowKey={(e) => e.id}
          isLoading={query.isLoading}
          isError={query.isError}
          onRetry={() => query.refetch()}
          emptyText="У вас пока нет расходов"
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
    </section>
  );
}
