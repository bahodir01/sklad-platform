import { Link } from "react-router-dom";
import { ShieldAlert } from "lucide-react";
import { Button } from "@/shared/ui/button";
import { HOME_ROUTE } from "@/shared/config/routes";

/** /403 — недостаточно прав (§5). Не путать с /login (там «войди заново»). */
export function ForbiddenPage() {
  return (
    <div className="flex min-h-[60vh] flex-col items-center justify-center gap-4 text-center">
      <ShieldAlert className="h-12 w-12 text-warning" aria-hidden="true" />
      <div>
        <h1 className="text-2xl font-semibold">Недостаточно прав</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          У вашей роли нет доступа к этому разделу.
        </p>
      </div>
      <Button asChild variant="outline">
        <Link to={HOME_ROUTE}>На главную</Link>
      </Button>
    </div>
  );
}
