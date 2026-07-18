import {
  LayoutDashboard,
  Printer,
  Bell,
  PlusCircle,
  ArrowLeftRight,
  PackageMinus,
  Boxes,
  ArrowDownUp,
  Wallet,
  BarChart3,
  Package,
  Ruler,
  Warehouse,
  Coins,
  type LucideIcon,
} from "lucide-react";
import { ROUTES } from "@/shared/config/routes";

export interface NavItem {
  label: string;
  to: string;
  icon: LucideIcon;
  /** true — экран этапа 1 (живой). false — заглушка «в разработке». */
  live: boolean;
  /** Слот бейджа (напр. счётчик «К печати») — данные появятся на этапе 3. */
  badge?: number;
}

export interface NavSection {
  /** Заголовок группы (undefined — верхние пункты без группы). */
  title?: string;
  items: NavItem[];
}

/**
 * Конфиг навигации (макет заказчика). Пункты этапов 2–6 показываются, но ведут
 * на заглушку (live:false). Живой только раздел «Справочники» (М1).
 */
export const NAV_SECTIONS: NavSection[] = [
  {
    items: [
      { label: "Дашборд", to: ROUTES.dashboard, icon: LayoutDashboard, live: false },
      { label: "К печати", to: ROUTES.toPrint, icon: Printer, live: false },
    ],
  },
  {
    title: "Документы",
    items: [
      { label: "Уведомления", to: ROUTES.notifications, icon: Bell, live: false },
      { label: "Приобретения", to: ROUTES.acquisitions, icon: PlusCircle, live: false },
      { label: "Перемещения", to: ROUTES.transfers, icon: ArrowLeftRight, live: false },
      { label: "Расходы товара", to: ROUTES.writeoffs, icon: PackageMinus, live: false },
    ],
  },
  {
    title: "Склад",
    items: [
      { label: "Остатки", to: ROUTES.stock, icon: Boxes, live: false },
      { label: "Движения", to: `${ROUTES.stock}/movements`, icon: ArrowDownUp, live: false },
    ],
  },
  {
    title: "Деньги",
    items: [{ label: "Кассы", to: ROUTES.cash, icon: Wallet, live: false }],
  },
  {
    title: "Отчёты",
    items: [{ label: "Отчёты", to: ROUTES.reports, icon: BarChart3, live: false }],
  },
  {
    title: "Справочники",
    items: [
      { label: "Номенклатура", to: ROUTES.products, icon: Package, live: true },
      { label: "Единицы измерения", to: ROUTES.units, icon: Ruler, live: true },
      { label: "Склады", to: ROUTES.warehouses, icon: Warehouse, live: true },
      { label: "Типы расхода товара", to: ROUTES.expenseTypes, icon: PackageMinus, live: true },
      { label: "Виды расхода денег", to: ROUTES.expenseCategories, icon: Coins, live: true },
    ],
  },
];
