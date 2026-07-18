import { Outlet } from "react-router-dom";

/**
 * Каркас страницы входа (§9.1): центрированная карточка на приложенческом фоне.
 */
export function AuthLayout() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-background p-4">
      <div className="w-full max-w-sm">
        <div className="mb-6 flex flex-col items-center gap-3 text-center">
          <div className="grid h-12 w-12 place-items-center rounded-xl bg-primary text-lg font-bold text-primary-foreground">
            С
          </div>
          <div>
            <h1 className="text-lg font-semibold">Складской учёт</h1>
            <p className="text-sm text-muted-foreground">Вход в систему</p>
          </div>
        </div>
        <Outlet />
      </div>
    </div>
  );
}
