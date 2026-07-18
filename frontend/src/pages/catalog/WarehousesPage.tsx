import { useWarehouses } from "@/entities/warehouse/api/queries";
import { warehouseFields } from "@/entities/warehouse/model/fields";
import type { Warehouse } from "@/entities/warehouse/model/types";
import { fieldByName } from "@/shared/lib/field-descriptor";
import { useCan } from "@/entities/session/lib/use-can";
import { usePageParams } from "@/shared/lib/use-page-params";
import { CatalogScreen } from "@/shared/ui/catalog-screen";
import { DataTable, type Column } from "@/shared/ui/data-table";
import { StatusFilter, BoolFilter } from "@/shared/ui/status-filter";
import { TablePagination } from "@/shared/ui/table-pagination";
import { CatalogStatusBadge } from "@/shared/ui/catalog-status-badge";
import { BoolCell } from "@/shared/ui/bool-cell";
import { WarehouseCreateDialog } from "@/features/catalog/warehouse-form/WarehouseCreateDialog";
import { WarehouseEditDialog } from "@/features/catalog/warehouse-form/WarehouseEditDialog";
import { ArchiveAction } from "@/features/catalog/archive-action/ArchiveAction";

const L = (name: string) => fieldByName(warehouseFields, name).label;

/** Склады → /catalog/warehouses (§8.3). Несущий экран: allows_issuance + догрузка детали. */
export function WarehousesPage() {
  const canWrite = useCan("catalog:write");
  const { page, size, get, setFilter, setPage } = usePageParams();
  const status = get("status");
  const allowsIssuance = get("allows_issuance");

  const query = useWarehouses({ page, size, status, allows_issuance: allowsIssuance });
  const data = query.data;

  const columns: Column<Warehouse>[] = [
    { key: "code", header: L("code"), render: (r) => <span className="font-medium">{r.code}</span> },
    { key: "name", header: L("name"), render: (r) => r.name },
    {
      key: "allows_issuance",
      header: L("allows_issuance"),
      render: (r) => <BoolCell value={r.allows_issuance} />,
    },
    { key: "status", header: L("status"), render: (r) => <CatalogStatusBadge status={r.status} /> },
  ];

  return (
    <CatalogScreen
      title="Склады"
      actions={canWrite ? <WarehouseCreateDialog /> : null}
      filters={
        <>
          <StatusFilter value={status} onChange={(v) => setFilter("status", v)} />
          <BoolFilter
            id="filter-allows_issuance"
            label="Склад списания"
            value={allowsIssuance}
            onChange={(v) => setFilter("allows_issuance", v)}
          />
        </>
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
        caption="Справочник складов"
        columns={columns}
        rows={data?.items ?? []}
        rowKey={(r) => r.id}
        isLoading={query.isLoading}
        isError={query.isError}
        onRetry={() => query.refetch()}
        emptyAction={canWrite ? <WarehouseCreateDialog /> : undefined}
        rowActions={
          canWrite
            ? (r) => (
                <>
                  <WarehouseEditDialog row={r} />
                  <ArchiveAction entity="warehouses" row={r} title={r.code} />
                </>
              )
            : undefined
        }
      />
    </CatalogScreen>
  );
}
