import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import { Printer, Send, FileSignature, Copy, PackageCheck } from "lucide-react";
import { useRequestsByStatus, useRequestsCount } from "@/entities/request/api/queries";
import {
  useIssueRequest,
  useBatchPrint,
  useMarkSigned,
  useSubmitToAccounting,
} from "@/entities/request/api/mutations";
import { openBatchPdf, openRequestPdf } from "@/entities/request/api/pdf";
import { RequestStatusBadge } from "@/entities/request/ui/RequestStatusBadge";
import { EmployeeCell } from "@/entities/request/ui/EmployeeCell";
import type { RequestListItem, RequestQueueStatus, RegistryRow } from "@/entities/request/model/types";
import { useWarehouseLookup } from "@/entities/warehouse/lib/use-warehouse-lookup";
import { PageHeader } from "@/shared/ui/page-header";
import { KpiCard } from "@/shared/ui/kpi-card";
import { DataTable, type Column } from "@/shared/ui/data-table";
import { TablePagination } from "@/shared/ui/table-pagination";
import { Button } from "@/shared/ui/button";
import { cn } from "@/shared/lib/utils";
import { ApiError } from "@/shared/api/errors";
import { api } from "@/shared/api/client";
import type { Page } from "@/shared/api/types";
import { usePageParams } from "@/shared/lib/use-page-params";
import { formatDate, formatDateTime } from "@/shared/lib/format";
import { printRegistry } from "@/shared/lib/print";

/** 4 карточки-фильтра экрана «Выдачи товара» (спека13 §5). */
const FILTERS: { status: RequestQueueStatus; label: string; meta: string; dot: "warning" | "info" | "success" | "accent" }[] = [
  { status: "to_issue", label: "К выдаче", meta: "ждут выдачи со склада", dot: "warning" },
  { status: "issued", label: "К подписи", meta: "выдано, ждут подписи", dot: "info" },
  { status: "signed", label: "Подписано", meta: "подписаны, не переданы", dot: "success" },
  { status: "submitted", label: "Передано", meta: "переданы в бухгалтерию", dot: "accent" },
];

function errMsg(e: unknown, fallback: string): string {
  return e instanceof ApiError ? e.message : fallback;
}

/**
 * Экран «Выдачи товара» (М4, admin, спека13 §5) — журнал-трекер по статусной
 * модели draft→to_issue→issued→signed→submitted. Наверху 4 карточки-фильтра со
 * счётчиками; клик фильтрует список. Набор действий зависит от активного фильтра:
 *   К выдаче   → «Выдать» (списание со склада).
 *   К подписи  → пакетная печать (PDF по сотрудникам) + «Отметить подписано».
 *   Подписано  → «Передать в бухгалтерию» + печать реестра.
 *   Передано   → просмотр, перепечать копий/реестра.
 * Пакетные действия — по галочкам: невыбранные бэкенд не трогает (исключения).
 */
