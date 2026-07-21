import * as React from "react";
import { Eye, EyeOff } from "lucide-react";
import { Input } from "./input";
import { cn } from "@/shared/lib/utils";

/**
 * Input с переключателем видимости пароля (глаз). Общий для формы создания
 * пользователя и сброса пароля (М7) — состояние видимости локально в поле,
 * наружу отдаёт обычный <input>-ref, совместим с register()/Controller.
 */
export const PasswordInput = React.forwardRef<
  HTMLInputElement,
  React.InputHTMLAttributes<HTMLInputElement>
>(({ className, ...props }, ref) => {
  const [visible, setVisible] = React.useState(false);

  return (
    <div className="relative">
      <Input {...props} ref={ref} type={visible ? "text" : "password"} className={cn("pr-9", className)} />
      <button
        type="button"
        onClick={() => setVisible((v) => !v)}
        tabIndex={-1}
        className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
        aria-label={visible ? "Скрыть пароль" : "Показать пароль"}
      >
        {visible ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
      </button>
    </div>
  );
});
PasswordInput.displayName = "PasswordInput";
