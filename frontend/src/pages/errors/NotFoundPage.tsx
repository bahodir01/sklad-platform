import { Link } from "react-router-dom";
import { FileQuestion } from "lucide-react";
import { Button } from "@/shared/ui/button";
import { HOME_ROUTE } from "@/shared/config/routes";

/** * — страница не найдена. */
export function NotFoundPage() {
  return (
    <div className="flex min-h-[60vh] flex-col items-center justify-center gap-4 text-center">
      <FileQuestion className="h-12 w-12 text-muted-foreground" aria-hidden="true" />
      <div>
        <h1 className="text-2xl font-semibold">Страница не найдена</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Такого раздела нет или он ещё не построен.
        </p>
      </div>
      <Button asChild variant="outline">
        <Link to={HOME_ROUTE}>На главную</Link>
      </Button>
    </div>
  );
}
