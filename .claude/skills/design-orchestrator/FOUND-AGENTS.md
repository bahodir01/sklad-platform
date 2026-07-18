# Найденные готовые агенты и скиллы (результаты поиска в интернете)

Ниже — то, что реально существует на GitHub и в маркетплейсах под твои критерии:
дизайн макетов от лендинга до больших проектов (CRM, дашборд, 3D) по ТЗ и выбору клиента.
Разбито на две группы: (A) целостные агенты-оркестраторы, которые сами разруливают тип
задачи, и (B) специализированные скиллы под отдельные типы.

---

## A. Целостные агенты-оркестраторы (сами маршрутизируют по типу задачи)

### 1. claude-workflow — мультиагентная оркестрация
- Сайт: https://claudeworkflow.com/
- Суть: 56 специалистов (frontend, backend, 3D, video, QA, research). Ты описываешь
  задачу простым текстом — Claude сам роутит её нужному специалисту, без ручного выбора
  агента. Есть бэклог с критериями приёмки, live web-UI со статусом всех агентов,
  21 MCP-сервер за одним прокси.
- Под твой кейс: это самый близкий готовый «мозг-роутер». Есть и frontend, и 3D-специалист.
- Минус: работает поверх Claude Code, отдельная подписка на оркестрацию.

### 2. Claude Design (Anthropic, официальный)
- Обзор: https://www.mindstudio.ai/blog/what-is-claude-design-anthropic-visual-prototyping
- Суть: описываешь продукт/бренд — генерирует анимированный адаптивный лендинг со скролл-
  эффектами, hover-состояниями, визуальной иерархией. Хорошо тянет и дашборд-UI, и
  Three.js 3D-сцены.
- Под твой кейс: один инструмент закрывает лендинг + дашборд + 3D. Ближе всего к «одному
  мощному агенту» из коробки, без сборки.

### 3. baoyu-design (JimLiu/baoyu-design)
- Репозиторий: https://github.com/jimliu/baoyu-design
- Суть: движок Claude Design, упакованный как локальный Agent Skill. Даёт почти все
  возможности claude.ai/design прямо в редакторе: мокапы, прототипы, лендинги, дашборды,
  мобильные приложения, слайды — всё как self-contained HTML. Лучше всего с Opus 4.8.
- Под твой кейс: готовый «дизайн-агент в одном скилле», локальный, без отдельной подписки.

### 4. Open-source Claude Design alternatives (GitHub topic claude-design)
- Топик: https://github.com/topics/claude-design
- Суть: локальные desktop-приложения (MIT), где твой coding-агент становится дизайн-движком:
  прототипы, лендинги, дашборды, слайды, картинки, видео. Экспорт HTML/PDF/PPTX/MP4.
  Мультимодельные (Claude, GPT, Gemini), BYOK.

### 5. hermes-agent-control-room (CryptoDmitry)
- Обзор: https://skillsllm.com/skill/hermes-agent-control-room
- Суть: шаблон «control room» — один агент-оркестратор как front door, маршрутизирует
  задачи специалистам через task-bus. Прямо сказано: оркестратор НЕ должен становиться
  гигантским агентом со всеми правами — он роутит и синтезирует. 866 звёзд, прошёл
  security-скан.
- Под твой кейс: это архитектурный образец «роутер + специалисты» — ровно тот принцип,
  что мы применили.

---

## B. Специализированные скиллы под отдельные типы (кирпичики)

### Лендинги / маркетинг / универсальный веб
- ux-ui-agent-skills (plugin87) — MIT. 138 дизайн-систем, DTCG-токены, любой фреймворк,
  встроенный Request Router, WCAG-гейты. https://github.com/plugin87/ux-ui-agent-skills
- borghei landing-page-generator — готовый формат ТЗ (Landing Page Brief) + фреймворки
  копирайтинга PAS/AIDA/BAB. https://github.com/borghei/Claude-Skills
- Taste-Skill (Leonxlnx) — самый звёздный сторонний дизайн-скилл, «анти-слоп» для frontend.

### CRM / дашборды / админки
- interface-design (Dammyjay93, бывший claude-design-skill) — плотность, таблицы, память
  решений в system.md. https://github.com/Dammyjay93/interface-design
- claude-design-skill (andykaufseo) — enterprise/SaaS-дашборды в духе Linear/Notion/Stripe.
  https://github.com/andykaufseo/claude-design-skill

### 3D / immersive
- 3d-web-experience — Three.js, R3F, Spline, WebGL. Правило «3D со смыслом».
  https://github.com/ai4brands-design/claude-skills (папка 3d-web-experience)
- cinematic-3d-website (gkren22) — MIT. Кинематографичные scroll-driven 3D (WebGPU/TSL,
  Theatre.js, GPU-частицы). https://github.com/gkren22/cinematic-3d-website
- claudedesignskills (freshtechbro) — 27 плагинов с прогрессивной загрузкой (Three.js,
  GSAP, R3F, Spline, Blender…). https://github.com/freshtechbro/claudedesignskills

---

## Вывод

Если нужно готовое «из коробки, ничего не собирать» — смотри в сторону **Claude Design**
(официальный) или **claude-workflow** (мультиагентный роутер с 56 специалистами).

Если нужен свой контролируемый агент под твою связку с аналитиком и своим выбором клиента —
собранный `design-orchestrator` (в этом же архиве) реализует архитектуру «роутер +
специалисты» по образцу hermes-agent-control-room, поверх лучших специализированных
скиллов из группы B.
