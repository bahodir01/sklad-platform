import {
  Printer,
  ClipboardList,
  FileText,
  Wallet,
  Bell,
  PlusCircle,
  ArrowLeftRight,
  BarChart3,
  Package,
  Ruler,
  Warehouse,
  PackageMinus,
  Coins,
  type LucideIcon,
} from "lucide-react";
import type { UserRole } from "@/shared/api/model-types";
import { ROUTES } from "@/shared/config/routes";

export interface NavItem {
  label: string;
  to: string;
  icon: LucideIcon;
  /** Роли, которым пункт виден. undefined — виден всем аутентифицированным. */
  roles?: UserRole[];
  /** Динамический бейдж-счётчик. 'toPrint' — очередь печати (admin, AP-3). */
  badgeKey?: "toPrint";
}

export interface NavSection {
  /** Заголовок группы (undefined — верхние пункты без группы). */
  title?: string;
  items: NavItem[];
}

/**
 * Конфиг навигации (макет заказчика), теперь по ролям. Разделы «Документы»,
 * «Деньги», «Отчёты» и очередь «К печати» — только admin; «Мои заявки»/«Мои
 * расходы» — только сотрудник; «Справочники» — всем (чтение любой ролью).
 * Фильтрация по роли и подстановка бейджа — в AppSidebar.
 */
export const NAV_SECTIONS: NavSection[] = [
  {
    items: [
      { label: "К печати", to: ROUTES.toPrint, icon: Printer, roles: ["admin"], badgeKey: "toPrint" },
      { label: "Реестр выданных", to: ROUTES.registry, icon: ClipboardList, roles: ["admin"] },
      { label: "Мои заявки", to: ROUTES.myRequests, icon: FileText, roles: ["teacher", "worker"] },
      { label: "Мои расходы", to: ROUTES.myExpenses, icon: Wallet, roles: ["teacher", "worker"] },
    ],
  },
  {
    title: "Документы",
    items: [
      { label: "Уведомления", to: ROUTES.notifications, icon: Bell, roles: ["admin"] },
      { label: "Приобретения", to: ROUTES.acquisitions, icon: PlusCircle, roles: ["admin"] },
      { label: "Перемещения", to: ROUTES.transfers, icon: ArrowLeftRight, roles: ["admin"] },
      { label: "Списание (порча/брак)", to: ROUTES.writeoffs, icon: PackageMinus, roles: ["admin"] },
    ],
  },
  {
    title: "Деньги",
    items: [{ label: "Кассы", to: ROUTES.cash, icon: Coins, roles: ["admin"] }],
  },
  {
    title: "Отчёты",
    items: [{ label: "Отчёты", to: ROUTES.reports, icon: BarChart3, roles: ["admin"] }],
  },
  {
    title: "Справочники",
    items: [
      { label: "Номенклатура", to: ROUTES.products, icon: Package },
      { label: "Единицы измерения", to: ROUTES.units, icon: Ruler },
      { label: "Склады", to: ROUTES.warehouses, icon: Warehouse },
      { label: "Типы расхода товара", to: ROUTES.expenseTypes, icon: PackageMinus },
      { label: "Виды расхода денег", to: ROUTES.expenseCategories, icon: Coins },
    ],
  },
];