export function ToPrintPage() {
  const { page, size, setPage, get, setFilter } = usePageParams();
  const active = (get("status") as RequestQueueStatus) ?? "to_issue";

  const wh = useWarehouseLookup();
  const list = useRequestsByStatus(active, { page, size });

  // Счётчики карточек — по одному запросу на статус (все 4 всегда, для навигации).
  const cToIssue = useRequestsCount("to_issue");
  const cIssued = useRequestsCount("issued");
  const cSigned = useRequestsCount("signed");
  const cSubmitted = useRequestsCount("submitted");
  const countByStatus: Record<RequestQueueStatus, number> = {
    to_issue: cToIssue.data?.count ?? 0,
    issued: cIssued.data?.count ?? 0,
    signed: cSigned.data?.count ?? 0,
    submitted: cSubmitted.data?.count ?? 0,
  };

  const issueMut = useIssueRequest();
  const batchMut = useBatchPrint();
  const signMut = useMarkSigned();
  const submitMut = useSubmitToAccounting();

  // Выбор строк для пакетных действий. Сбрасывается при смене фильтра/страницы.
  const [selected, setSelected] = useState<Set<number>>(new Set());
  useEffect(() => setSelected(new Set()), [active, page]);

  const rows = list.data?.items ?? [];
  const selectable = active === "issued" || active === "signed";

  function toggleRow(r: RequestListItem) {
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

  // ── Действия ────────────────────────────────────────────────────────
  function handleIssue(r: RequestListItem) {
    issueMut.mutate(r.id, {
      onSuccess: (res) => toast.success(`Выдано по заявке ${r.number}. Проводка ${res.writeoff.number}`),
      onError: (e) => toast.error(errMsg(e, "Не удалось выдать")),
    });
  }

  function handleBatchPrint() {
    if (selectedIds.length === 0) {
      toast.info("Отметьте заявки для печати");
      return;
    }
    batchMut.mutate(selectedIds, {
      onSuccess: (res) => {
        toast.success(`Пачка ${res.batch_number}: напечатано ${res.printed.length}` +
          (res.skipped.length ? `, пропущено ${res.skipped.length}` : ""));
        void openBatchPdf(res.batch_id).catch((e) =>
          toast.error(errMsg(e, "Не удалось открыть PDF пачки")));
        setSelected(new Set());
      },
      onError: (e) => toast.error(errMsg(e, "Ошибка пакетной печати")),
    });
  }

  function handleMarkSigned() {
    if (selectedIds.length === 0) {
      toast.info("Отметьте подписанные заявки");
      return;
    }
    signMut.mutate(selectedIds, {
      onSuccess: (res) => {
        toast.success(`Подписано: ${res.signed.length}` +
          (res.skipped.length ? `, пропущено ${res.skipped.length}` : ""));
        setSelected(new Set());
      },
      onError: (e) => toast.error(errMsg(e, "Не удалось отметить подписанными")),
    });
  }

  function handleSubmit() {
    if (selectedIds.length === 0) {
      toast.info("Отметьте заявки для передачи");
      return;
    }
    submitMut.mutate(selectedIds, {
      onSuccess: (res) => {
        setSelected(new Set());
        toast.success(`Передано: ${res.submitted.length}. Реестр ${res.register_no ?? "—"}`, {
          action: res.register_no
            ? { label: "Печать реестра", onClick: () => printRequestRegistry(res.register_no!) }
            : undefined,
        });
      },
      onError: (e) => toast.error(errMsg(e, "Не удалось передать в бухгалтерию")),
    });
  }

  /** Печать официального реестра передачи по его номеру (перепечать). */
  async function printRequestRegistry(registerNo: string) {
    try {
      const res = await api.get<Page<RegistryRow>>("/requests/registry", {
        register_no: registerNo,
        page: 1,
        size: 200,
      });
      printRegistry<RegistryRow>(
        "Реестр передачи в бухгалтерию (товар)",
        `Реестр № ${registerNo}`,
        [
          { header: "№ заявки", value: (r) => r.request_number },
          { header: "№ проводки", value: (r) => r.writeoff_number },
          { header: "Сотрудник", value: (r) => r.employee_full_name?.trim() || `#${r.employee_id}` },
          { header: "Склад", value: (r) => wh.name(r.warehouse_id) },
          { header: "Выдано", value: (r) => formatDateTime(r.issued_at) },
          { header: "Передано", value: (r) => formatDate(r.submitted_at) },
        ],
        res.items,
      );
    } catch (e) {
      toast.error(errMsg(e, "Не удалось загрузить реестр"));
    }
  }

  /** Печать сопроводительного листа передачи по текущим подписанным строкам. */
  function printSignedSheet() {
    if (rows.length === 0) {
      toast.info("Нет строк для печати");
      return;
    }
    printRegistry<RequestListItem>(
      "Реестр к передаче в бухгалтерию (товар)",
      "Подписанные заявки, ожидающие передачи",
      [
        { header: "№ заявки", value: (r) => r.number },
        { header: "Сотрудник", value: (r) => r.employee_full_name?.trim() || `#${r.employee_id}` },
        { header: "Склад", value: (r) => wh.name(r.warehouse_id) },
        { header: "Выдано", value: (r) => formatDateTime(r.issued_at) },
      ],
      rows,
    );
  }

  // ── Колонки ─────────────────────────────────────────────────────────
  const baseColumns: Column<RequestListItem>[] = [
    {
      key: "number",
      header: "№ заявки",
      render: (r) => <span className="font-mono text-[12.5px] text-muted-foreground">{r.number}</span>,
    },
    {
      key: "employee",
      header: "Сотрудник",
      render: (r) => (
        <EmployeeCell employeeId={r.employee_id} fullName={r.employee_full_name} category={r.employee_category} />
      ),
    },
    { key: "warehouse", header: "Склад", render: (r) => wh.name(r.warehouse_id) },
    {
      key: "date",
      header: active === "to_issue" ? "Создана" : "Выдана",
      render: (r) => (active === "to_issue" ? formatDate(r.created_at) : formatDateTime(r.issued_at)),
    },
  ];

  const submittedColumns: Column<RequestListItem>[] =
    active === "submitted"
      ? [
          { key: "register", header: "№ реестра", render: (r) => (
            <span className="font-mono text-[12.5px]">{r.submitted_register_no ?? "—"}</span>
          ) },
          { key: "submitted_at", header: "Передано", render: (r) => formatDate(r.submitted_at) },
        ]
      : [];

  const columns: Column<RequestListItem>[] = [
    ...baseColumns,
    ...submittedColumns,
    { key: "status", header: "Статус", render: (r) => <RequestStatusBadge status={r.status} /> },
  ];

  // ── Панель действий фильтра ─────────────────────────────────────────
  const toolbar = (() => {
    if (active === "issued") {
      return (
        <>
          <Button variant="outline" onClick={handleBatchPrint} disabled={batchMut.isPending || selectedIds.length === 0}>
            <Printer className="h-4 w-4" />
            Печать пачкой{selectedIds.length ? ` (${selectedIds.length})` : ""}
          </Button>
          <Button onClick={handleMarkSigned} disabled={signMut.isPending || selectedIds.length === 0}>
            <FileSignature className="h-4 w-4" />
            Отметить подписано
          </Button>
        </>
      );
    }
    if (active === "signed") {
      return (
        <>
          <Button variant="outline" onClick={printSignedSheet} disabled={rows.length === 0}>
            <Printer className="h-4 w-4" />
            Печать реестра
          </Button>
          <Button onClick={handleSubmit} disabled={submitMut.isPending || selectedIds.length === 0}>
            <Send className="h-4 w-4" />
            Передать в бухгалтерию{selectedIds.length ? ` (${selectedIds.length})` : ""}
          </Button>
        </>
      );
    }
    return null;
  })();

  return (
    <section>
      <PageHeader
        breadcrumb="Документы › Выдачи товара"
        title="Выдачи товара"
        subtitle="Журнал выдач: выдача со склада, пакетная печать и подпись, передача в бухгалтерию"
        actions={toolbar}
      />

      {/* Карточки-фильтры со счётчиками (клик → фильтр списка). */}
      <div className="mb-5 grid grid-cols-1 gap-3.5 sm:grid-cols-2 lg:grid-cols-4">
        {FILTERS.map((f) => (
          <button
            key={f.status}
            type="button"
            onClick={() => setFilter("status", f.status === "to_issue" ? undefined : f.status)}
            aria-pressed={active === f.status}
            className={cn(
              "rounded-xl text-left transition-shadow focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
              active === f.status && "ring-2 ring-primary",
            )}
          >
            <KpiCard
              label={f.label}
              value={countByStatus[f.status]}
              meta={f.meta}
              dot={f.dot}
              accent={active === f.status}
            />
          </button>
        ))}
      </div>

      <div className="rounded-lg border">
        <DataTable
          caption="Заявки на выдачу товара по статусу"
          columns={columns}
          rows={rows}
          rowKey={(r) => r.id}
          isLoading={list.isLoading}
          isError={list.isError}
          onRetry={() => list.refetch()}
          emptyText="Нет заявок в этом статусе"
          selectedKeys={selectable ? selected : undefined}
          onToggleRow={selectable ? toggleRow : undefined}
          onToggleAll={selectable ? toggleAll : undefined}
          rowActions={(r) => {
            if (active === "to_issue") {
              return (
                <Button size="sm" onClick={() => handleIssue(r)} disabled={issueMut.isPending}>
                  <PackageCheck className="h-4 w-4" />
                  Выдать
                </Button>
              );
            }
            if (active === "submitted") {
              return (
                <>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => void openRequestPdf(r.id).catch((e) => toast.error(errMsg(e, "Не удалось открыть PDF")))}
                  >
                    <Copy className="h-4 w-4" />
                    Копия
                  </Button>
                  {r.submitted_register_no ? (
                    <Button size="sm" variant="outline" onClick={() => printRequestRegistry(r.submitted_register_no!)}>
                      <Printer className="h-4 w-4" />
                      Реестр
                    </Button>
                  ) : null}
                </>
              );
            }
            return <span className="text-xs text-muted-foreground">—</span>;
          }}
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
