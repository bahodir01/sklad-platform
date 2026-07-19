import { useRegistry } from "@/entities/request/api/queries";
import { EmployeeCell } from "@/entities/request/ui/EmployeeCell";
import type { RegistryRow } from "@/entities/request/model/types";
import { useWarehouseLookup } from "@/entities/warehouse/lib/use-warehouse-lookup";
import { PageHeader } from "@/shared/ui/page-header";
import { DataTable, type Column } from "@/shared/ui/data-table";
import { TablePagination } from "@/shared/ui/table-pagination";
import { usePageParams } from "@/shared/lib/use-page-params";
import { formatDate, formatDateTime } from "@/shared/lib/format";

/**
 * Реестр передачи в бухгалтерию (М4, admin, спека13 §4/ADR-2a). Только
 * переданные заявки (status=submitted). Оба номера: заявки и проводки —
 * бухгалтерия держит бумагу с номером ЗАЯВКИ, в учёте списание под номером
 * ПРОВОДКИ; плюс общий номер реестра передачи.
 */
export function RegistryPage() {
  const { page, size, setPage } = usePageParams();
  const query = useRegistry({ page, size });
  const wh = useWarehouseLookup();
  const data = query.data;

  const columns: Column<RegistryRow>[] = [
    {
      key: "request_number",
      header: "№ заявки",
      render: (r) => <span className="font-mono text-[12.5px]">{r.request_number}</span>,
    },
    {
      key: "writeoff_number",
      header: "№ проводки",
      render: (r) => <span className="font-mono text-[12.5px] text-muted-foreground">{r.writeoff_number}</span>,
    },
    {
      key: "employee",
      header: "Сотрудник",
      render: (r) => (
        <EmployeeCell
          employeeId={r.employee_id}
          fullName={r.employee_full_name}
          category={r.employee_category}
        />
      ),
    },
    { key: "warehouse", header: "Склад", render: (r) => wh.name(r.warehouse_id) },
    { key: "issued_at", header: "Выдано", render: (r) => formatDateTime(r.issued_at) },
    {
      key: "register_no",
      header: "№ реестра",
      render: (r) => <span className="font-mono text-[12.5px]">{r.submitted_register_no ?? "—"}</span>,
    },
    { key: "submitted_at", header: "Передано", render: (r) => formatDate(r.submitted_at) },
  ];

  return (
    <section>
      <PageHeader
        breadcrumb="Документы › Реестр передачи"
        title="Реестр передачи"
        subtitle="Переданные в бухгалтерию заявки с номерами заявки, проводки и реестра"
      />
      <div className="rounded-lg border">
        <DataTable
          caption="Реестр передачи в бухгалтерию"
          columns={columns}
          rows={data?.items ?? []}
          rowKey={(r) => r.request_id}
          isLoading={query.isLoading}
          isError={query.isError}
          onRetry={() => query.refetch()}
          emptyText="Переданных заявок пока нет"
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
