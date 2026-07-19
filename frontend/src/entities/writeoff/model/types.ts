import type { components } from "@/shared/api/schema";

/** ЭТАП 4: прямое списание порча/брак БЕЗ заявки (§4.4). Типы — из schema.d.ts. */
export type WriteoffCreate = components["schemas"]["WriteoffCreate"];
export type WriteoffRead = components["schemas"]["WriteoffRead"];
export type WriteoffItemCreate = components["schemas"]["WriteoffItemCreate"];
