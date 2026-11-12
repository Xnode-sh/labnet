# APPLIANCE — инсталлер, который вмещает Termux, ПО, ИИ и сеть судного дня

Цель: один артефакт, который ставится на любой Android и приносит готовое окружение —
**Termux + предустановленное ПО + labnet + Ковчег + ИИ**. Работает оффлайн.

## Уровень 1 — установщик в существующий Termux (готово)

```bash
git clone <labnet> ~/labnet
bash ~/labnet/install/install.sh
```

Скрипт ставит зависимости (`python`, `python-cryptography`, `git`), создаёт узел,
публикует объявление, готовит ИИ-промпт и запускает фоновый демон.

Состав предустановки (Termux-пакеты):
`python python-cryptography termux-api` (+ опц. `ollama`).

## Уровень 2 — оффлайн-бандл (флешка)

Для установки **без интернета** положи рядом с repo каталог `bundle/` с `.deb`-пакетами
Termux (`python`, `python-cryptography`, `termux-api`) и моделью GGUF, затем:

```bash
pkg install ./bundle/*.deb     # зависимости из бандла
bash install/install.sh        # остальная настройка
```

## Уровень 3 — APK, вмещающий Termux (форк) — путь сборки

Автоматизировано в `appliance/` (запускать на Linux с Docker):

```bash
bash appliance/build-bootstrap.sh   # клонирует termux-packages, собирает bootstrap
                                    # и вкладывает labnet + seed + промпт + установщик
bash appliance/APK.md               # дальнейшие шаги (форк termux-app → APK)
```

Это полный «инсталлер, который несёт Termux внутри». Опирается на форк лабы `red-term`
(см. его `docs/F0-bootstrap.md`). Сборка выполняется **на компьютере с Docker**, не на телефоне.

Шаги (кратко):

1. Форк `termux/termux-packages`, затем:
   ```bash
   export TERMUX_APP_PACKAGE=sh.xnode.redterm
   export TERMUX__PREFIX=/data/data/sh.xnode.redterm/files/usr
   ./scripts/run-docker.sh ./scripts/build-bootstraps.sh \
       --architectures aarch64 \
       --add "python,python-cryptography,termux-api,nano"
   ```
2. Вложить `labnet` (весь код), `install/persona-doomsday.md` и, по желанию, модель/бандл
   в bootstrap как `$PREFIX/share/labnet`.
3. Форк `termux/termux-app` → `sh.xnode.redterm`, вложить собранные `bootstrap-*.zip`,
   дебрендинг, `targetSdk 28` (иначе нет `exec`), подпись release-keystore.
4. Раздача: подписанный APK или свой F-Droid-репо. GPLv3 — исходники открыть.
5. First-run: автозапуск `install/install.sh` из bootstrap при первом старте.

**Блокер:** ребилд bootstrap требует Docker и часов сборки — на телефоне не выполняется.
Пункты 1–5 выполняются на рабочей станции (acer-lab/сервер).

## Что уже готово к вложению

- `labnet/` — вся сеть судного дня (сеть, Ковчег, чат, ИИ, sneakernet).
- `install/install.sh` — установка в Termux и first-run.
- `install/persona-doomsday.md` — промпт ИИ-узла.
- `docs/RUNBOOK.md` — инструкция для людей.
