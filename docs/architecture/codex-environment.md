# Локальная среда Codex

## Базовая политика

- Основная модель проекта: `gpt-5.6-sol`
- Reasoning effort: `medium`
- Project override: `.codex/config.toml`
- Routing используется как рекомендация, а не как автоматическое переключение модели
- Подагенты запускаются только когда независимая работа окупает перенос контекста; для обычной связной задачи работа остаётся в одном потоке
- Security, тесты, обработка ошибок и сохранность пользовательских данных не сокращаются ради экономии контекста

## Установленные расширения

- Ponytail установлен как user-level plugin из marketplace `DietrichGebert/ponytail`
- Codex Model Routing установлен как user-level skill в `%USERPROFILE%\.codex\skills\codex-model-routing`
- Model Routing работает в offline/native advisory режиме. Dashboard, telemetry, login startup, API providers и платные API-вызовы не включены
- Project-specific skills находятся в `.agents/skills` и перечислены в корневом `AGENTS.md`

Ponytail hooks требуют отдельного просмотра и доверия через `/hooks`. До этого они пропускаются Codex. Не используйте обход проверки доверия.

## Экономия контекста

Сначала ищите точный символ, маршрут или тест через `rg`. Открывайте только связанные файлы и ограниченные фрагменты. Не загружайте зависимости, сборочные каталоги, caches, virtualenv, generated artifacts, базы и полные успешные логи без необходимости. Начинайте с targeted tests, расширяйте проверку после завершения функционального блока и запускайте полный набор quality gates перед PR.

При передаче незавершённой работы используйте `crm-context-handoff`; локальный файл `.codex/handoff.md` игнорируется Git.

## Проверка и откат

Проверка проекта:

```powershell
git status --short --branch
codex doctor --summary
codex plugin marketplace list
```

Проверка Model Routing без запуска dashboard:

```powershell
& "$env:USERPROFILE\.codex\skills\codex-model-routing\scripts\bootstrap.ps1" -Command doctor
& "$env:USERPROFILE\.codex\skills\codex-model-routing\scripts\bootstrap.ps1" -Command status
```

Откат user-level `config.toml` выполняется копированием сохранённого файла из `%USERPROFILE%\.codex\backups\personal-optimization-20261025-1925\config.toml` после сравнения с текущей конфигурацией. Ponytail удаляется командой `codex plugin remove ponytail@ponytail`; marketplace — `codex plugin marketplace remove ponytail`. Model Routing удаляется его `bootstrap.ps1 -Command uninstall`. Project-level изменения откатываются обычным Git diff/restore выбранных файлов.
