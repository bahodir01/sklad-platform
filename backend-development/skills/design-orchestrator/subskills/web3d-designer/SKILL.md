---
name: web3d-designer
description: >
  Ветка 3D для роутера design-orchestrator. Активируется, когда клиент выбрал 3D-дизайн
  (style_preset=3d), или project_type=immersive3d, или must_have содержит 3D-объект/сцену.
  Строит immersive-макеты на Three.js, React Three Fiber, Spline, WebGL со scroll-driven
  анимацией. Помнит: 3D должно служить цели, не быть украшением. НЕ для обычных лендингов
  без 3D (там web-designer) и НЕ для CRM (там interface-designer).
---

# Ветка 3D — immersive и scroll-driven макеты

Активирует базу `3d-web-experience` (лежит в `vendor/3d-web-experience/`).
Стек: Three.js, React Three Fiber, Spline, WebGL, GSAP ScrollTrigger.

## Когда активна
style_preset = 3d, ИЛИ project_type = immersive3d, ИЛИ client_choice.overrides.must_have
содержит упоминание 3D-объекта / сцены / конфигуратора. Эта ветка имеет приоритет:
если клиент выбрал 3D даже для простого лендинга — идём сюда.

## Главное правило (из 3d-web-experience)
3D должно служить цели: визуализация продукта, конфигуратор, storytelling — хорошо.
3D ради 3D — плохо: путает пользователя, жрёт батарею на мобильных, не помогает конверсии.
Перед генерацией реши: что именно 3D показывает и зачем. Если ответа нет — предложи клиенту
CSS 3D + GSAP вместо тяжёлого WebGL (80% эффекта за 20% сложности).

## Выбор стека под задачу
- Быстрый 3D-элемент, дизайнер уже сделал сцену → Spline (embed).
- React-проект, сложная интерактивная сцена → React Three Fiber.
- Максимум контроля/производительности, vanilla → чистый Three.js.
- Простой parallax/tilt на лендинге → CSS 3D + GSAP, без WebGL.

## Обязательное для 3D-макета
1. Hero с 3D-объектом или сценой, связанной с продуктом из brief.
2. Fallback: WebGL-детекция + статичная картинка/видео, если 3D не поддерживается.
3. Производительность: GLTF/GLB с Draco-сжатием, ленивая загрузка, quality tiers, лимит на мобильных.
4. Доступность: reduced-motion уважается; ключевой контент доступен без 3D.
5. Scroll-choreography (если нужно): GSAP ScrollTrigger, Lenis для плавного скролла.

## Как применять стиль
Пресет клиента задаёт настроение (luxury/bold хорошо ложатся на 3D). Overrides поверх.
Палитра и типографика — как в web-ветке, плюс параметры сцены (освещение, материалы, фон).

## Выход
HTML (single-file с Three.js через CDN) или React (R3F). Обязательно с fallback и
reduced-motion. Тяжёлые ассеты — по ссылке/плейсхолдеру, не инлайнить бинарь в артефакт.

## Делегирование
Вся 3D-экспертиза (рендер, оптимизация, asset pipeline, шейдеры) — в 3d-web-experience.
Этот файл фиксирует правило «3D со смыслом», fallback и выбор стека.
