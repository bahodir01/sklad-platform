import { Construction } from "lucide-react";

/**
 * Заглушка «в разработке» для пунктов меню этапов 2–6. Раздел показан в
 * sidebar (по макету), но экран строится не на этапе 1 — ведёт сюда.
 */
export function StubPage({ title = "Раздел" }: { title?: string }) {
  return (
    <div className="flex min-h-[60vh] flex-col items-center justify-center gap-4 text-center">
      <Construction className="h-12 w-12 text-warning" aria-hidden="true" />
      <div>
        <h1 className="text-2xl font-semibold">{title}</h1>
        <p className="mt-1 max-w-md text-sm text-muted-foreground">
          Раздел в разработке. Он появится на следующих этапах проекта. Сейчас
          доступны справочники.
        </p>
      </div>
    </div>
  );
}
