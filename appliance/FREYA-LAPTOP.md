# FREYA на ноутбуке — собрать APK-аплаенс сети судного дня

Готовый текст-поручение. Скопировать в FREYA на Linux-машине с Docker.

---

FREYA, задача: собрать **установщик-аплаенс «сеть судного дня»** — APK, который вмещает
Termux с предустановленными ПО, ИИ и сетью labnet с Ковчегом.

Контекст: репозиторий `Xnode-sh/labnet` уже содержит всю сеть (45 тестов, CI зелёный),
набор выживания, промпт ИИ-узла и **сборочный кит** `appliance/`.

Требования к машине: Linux + Docker (запущен), ~10–15 ГБ диска, интернет.

Шаги:

1. Проверь окружение:
   ```bash
   docker info >/dev/null 2>&1 && echo docker-ok || echo "нет Docker"
   ```
   Нет Docker — поставь (`apt install docker.io`), запусти, повтори.

2. Получи репо (приватный — через `gh`):
   ```bash
   gh repo clone Xnode-sh/labnet ~/labnet || git clone <url> ~/labnet
   cd ~/labnet
   ```

3. Собери bootstrap с нашим ПО (долго — десятки минут, делает всё сама):
   ```bash
   bash appliance/build-bootstrap.sh
   ```
   Скрипт клонирует `termux/termux-packages`, собирает bootstrap под
   `sh.xnode.redterm`, ставит `python python-cryptography termux-api`,
   вкладывает labnet + seed + persona + installer.

4. Собери APK по инструкции `appliance/APK.md`:
   - форк/используй `red-term` (форк termux-app лабы) → пакет `sh.xnode.redterm`;
   - положи собранные `bootstrap-<arch>.zip` в `app/src/main/cpp/`;
   - `targetSdk 28`; release-keystore; `./gradlew assembleRelease`.

5. Проверь:
   ```bash
   unzip -p ~/labnet/appliance/.work/termux-packages/bootstrap-aarch64.zip | grep -a com.termux
   ```
   Должно быть **пусто**. APK при первом запуске вызывает `labnet-setup`.

6. Отчёт:
   - чекпоинт в `~/freya/state` и push в `Xnode-sh/freya`;
   - пришли ссылку на APK и коротко: что собрано, что осталось.
   - Блокер (нет Docker/нет прав) — сообщи **фактом**, не выдумывай успех.
   - Секреты (keystore, пароль сети, токены) в git не коммить.

Цель: подписанный APK или готовый `bootstrap-*.zip` + собранный APK, который ставится
на любой Android и оффлайн поднимает сеть с Ковчегом и набором выживания.
