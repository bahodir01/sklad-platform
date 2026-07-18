import { useExpenseTypes } from "@/entities/expense-type/api/queries";
import { expenseTypeFields } from "@/entities/expense-type/model/fields";
import type { ExpenseType } from "@/entities/expense-type/model/types";
import { fieldByName } from "@/shared/lib/field-descriptor";
import { useCan } from "@/entities/session/lib/use-can";
import { usePageParams } from "@/shared/lib/use-page-params";
import { CatalogScreen } from "@/shared/ui/catalog-screen";
import { DataTable, type Column } from "@/shared/ui/data-table";
import { StatusFilter } from "@/shared/ui/status-filter";
import { TablePagination } from "@/shared/ui/table-pagination";
import { CatalogStatusBadge } from "@/shared/ui/catalog-status-badge";
import { BoolCell } from "@/shared/ui/bool-cell";
import { ExpenseTypeCreateDialog } from "@/features/catalog/expense-type-form/ExpenseTypeCreateDialog";
import { ExpenseTypeEditDialog } from "@/features/catalog/expense-type-form/ExpenseTypeEditDialog";
import { ArchiveAction } from "@/features/catalog/archive-action/ArchiveAction";

const L = (name: string) => fieldByName(expenseTypeFields, name).label;

/** Типы расхода ТОВАРА → /catalog/expense-types (§8.4). НЕ путать с видами расхода денег. */
export function ExpenseTypesPage() {
  const canWrite = useCan("catalog:write");
  const { page, size, get, setFilter, setPage } = usePageParams();
  const status = get("status");

  const query = useExpenseTypes({ page, size, status });
  const data = query.data;

  const columns: Column<ExpenseType>[] = [
    { key: "name", header: L("name"), render: (r) => <span className="font-medium">{r.name}</span> },
    {
      key: "requires_employee",
      header: L("requires_employee"),
      render: (r) => <BoolCell value={r.requires_employee} />,
    },
    { key: "status", header: L("status"), render: (r) => <CatalogStatusBadge status={r.status} /> },
  ];

  return (
    <CatalogScreen
      title="Типы расхода товара"
      actions={canWrite ? <ExpenseTypeCreateDialog /> : null}
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
        caption="Справочник типов расхода товара"
        columns={columns}
        rows={data?.items ?? []}
        rowKey={(r) => r.id}
        isLoading={query.isLoading}
        isError={query.isError}
        onRetry={() => query.refetch()}
        emptyAction={canWrite ? <ExpenseTypeCreateDialog /> : undefined}
        rowActions={
          canWrite
            ? (r) => (
                <>
                  <ExpenseTypeEditDialog row={r} />
                  <ArchiveAction entity="expense-types" row={r} title={r.name} />
                </>
              )
            : undefined
        }
      />
    </CatalogScreen>
  );
}
