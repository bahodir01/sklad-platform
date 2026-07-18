#!/usr/bin/env bash
# Установка внешних скиллов для design-orchestrator.
# Тянет три ветки (WEB / APP / 3D) в папку vendor/ рядом с оркестратором.
# Требования: git, node/npx. Проверь лицензии репозиториев перед коммерческим использованием.

set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENDOR="$ROOT/vendor"
mkdir -p "$VENDOR"

echo "==> design-orchestrator: установка внешних скиллов в $VENDOR"

# --- WEB: ux-ui-agent-skills (MIT) ---
echo "==> [WEB] ux-ui-agent-skills"
if [ ! -d "$VENDOR/ux-ui-agent-skills" ]; then
  git clone --depth 1 https://github.com/plugin87/ux-ui-agent-skills.git "$VENDOR/ux-ui-agent-skills"
else
  echo "    уже есть, пропускаю"
fi

# --- APP: interface-design ---
echo "==> [APP] interface-design"
if [ ! -d "$VENDOR/interface-design" ]; then
  git clone --depth 1 https://github.com/Dammyjay93/interface-design.git "$VENDOR/interface-design"
else
  echo "    уже есть, пропускаю"
fi

# --- 3D: 3d-web-experience (внутри монорепо ai4brands-design/claude-skills) ---
echo "==> [3D] 3d-web-experience"
if [ ! -d "$VENDOR/3d-web-experience" ]; then
  TMP="$(mktemp -d)"
  git clone --depth 1 https://github.com/ai4brands-design/claude-skills.git "$TMP/claude-skills"
  if [ -d "$TMP/claude-skills/3d-web-experience" ]; then
    cp -r "$TMP/claude-skills/3d-web-experience" "$VENDOR/3d-web-experience"
  else
    echo "    ВНИМАНИЕ: папка 3d-web-experience не найдена в репозитории — проверь структуру вручную"
  fi
  rm -rf "$TMP"
else
  echo "    уже есть, пропускаю"
fi

echo ""
echo "==> Готово. Структура:"
echo "    $ROOT/SKILL.md                     (роутер)"
echo "    $ROOT/subskills/{web,interface,web3d}-designer/  (ветки)"
echo "    $VENDOR/ux-ui-agent-skills/        (WEB)"
echo "    $VENDOR/interface-design/          (APP)"
echo "    $VENDOR/3d-web-experience/         (3D)"
echo ""
echo "Дальше: положи всю папку design-orchestrator в свою skills-директорию агента."
echo "Проверь LICENSE у interface-design и 3d-web-experience перед коммерческим использованием."
