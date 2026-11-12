# APK, который вмещает Termux — сборка на ноутбуке

Кратко: **это делает FREYA на Linux-ноутбуке/сервере с Docker**, не на телефоне.
Ниже — что именно и в каком порядке.

## Требования к машине
- Linux с **Docker** (запущен), интернет для первого `git clone`.
- ~10–15 ГБ диска, несколько часов времени.
- Желательно — рабочая станция лабы (acer-lab). Если Docker нет: `apt install docker.io`.

## Шаг 1 — bootstrap с нашим ПО

```bash
git clone <labnet> ~/labnet && cd ~/labnet
bash appliance/build-bootstrap.sh
```

Скрипт: клонирует `termux/termux-packages`, собирает в Docker bootstrap под префикс
`sh.xnode.redterm`, ставит `python python-cryptography git termux-api nano rsync`,
затем **вкладывает** labnet, набор выживания, промпт ИИ и установщик (`usr/share/labnet`),
добавляет `usr/bin/labnet-setup`. На выходе — `bootstrap-aarch64.zip` с нашим префиксом.

Проверка: `unzip -p bootstrap-aarch64.zip | grep -a com.termux` должен быть **пуст**.

## Шаг 2 — форк приложения Termux (GPLv3)

Основа — уже существующий форк лабы `red-term` (см. его `docs/F0-bootstrap.md`).
На машине:

1. Форк `termux/termux-app` → пакет `sh.xnode.redterm` (рефактор `com.termux`).
2. Положить собранные `bootstrap-<arch>.zip` в `app/src/main/cpp/`.
3. `targetSdk 28` (иначе Android запрещает `exec` — суть Termux теряется).
4. `./gradlew assembleRelease` с release-keystore.
5. Раздача: подписанный APK или свой F-Droid-репо. Исходники открыть (GPLv3).

## Шаг 3 — первый запуск

При первом старте приложение распаковывает bootstrap, дальше человек выполняет:

```bash
labnet-setup            # ставит узел, пароль сети, набор выживания, включает демон
labnet web              # чат в браузере
```

## Что уже готово к вложению (проверено на телефоне)
- `labnet/` — вся сеть судного дня (45 тестов, CI зелёный).
- `install/install.sh` — установка + первый запуск, наполняет Ковчег.
- `install/persona-doomsday.md` — промпт ИИ-узла.
- `seed/` — набор выживания (вода, первая помощь, еда, энергия, связь, укрытие).
- `docs/RUNBOOK.md` — инструкция для людей.

## Блокеры и примечания
- Без Docker сборка bootstrap невозможна.
- `targetSdk 28` = только sideload / свой F-Droid (Google Play отпадает) — принято осознанно.
- Размер bootstrap растёт от тулсета — держать под контролем.
- Публикация форка: сохранить GPLv3 и выложить исходники.
