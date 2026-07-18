import { useExpenseCategories } from "@/entities/expense-category/api/queries";
import { expenseCategoryFields } from "@/entities/expense-category/model/fields";
import type { ExpenseCategory } from "@/entities/expense-category/model/types";
import { fieldByName } from "@/shared/lib/field-descriptor";
import { useCan } from "@/entities/session/lib/use-can";
import { usePageParams } from "@/shared/lib/use-page-params";
import { CatalogScreen } from "@/shared/ui/catalog-screen";
import { DataTable, type Column } from "@/shared/ui/data-table";
import { StatusFilter } from "@/shared/ui/status-filter";
import { TablePagination } from "@/shared/ui/table-pagination";
import { CatalogStatusBadge } from "@/shared/ui/catalog-status-badge";
import { ExpenseCategoryCreateDialog } from "@/features/catalog/expense-category-form/ExpenseCategoryCreateDialog";
import { ExpenseCategoryEditDialog } from "@/features/catalog/expense-category-form/ExpenseCategoryEditDialog";
import { ArchiveAction } from "@/features/catalog/archive-action/ArchiveAction";

const L = (name: string) => fieldByName(expenseCategoryFields, name).label;

/** Виды расхода ДЕНЕГ → /catalog/expense-categories (§8.5). НЕ путать с типами расхода товара. */
export function ExpenseCategoriesPage() {
  const canWrite = useCan("catalog:write");
  const { page, size, get, setFilter, setPage } = usePageParams();
  const status = get("status");

  const query = useExpenseCategories({ page, size, status });
  const data = query.data;

  const columns: Column<ExpenseCategory>[] = [
    { key: "name", header: L("name"), render: (r) => <span className="font-medium">{r.name}</span> },
    { key: "status", header: L("status"), render: (r) => <CatalogStatusBadge status={r.status} /> },
  ];

  return (
    <CatalogScreen
      title="Виды расхода денег"
      actions={canWrite ? <ExpenseCategoryCreateDialog /> : null}
      filters={<StatusFilter value={status} onChange={(v) => setFilter("status", v)} />}
      pagination={
        data ? (
          <TablePagination
            page={data.page}
            size={data.size}
            total={data.total}
            pages={data.pages}
            onPageChange={setPage}
          />
        ) : null
      }
    >
      <DataTable
        caption="Справочник видов расхода денег"
        columns={columns}
        rows={data?.items ?? []}
        rowKey={(r) => r.id}
        isLoading={query.isLoading}
        isError={query.isError}
        onRetry={() => query.refetch()}
        emptyAction={canWrite ? <ExpenseCategoryCreateDialog /> : undefined}
        rowActions={
          canWrite
            ? (r) => (
                <>
                  <ExpenseCategoryEditDialog row={r} />
                  <ArchiveAction entity="expense-categories" row={r} title={r.name} />
                </>
              )
            : undefined
        }
      />
    </CatalogScreen>
  );
}
