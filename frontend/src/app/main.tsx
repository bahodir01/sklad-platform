import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { RouterProvider } from "react-router-dom";
import "../index.css";
import { installZodRu } from "@/shared/lib/zod-ru";
import { AppProviders } from "./providers";
import { router } from "./router";

// Русская локализация сообщений Zod — до первого рендера форм.
installZodRu();

const rootEl = document.getElementById("root");
if (!rootEl) throw new Error("Элемент #root не найден");

createRoot(rootEl).render(
  <StrictMode>
    <AppProviders>
      <RouterProvider router={router} />
    </AppProviders>
  </StrictMode>,
);
