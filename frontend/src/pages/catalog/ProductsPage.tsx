import { useProducts } from "@/entities/product/api/queries";
import { useUnitsForResolve } from "@/entities/unit/api/queries";
import { productFields } from "@/entities/product/model/fields";
import type { Product } from "@/entities/product/model/types";
import { fieldByName } from "@/shared/lib/field-descriptor";
import { useCan } from "@/entities/session/lib/use-can";
import { usePageParams } from "@/shared/lib/use-page-params";
import { CatalogScreen } from "@/shared/ui/catalog-screen";
import { DataTable, type Column } from "@/shared/ui/data-table";
import { StatusFilter } from "@/shared/ui/status-filter";
import { TablePagination } from "@/shared/ui/table-pagination";
import { CatalogStatusBadge } from "@/shared/ui/catalog-status-badge";
import { Label } from "@/shared/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/shared/ui/select";
import { ProductCreateDialog } from "@/features/catalog/product-form/ProductCreateDialog";
import { ProductEditDialog } from "@/features/catalog/product-form/ProductEditDialog";
import { ArchiveAction } from "@/features/catalog/archive-action/ArchiveAction";

const L = (name: string) => fieldByName(productFields, name).label;
const ALL = "__all__";

/** Номенклатура → /catalog/products (§8.2). Фильтры status и unit_id (реализованы в API). */
export function ProductsPage() {
  const canWrite = useCan("catalog:write");
  const { page, size, get, setFilter, setPage } = usePageParams();
  const status = get("status");
  const unitId = get("unit_id");

  const query = useProducts({ page, size, status, unit_id: unitId });
  const data = query.data;

  // Резолв кода ЕИ из кэша units (К-F): в списке товара приходит только unit_id.
  const units = useUnitsForResolve();
  const unitCode = (id: number) => units.data?.items.find((u) => u.id === id)?.code ?? `#${id}`;

  const columns: Column<Product>[] = [
    { key: "name", header: L("name"), render: (r) => <span className="font-medium">{r.name}</span> },
    { key: "unit_id", header: L("unit_id"), render: (r) => unitCode(r.unit_id) },
    { key: "sku", header: L("sku"), render: (r) => r.sku ?? "—" },
    { key: "status", header: L("status"), render: (r) => <CatalogStatusBadge status={r.status} /> },
  ];

  return (
    <CatalogScreen
      title="Номенклатура"
      actions={canWrite ? <ProductCreateDialog /> : null}
      filters={
        <>
          <StatusFilter value={status} onChange={(v) => setFilter("status", v)} />
          <div className="flex items-center gap-2">
            <Label htmlFor="filter-unit" className="text-muted-foreground">
              Единица измерения
            </Label>
            <Select
              value={unitId ?? ALL}
              onValueChange={(v) => setFilter("unit_id", v === ALL ? undefined : v)}
            >
              <SelectTrigger id="filter-unit" className="w-48">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={ALL}>Все</SelectItem>
                {(units.data?.items ?? []).map((u) => (
                  <SelectItem key={u.id} value={String(u.id)}>
                    {u.code} — {u.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
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
        caption="Справочник номенклатуры"
        columns={columns}
        rows={data?.items ?? []}
        rowKey={(r) => r.id}
        isLoading={query.isLoading}
        isError={query.isError}
        onRetry={() => query.refetch()}
        emptyAction={canWrite ? <ProductCreateDialog /> : undefined}
        rowActions={
          canWrite
            ? (r) => (
                <>
                  <ProductEditDialog row={r} />
                  <ArchiveAction entity="products" row={r} title={r.name} />
                </>
              )
            : undefined
        }
      />
    </CatalogScreen>
  );
}
