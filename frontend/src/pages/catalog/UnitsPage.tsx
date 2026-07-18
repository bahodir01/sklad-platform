import { useUnits } from "@/entities/unit/api/queries";
import { unitFields } from "@/entities/unit/model/fields";
import type { Unit } from "@/entities/unit/model/types";
import { fieldByName } from "@/shared/lib/field-descriptor";
import { useCan } from "@/entities/session/lib/use-can";
import { usePageParams } from "@/shared/lib/use-page-params";
import { CatalogScreen } from "@/shared/ui/catalog-screen";
import { DataTable, type Column } from "@/shared/ui/data-table";
import { BoolFilter } from "@/shared/ui/status-filter";
import { TablePagination } from "@/shared/ui/table-pagination";
import { ActiveBadge } from "@/shared/ui/catalog-status-badge";
import { UnitCreateDialog } from "@/features/catalog/unit-form/UnitCreateDialog";
import { UnitEditDialog } from "@/features/catalog/unit-form/UnitEditDialog";
import { ArchiveAction } from "@/features/catalog/archive-action/ArchiveAction";

const L = (name: string) => fieldByName(unitFields, name).label;

/** Единицы измерения → /catalog/units (§8.1). Фильтр — is_active (реализован в API). */
export function UnitsPage() {
  const canWrite = useCan("catalog:write");
  const { page, size, get, setFilter, setPage } = usePageParams();
  const isActive = get("is_active");

  const query = useUnits({ page, size, is_active: isActive });
  const data = query.data;

  const columns: Column<Unit>[] = [
    { key: "code", header: L("code"), render: (r) => <span className="font-medium">{r.code}</span> },
    { key: "name", header: L("name"), render: (r) => r.name },
    { key: "is_active", header: L("is_active"), render: (r) => <ActiveBadge isActive={r.is_active} /> },
  ];

  return (
    <CatalogScreen
      title="Единицы измерения"
      actions={canWrite ? <UnitCreateDialog /> : null}
      filters={
        <BoolFilter
          id="filter-is_active"
          label="Статус"
          value={isActive}
          onChange={(v) => setFilter("is_active", v)}
          trueLabel="Активные"
          falseLabel="В архиве"
        />
      }
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
        caption="Справочник единиц измерения"
        columns={columns}
        rows={data?.items ?? []}
        rowKey={(r) => r.id}
        isLoading={query.isLoading}
        isError={query.isError}
        onRetry={() => query.refetch()}
        emptyAction={canWrite ? <UnitCreateDialog /> : undefined}
        rowActions={
          canWrite
            ? (r) => (
                <>
                  <UnitEditDialog row={r} />
                  <ArchiveAction entity="units" row={r} title={r.code} />
                </>
              )
            : undefined
        }
      />
    </CatalogScreen>
  );
}
