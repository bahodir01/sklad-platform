import { ChevronLeft, ChevronRight } from "lucide-react";
import { Button } from "./button";

interface TablePaginationProps {
  page: number;
  size: number;
  total: number;
  pages: number;
  onPageChange: (page: number) => void;
}

export function TablePagination({ page, size, total, pages, onPageChange }: TablePaginationProps) {
  if (total === 0) return null;

  const from = (page - 1) * size + 1;
  const to = Math.min(page * size, total);

  return (
    <nav
      className="flex items-center justify-between gap-4 pt-4"
      aria-label="Навигация по страницам"
    >
      <p className="text-sm text-muted-foreground" aria-live="polite">
        {from}–{to} из {total}
      </p>
      <div className="flex items-center gap-2">
        <Button
          variant="outline"
          size="sm"
          onClick={() => onPageChange(page - 1)}
          disabled={page <= 1}
          aria-label="Предыдущая страница"
        >
          <ChevronLeft className="h-4 w-4" />
          Назад
        </Button>
        <span className="text-sm tabular-nums">
          {page} / {Math.max(1, pages)}
        </span>
        <Button
          variant="outline"
          size="sm"
          onClick={() => onPageChange(page + 1)}
          disabled={page >= pages}
          aria-label="Следующая страница"
        >
          Вперёд
          <ChevronRight className="h-4 w-4" />
        </Button>
      </div>
    </nav>
  );
}
