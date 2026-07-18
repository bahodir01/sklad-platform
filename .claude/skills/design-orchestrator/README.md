# design-orchestrator

Агент-роутер для дизайна веб-макетов. Принимает ТЗ от агента-аналитика и выбор клиента,
определяет тип проекта, активирует **один** нужный под-скилл и возвращает макет как
HTML/React артефакт + design tokens.

## Зачем роутер, а не монолит

Качественные дизайн-скиллы используют прогрессивную загрузку: грузят в контекст только то,
что нужно под задачу. Один монолитный SKILL.md с 3D-движком + CRM + лендингами жрал бы
контекст на каждом запросе, даже на простом лендинге. Роутер грузит vendor только активной
ветки.

## Архитектура

```
Агент-аналитик ──ТЗ──▶ design-orchestrator (роутер)
                              │ выбирает ветку по project_type + client_choice
              ┌───────────────┼───────────────┐
              ▼               ▼               ▼
          WEB-ветка       APP-ветка        3D-ветка
       web-designer    interface-designer  web3d-designer
              │               │               │
     ux-ui-agent-skills  interface-design  3d-web-experience
              └───────────────┴───────────────┘
                              ▼
                 Артефакт: HTML/React + design tokens
```

## Ветки

| project_type / сигнал клиента | Ветка | Внешний скилл |
|---|---|---|
| landing, corporate, blog, portfolio, ecommerce, saas | WEB | ux-ui-agent-skills (MIT) |
| crm, dashboard, admin, webapp, mobile | APP | interface-design |
| immersive3d, style_preset=3d, must_have содержит 3D | 3D | 3d-web-experience |

Правило приоритета: выбор клиента (3D) побеждает тип проекта.

## Установка

1. Установи внешние скиллы:
   ```bash
   bash scripts/install.sh
   ```
   Он склонирует три репозитория в `vendor/`.

2. Положи всю папку `design-orchestrator/` в skills-директорию своего агента
   (например `~/.claude/skills/` для Claude Code, или директорию скиллов твоей среды).

3. Проверь лицензии: ux-ui-agent-skills — MIT (свободно). У interface-design и
   3d-web-experience сверься с их LICENSE перед коммерческим использованием.

## Как вызывать

Роутер срабатывает на запросы вида «сгенерируй дизайн сайта по ТЗ», «собери макет из brief»,
«клиент выбрал 3D/CRM/лендинг». Подай ему два объекта:

- `brief` — ТЗ от аналитика (см. формат в `SKILL.md`)
- `client_choice` — выбор клиента (пресет + правки)

Роутер определит ветку, активирует под-скилл и вернёт макет.

## Выбор стиля клиентом (гибрид)

Клиент берёт `style_preset` как базу (minimal, bold, corporate, luxury, brutalist, 3d…),
а `overrides` (палитра, шрифты, must-have, avoid) накладываются поверх. Правки важнее пресета.

## Figma

По умолчанию выключено. Экспорт только по явному запросу и один экран за раз — Figma MCP
переполняет контекст на большом проекте. Дизайнеру лучше отдавать design tokens + HTML.

## Файлы

- `SKILL.md` — роутер (таблица маршрутизации, формат brief/client_choice, правила качества)
- `subskills/web-designer/` — WEB-ветка
- `subskills/interface-designer/` — APP-ветка (CRM/дашборд)
- `subskills/web3d-designer/` — 3D-ветка
- `skills.manifest.json` — карта веток и внешних репозиториев со ссылками и лицензиями
- `scripts/install.sh` — установщик внешних скиллов
