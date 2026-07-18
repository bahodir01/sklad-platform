import { useState } from "react";
import { Archive, ArchiveRestore } from "lucide-react";
import { toast } from "sonner";
import { useUpdateCatalog } from "@/shared/api/catalog-hooks";
import type { CatalogEntity } from "@/shared/api/query-keys";
import { Button } from "@/shared/ui/button";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/shared/ui/alert-dialog";
import { applyApiError } from "@/shared/lib/apply-api-error";
import { archiveBody, isRowArchived } from "./archive-adapter";

interface ArchiveActionProps {
  entity: CatalogEntity;
  row: { id: number; is_active?: boolean; status?: "active" | "archived" };
  /** Человекочитаемое имя записи для текста подтверждения. */
  title: string;
}

/**
 * «В архив» / «Из архива» — единственный необратимый-на-вид жест (§9.6).
 * Подтверждение через AlertDialog; PATCH адаптированным телом; инвалидация —
 * в самом хуке useUpdateCatalog (§7.3). Разархивация — тем же компонентом.
 */
export function ArchiveAction({ entity, row, title }: ArchiveActionProps) {
  const [open, setOpen] = useState(false);
  const archived = isRowArchived(entity, row);
  const mutation = useUpdateCatalog<{ id: number }, Record<string, unknown>>(entity);

  const handleConfirm = () => {
    mutation.mutate(
      { id: row.id, body: archiveBody(entity, !archived) },
      {
        onSuccess: () => {
          setOpen(false);
          toast.success(archived ? "Запись возвращена из архива" : "Запись перемещена в архив");
        },
        onError: (error) => applyApiError(error),
      },
    );
  };

  return (
    <AlertDialog open={open} onOpenChange={setOpen}>
      <AlertDialogTrigger asChild>
        <Button variant="ghost" size="sm" aria-label={archived ? "Вернуть из архива" : "В архив"}>
          {archived ? <ArchiveRestore /> : <Archive />}
          {archived ? "Из архива" : "В архив"}
        </Button>
      </AlertDialogTrigger>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>
            {archived ? "Вернуть из архива?" : "Переместить в архив?"}
          </AlertDialogTitle>
          <AlertDialogDescription>
            {archived
              ? `Запись «${title}» снова станет активной.`
              : `Запись «${title}» будет скрыта из активных. Удаления в системе нет — только архивация.`}
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel disabled={mutation.isPending}>Отмена</AlertDialogCancel>
          <AlertDialogAction
            onClick={(e) => {
              e.preventDefault();
              handleConfirm();
            }}
            disabled={mutation.isPending}
          >
            {archived ? "Вернуть" : "В архив"}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
