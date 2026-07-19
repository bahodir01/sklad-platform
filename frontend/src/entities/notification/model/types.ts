import type { components } from "@/shared/api/schema";

/** М2 Уведомления. Типы — из schema.d.ts (§2). */
export type NotificationListItem = components["schemas"]["NotificationList"];
export type NotificationRead = components["schemas"]["NotificationRead"];
export type NotificationItemRead = components["schemas"]["NotificationItemRead"];
export type NotificationCreate = components["schemas"]["NotificationCreate"];
export type NotificationItemCreate = components["schemas"]["NotificationItemCreate"];
export type NotificationStatus = components["schemas"]["NotificationStatus"];
