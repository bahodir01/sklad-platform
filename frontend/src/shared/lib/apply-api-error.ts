import { toast } from "sonner";
import type { UseFormSetError, FieldValues, Path } from "react-hook-form";
import { ApiError } from "@/shared/api/errors";

/**
 * Единый разбор ошибки мутации (§10):
 *   422 c details.errors → setError на поля по loc (имена = атрибуты контракта);
 *   иначе                → message в тост (готовый русский текст с бэка).
 *
 * message НИКОГДА не переписывается на клиенте.
 */
export function applyApiError<T extends FieldValues>(
  error: unknown,
  setError?: UseFormSetError<T>,
): void {
  if (!(error instanceof ApiError)) {
    toast.error("Непредвиденная ошибка");
    return;
  }

  const fieldErrors = error.fieldErrors();
  if (setError && fieldErrors.length > 0) {
    let applied = false;
    for (const fe of fieldErrors) {
      // loc = ['body', '<attr>'] — берём последний сегмент как имя поля формы.
      const name = fe.loc[fe.loc.length - 1];
      if (name && name !== "body") {
        setError(name as Path<T>, { type: "server", message: fe.msg });
        applied = true;
      }
    }
    if (applied) return;
  }

  toast.error(error.message);
}
