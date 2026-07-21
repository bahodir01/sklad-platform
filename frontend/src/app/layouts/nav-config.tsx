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
  Send,
  Network,
  Users,
  type LucideIcon,
} from "lucide-react";
import type { UserRole } from "@/shared/api/model-types";
import { ROUTES } from "@/shared/config/routes";

/**
 * URL графа codebase-memory (родной UI индексатора). Настраивается через
 * VITE_CODEBASE_GRAPH_URL; дефолт — локальный dev-порт индексатора. В проде,
 * если сервис не поднят, пункт можно скрыть, задав пустую строку.
 */
export const CODEBASE_GRAPH_URL: string =
  import.meta.env.VITE_CODEBASE_GRAPH_URL ?? "http://localhost:9749";

export interface NavItem {
  label: string;
  to: string;
  icon: LucideIcon;
  /** Роли, которым пункт виден. undefined — виден всем аутентифицированным. */
  roles?: UserRole[];
  /** Динамический бейдж-счётчик. 'toPrint' — очередь печати (admin, AP-3). */
  badgeKey?: "toPrint";
  /** Внешняя ссылка (открывается в новой вкладке), а не роут приложения. */
  external?: boolean;
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
      { label: "Выдачи товара", to: ROUTES.toPrint, icon: Printer, roles: ["admin"], badgeKey: "toPrint" },
      { label: "Реестр передачи", to: ROUTES.registry, icon: ClipboardList, roles: ["admin"] },
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
    items: [
      { label: "Кассы", to: ROUTES.cash, icon: Coins, roles: ["admin"] },
      { label: "Передача расходов", to: ROUTES.cashExpenses, icon: Send, roles: ["admin"] },
    ],
  },
  {
    title: "Отчёты",
    items: [{ label: "Отчёты", to: ROUTES.reports, icon: BarChart3, roles: ["admin"] }],
  },
  {
    title: "Администрирование",
    items: [{ label: "Пользователи", to: ROUTES.users, icon: Users, roles: ["admin"] }],
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
  {
    title: "Разработка",
    items: [
      {
        label: "Граф кодовой базы",
        to: CODEBASE_GRAPH_URL,
        icon: Network,
        roles: ["admin"],
        external: true,
      },
    ],
  },
];
