import type { components } from "@/shared/api/schema";

/** М4 Заявки. Типы — из schema.d.ts (руками не объявлять, §2). */
export type RequestListItem = components["schemas"]["RequestList"];
export type RequestRead = components["schemas"]["RequestRead"];
export type RequestCreate = components["schemas"]["RequestCreate"];
export type RequestItemCreate = components["schemas"]["RequestItemCreate"];
export type RequestStatus = components["schemas"]["RequestStatus"];
export type RequestCount = components["schemas"]["RequestCount"];
export type IssueResult = components["schemas"]["IssueResult"];
export type RegistryRow = components["schemas"]["RegistryRow"];
export type BatchPrintResult = components["schemas"]["BatchPrintResult"];
export type WriteoffRead = components["schemas"]["WriteoffRead"];
