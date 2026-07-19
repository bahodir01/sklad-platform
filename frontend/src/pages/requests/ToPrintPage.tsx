import { useMemo } from "react";
import { toast } from "sonner";
import { Printer } from "lucide-react";
import { useRequestsByStatus, useRegistry } from "@/entities/request/api/queries";
import { usePrintRequest, useIssueRequest, useBatchPrint } from "@/entities/request/api/mutations";
import { RequestStatusBadge } from "@/entities/request/ui/RequestStatusBadge";
import { EmployeeCell } from "@/entities/request/ui/EmployeeCell";
import type { RequestListItem } from "@/entities/request/model/types";
import { useWarehouseLookup } from "@/entities/warehouse/lib/use-warehouse-lookup";
import { PageHeader } from "@/shared/ui/page-header";
import { KpiCard } from "@/shared/ui/kpi-card";
import { DataTable, type Column } from "@/shared/ui/data-table";
import { Button } from "@/shared/ui/button";
import { ApiError } from "@/shared/api/errors";
import { formatDate, isToday } from "@/shared/lib/format";

const QUEUE_SIZE = 100;

/**
 * Очередь «К печати» (М4, admin, макет sklad-ui-mockup). Собирается из двух
 * наборов: to_print (кнопка «Печать») и printed (кнопка «Выдано»). Кнопка
 * «Выдано» активна ТОЛЬКО после печати (ADR-3): у to_print она disabled.
 */
export function ToPrintPage() {
  const toPrint = useRequestsByStatus("to_print", { page: 1, size: QUEUE_SIZE });
  const printed = useRequestsByStatus("printed", { page: 1, size: QUEUE_SIZE });
  const registry = useRegistry({ page: 1, size: 100 });
  const wh = useWarehouseLookup();

  const printMut = usePrintRequest();
  const issueMut = useIssueRequest();
  const batchMut = useBatchPrint();

  const rows = useMemo<RequestListItem[]>(() => {
    const a = toPrint.data?.items ?? [];
    const b = printed.data?.items ?? [];
    return [...a, ...b].sort((x, y) => y.created_at.localeCompare(x.created_at));
  }, [toPrint.data, printed.data]);

  const issuedToday = (registry.data?.items ?? []).filter((r) => isToday(r.issued_at)).length;
  const toPrintTotal = toPrint.data?.total ?? 0;
  const printedTotal = printed.data?.total ?? 0;

  const isLoading = toPrint.isLoading || printed.isLoading;
  const isError = toPrint.isError || printed.isError;

  function handlePrint(id: number, number: string) {
    printMut.mutate(id, {
      onSuccess: () => toast.success(`Заявка ${number} отмечена напечатанной`),
      onError: (e) => toast.error(e instanceof ApiError ? e.message : "Не удалось напечатать"),
    });
  }

  function handleIssue(id: number, number: string) {
    issueMut.mutate(id, {
      onSuccess: (res) =>
        toast.success(`Выдано по заявке ${number}. Проводка ${res.writeoff.number}`),
      onError: (e) => toast.error(e instanceof ApiError ? e.message : "Не удалось выдать"),
    });
  }

  function handleBatchPrint() {
    const ids = (toPrint.data?.items ?? []).map((r) => r.id);
    if (ids.length === 0) {
      toast.info("Нет заявок, требующих печати");
      return;
    }
    batchMut.mutate(ids, {
      onSuccess: (res) =>
        toast.success(`Напечатано: ${res.printed.length}, пропущено: ${res.skipped.length}`),
      onError: (e) => toast.error(e instanceof ApiError ? e.message : "Ошибка пакетной печати"),
    });
  }

  const columns: Column<RequestListItem>[] = [
    {
      key: "number",
      header: "№ заявки",
      render: (r) => <span className="font-mono text-[12.5px] text-muted-foreground">{r.number}</span>,
    },
    {
      key: "employee",
      header: "Сотрудник",
      // §6.3: реальное ФИО + категория из вычисляемых полей бэка (JOIN на users).
      render: (r) => (
        <EmployeeCell
          employeeId={r.employee_id}
          fullName={r.employee_full_name}
          category={r.employee_category}
        />
      ),
    },
    { key: "warehouse", header: "Склад", render: (r) => wh.name(r.warehouse_id) },
    { key: "date", header: "Создана", render: (r) => formatDate(r.created_at) },
    { key: "status", header: "Статус", render: (r) => <RequestStatusBadge status={r.status} /> },
  ];

  return (
    <section>
      <PageHeader
        breadcrumb="Документы › Очередь «К печати»"
        title="К печати"
        subtitle="Заявки, подтверждённые сотрудниками и ожидающие печати бланка"
        actions={
          <Button variant="outline" onClick={handleBatchPrint} disabled={batchMut.isPending}>
            <Printer className="h-4 w-4" />
            Пакетная печать
          </Button>
        }
      />

      <div className="mb-5 grid grid-cols-1 gap-3.5 sm:grid-cols-3">
        <KpiCard label="Требует печати" value={toPrintTotal} meta="в очереди" dot="warning" accent />
        <KpiCard label="Ожидают выдачи" value={printedTotal} meta="напечатано" dot="info" />
        <KpiCard label="Выдано сегодня" value={issuedToday} meta="за смену (из реестра)" dot="success" />
      </div>

      <div className="rounded-lg border">
        <DataTable
          caption="Очередь заявок к печати и выдаче"
          columns={columns}
          rows={rows}
          rowKey={(r) => r.id}
          isLoading={isLoading}
          isError={isError}
          onRetry={() => {
            toPrint.refetch();
            printed.refetch();
          }}
          emptyText="Очередь пуста — нет заявок к печати или выдаче"
          rowActions={(r) => (
            <>
              <Button
                size="sm"
                variant={r.status === "to_print" ? "default" : "outline"}
                onClick={() => handlePrint(r.id, r.number)}
                disabled={printMut.isPending}
              >
                <Printer className="h-4 w-4" />
                {r.status === "to_print" ? "Печать" : "Повтор"}
              </Button>
              <Button
                size="sm"
                variant={r.status === "printed" ? "default" : "outline"}
                onClick={() => handleIssue(r.id, r.number)}
                // ADR-3: «Выдано» неактивна до печати.
                disabled={r.status !== "printed" || issueMut.isPending}
                title={r.status !== "printed" ? "Доступно только после печати бланка" : undefined}
              >
                Выдано
              </Button>
            </>
          )}
        />
      </div>

      <p className="mt-4 flex gap-2 text-xs text-muted-foreground">
        <span className="font-medium text-foreground">Как это работает:</span>
        <span>
          Сотрудник подтверждает заявку → она попадает сюда со статусом «Требует печати».
          Завсклад печатает бланк, сотрудник ставит подпись на бумаге. Кнопка «Выдано»
          активна только после печати — по нажатию товар списывается со склада.
        </span>
      </p>
    </section>
  );
}
