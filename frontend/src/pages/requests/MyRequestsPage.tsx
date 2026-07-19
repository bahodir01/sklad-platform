import { toast } from "sonner";
import { CheckCircle2 } from "lucide-react";
import { useMyRequests } from "@/entities/request/api/queries";
import { useConfirmRequest } from "@/entities/request/api/mutations";
import { RequestStatusBadge } from "@/entities/request/ui/RequestStatusBadge";
import type { RequestListItem } from "@/entities/request/model/types";
import { useWarehouseLookup } from "@/entities/warehouse/lib/use-warehouse-lookup";
import { RequestCreateDialog } from "@/features/requests/request-form/RequestCreateDialog";
import { PageHeader } from "@/shared/ui/page-header";
import { DataTable, type Column } from "@/shared/ui/data-table";
import { TablePagination } from "@/shared/ui/table-pagination";
import { Button } from "@/shared/ui/button";
import { ApiError } from "@/shared/api/errors";
import { usePageParams } from "@/shared/lib/use-page-params";
import { formatDate } from "@/shared/lib/format";

/**
 * «Мои заявки» (teacher/worker, §5.1). Список своих заявок + подтверждение
 * черновика (draft→to_print): после подтверждения заявка уходит в очередь
 * печати к администратору.
 */
export function MyRequestsPage() {
  const { page, size, setPage } = usePageParams();
  const query = useMyRequests({ page, size });
  const wh = useWarehouseLookup();
  const confirm = useConfirmRequest();
  const data = query.data;

  function handleConfirm(id: number, number: string) {
    confirm.mutate(id, {
      onSuccess: () => toast.success(`Заявка ${number} подтверждена и отправлена на печать`),
      onError: (e) => toast.error(e instanceof ApiError ? e.message : "Не удалось подтвердить"),
    });
  }

  const columns: Column<RequestListItem>[] = [
    {
      key: "number",
      header: "№ заявки",
      render: (r) => <span className="font-mono text-[12.5px]">{r.number}</span>,
    },
    { key: "warehouse", header: "Склад", render: (r) => wh.name(r.warehouse_id) },
    { key: "created_at", header: "Создана", render: (r) => formatDate(r.created_at) },
    { key: "status", header: "Статус", render: (r) => <RequestStatusBadge status={r.status} /> },
  ];

  return (
    <section>
      <PageHeader
        breadcrumb="Заявки › Мои заявки"
        title="Мои заявки"
        subtitle="Заявки на получение товара со склада"
        actions={<RequestCreateDialog />}
      />
      <div className="rounded-lg border">
        <DataTable
          caption="Мои заявки на получение"
          columns={columns}
          rows={data?.items ?? []}
          rowKey={(r) => r.id}
          isLoading={query.isLoading}
          isError={query.isError}
          onRetry={() => query.refetch()}
          emptyText="У вас пока нет заявок"
          emptyAction={<RequestCreateDialog />}
          rowActions={(r) =>
            r.status === "draft" ? (
              <Button
                size="sm"
                onClick={() => handleConfirm(r.id, r.number)}
                disabled={confirm.isPending}
              >
                <CheckCircle2 className="h-4 w-4" />
                Подтвердить
              </Button>
            ) : (
              <span className="text-xs text-muted-foreground">—</span>
            )
          }
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
