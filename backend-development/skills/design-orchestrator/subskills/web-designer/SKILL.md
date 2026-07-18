---
name: web-designer
description: >
  Ветка WEB для роутера design-orchestrator. Активируется для лендингов, корпоративных
  сайтов, блогов, портфолио, e-commerce и SaaS. Использует базу ux-ui-agent-skills
  (пресеты стилей, 138 дизайн-систем, DTCG-токены, любой фреймворк). НЕ для CRM/дашбордов
  (там ветка interface-designer) и НЕ для 3D (там web3d-designer).
---

# Ветка WEB — маркетинговые сайты и витрины

Активирует базовый набор `ux-ui-agent-skills` (MIT, лежит в `vendor/ux-ui-agent-skills/`).
Если он установлен как отдельный скилл — его Request Router подхватит запрос сам; если
подключён как vendor-папка, читай `vendor/ux-ui-agent-skills/CLAUDE.md` перед генерацией.

## Когда активна
project_type ∈ { landing, corporate, blog, portfolio, ecommerce, saas }
и клиент НЕ выбрал 3D.

## Порядок секций по умолчанию
hero → доверие (логотипы/цифры) → ценность (features) → доказательства (отзывы/кейсы)
→ предложение (pricing / каталог) → финальный CTA → футер.
Для e-commerce добавь: каталог, карточку товара, корзину/checkout.
Для SaaS: pricing-таблицу с планами, сравнение, FAQ.

## Как применять стиль
1. Возьми `client_choice.style_preset` как базу. Можно смапить на одну из 138 дизайн-систем
   ux-ui-agent-skills (`/apply-aesthetic <name>` — linear, stripe, vercel, notion и т.д.).
2. Наложи `overrides` клиента (палитра, шрифты, must-have, avoid). Правки важнее пресета.
3. Сгенерируй DTCG-токены (primitive → semantic → component), затем верстай от них.

## Выход
HTML или React (стек из `client_choice.stack`, по умолчанию — HTML+Tailwind или React).
Для многостраничника — общие компоненты один раз, затем страницы.
Прогони мысленно контраст (AA) и адаптивность (280/320/414px) перед выдачей.

## Делегирование
Вся тяжёлая экспертиза (токены, компоненты, a11y-гейты, 138 систем) — в ux-ui-agent-skills.
Этот файл только фиксирует порядок секций и конверсионную логику маркетингового сайта.
