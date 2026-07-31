# Как залить проект в свой GitHub

Токены и пароли никогда не пишите в чаты с ИИ-ассистентами — только локально в терминале.

## 1. Создайте новый репозиторий на GitHub

Зайдите на https://github.com/new, название например `dxf-from-photo`, ничего не инициализируйте (без README).

## 2. Создайте временный токен (если нужен HTTPS)

GitHub → Settings → Developer settings → Personal access tokens → Generate new token (fine-grained, срок действия 1 день, доступ только к нужному репозиторию).

Проще использовать SSH-ключ, если он уже настроен.

## 3. Залейте проект

В терминале на своей машине, из папки проекта:

```bash
cd dxf_from_photo
git init
git add .
git commit -m "Initial commit: DXF from photo tool"
git branch -M main
git remote add origin https://github.com/agronom28-crypto/dxf-from-photo.git
git push -u origin main
```

При запросе логина/пароля используйте временный токен как пароль.

## 4. Сразу отзовите токен

После успешного push зайдите обратно в Developer settings и нажмите Revoke на использованном токене.
