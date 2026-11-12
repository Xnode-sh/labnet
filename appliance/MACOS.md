# Сборка на Mac (macOS или Linux-машина)

Кит `appliance/` портируемый. На маке единственное отличие — Docker ставится как
**Docker Desktop** (или `colima`), и на Apple Silicon нужен `linux/amd64`.

## 1. Docker

**Docker Desktop (проще):**
- Скачать с docker.com и установить, запустить, дождаться «Engine running».

**Или colima (легче):**
```bash
brew install colima docker
colima start --arch x86_64 --memory 8   # x86_64 нужен для termux-packages
```

Проверка: `docker info` без ошибок.

## 2. Сборка bootstrap

```bash
gh repo clone Xnode-sh/labnet ~/labnet && cd ~/labnet
bash appliance/build-bootstrap.sh
```

На Apple Silicon скрипт сам выставит `DOCKER_DEFAULT_PLATFORM=linux/amd64`.
Сборка идёт внутри Linux-контейнера — на macOS это нормально и работает.

## 3. APK

APK собирается уже на macOS-инструментах (не в Docker):
- JDK 17, Android SDK (cmdline-tools), Gradle — как в `red-term`.
- Форк `termux-app` → `sh.xnode.redterm`, `targetSdk 28`, вложить `bootstrap-*.zip`.
- `./gradlew assembleRelease` с release-keystore.

Подробно — `appliance/APK.md`.

## Что нужно один раз настроить (доступ)

Чтобы сборку сделала FREYA с телефона, добавь её публичный ключ (уже сгенерирован) в
`~/.ssh/authorized_keys` на маке, и скажи имя пользователя и адрес мака:

```bash
mkdir -p ~/.ssh && chmod 700 ~/.ssh
echo 'ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIEAinl2ZDLjQmJWqahV12DOKWRNS+nh629mcZzBnBKcH freya-phone@redlab' >> ~/.ssh/authorized_keys
chmod 600 ~/.ssh/authorized_keys
```

## Ограничения
- 8 ГБ RAM уйдёт в swap при сборке — лучше закрыть лишнее.
- Первый прогон долгий (десятки минут): тянет образ и пакеты.
- Публикация форка: GPLv3, исходники открыть.
