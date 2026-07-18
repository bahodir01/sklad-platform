import type { ReactNode } from "react";
import { Table, TableBody, TableCaption, TableCell, TableHead, TableHeader, TableRow } from "./table";
import { Skeleton } from "./skeleton";
import { Button } from "./button";

export interface Column<T> {
  /** Ключ для React и заголовка. */
  key: string;
  header: string;
  /** Числовые колонки — вправо (§11). */
  align?: "left" | "right";
  render: (row: T) => ReactNode;
}

interface DataTableProps<T> {
  /** Скрытая подпись таблицы для скринридера (§11). */
  caption: string;
  columns: Column<T>[];
  rows: T[];
  rowKey: (row: T) => string | number;
  isLoading: boolean;
  isError: boolean;
  onRetry?: () => void;
  /** Действия строки (правка/архив) — колонка справа. */
  rowActions?: (row: T) => ReactNode;
  /** Пустое состояние: текст + опционально кнопка «Добавить». */
  emptyText?: string;
  emptyAction?: ReactNode;
  /** Число колонок-скелетов при загрузке. */
  skeletonRows?: number;
}

/**
 * Чистая презентация (§9.2): ни useQuery, ни useMutation. Четыре состояния —
 * loading (скелет строк), error (текст + Retry), empty («Записей нет»), data.
 */
export function DataTable<T>({
  caption,
  columns,
  rows,
  rowKey,
  isLoading,
  isError,
  onRetry,
  rowActions,
  emptyText = "Записей нет",
  emptyAction,
  skeletonRows = 6,
}: DataTableProps<T>) {
  const colCount = columns.length + (rowActions ? 1 : 0);

  return (
    <Table>
      <TableCaption className="sr-only">{caption}</TableCaption>
      <TableHeader>
        <TableRow>
          {columns.map((col) => (
            <TableHead key={col.key} className={col.align === "right" ? "text-right" : undefined}>
              {col.header}
            </TableHead>
          ))}
          {rowActions ? (
            <TableHead className="text-right">
              <span className="sr-only">Действия</span>
            </TableHead>
          ) : null}
        </TableRow>
      </TableHeader>
      <TableBody>
        {isLoading ? (
          Array.from({ length: skeletonRows }).map((_, i) => (
            <TableRow key={`sk-${i}`}>
              {Array.from({ length: colCount }).map((__, j) => (
                <TableCell key={`sk-${i}-${j}`}>
                  <Skeleton className="h-5 w-full" />
                </TableCell>
              ))}
            </TableRow>
          ))
        ) : isError ? (
          <TableRow>
            <TableCell colSpan={colCount} className="py-10 text-center">
              <p className="mb-3 text-sm text-muted-foreground">
                Не удалось загрузить данные.
              </p>
              {onRetry ? (
                <Button variant="outline" size="sm" onClick={onRetry}>
                  Повторить
                </Button>
              ) : null}
            </TableCell>
          </TableRow>
        ) : rows.length === 0 ? (
          <TableRow>
            <TableCell colSpan={colCount} className="py-10 text-center">
              <p className="mb-3 text-sm text-muted-foreground">{emptyText}</p>
              {emptyAction}
            </TableCell>
          </TableRow>
        ) : (
          rows.map((row) => (
            <TableRow key={rowKey(row)}>
              {columns.map((col) => (
                <TableCell
                  key={col.key}
                  className={col.align === "right" ? "text-right tabular-nums" : undefined}
                >
                  {col.render(row)}
                </TableCell>
              ))}
              {rowActions ? (
                <TableCell className="text-right">
                  <div className="flex justify-end gap-1">{rowActions(row)}</div>
                </TableCell>
              ) : null}
            </TableRow>
          ))
        )}
      </TableBody>
    </Table>
  );
}
