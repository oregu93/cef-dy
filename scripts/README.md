# Скрипты базы знаний

## Обновить re-entry blocks

```powershell
python scripts/kb_refresh.py
```

Проверить без изменения файлов:

```powershell
python scripts/kb_refresh.py --check
```

## Проверить структуру

```powershell
python scripts/kb_validate.py
```

Строгий режим перед существенным commit:

```powershell
python scripts/kb_validate.py --strict
```

`kb_validate.py` проверяет YAML, IDs, статусы, evidence requirements, ссылки, основные ошибки Markdown/LaTeX и синхронизацию re-entry blocks.

## Восстановление после сбоя Work-сессии

`work_recovery.py` — standard-library-only утилита для Windows/Linux. Она сохраняет
локальные ignored-снимки и диагностирует продолжение, не восстанавливая файлы
автоматически и не меняя tracked-файлы или Git index.

```text
python scripts/work_recovery.py start --job <JOB_ID>
python scripts/work_recovery.py panic --job <JOB_ID>
python scripts/work_recovery.py audit --job <JOB_ID>
python scripts/work_recovery.py report --job <JOB_ID>
python scripts/work_recovery.py selftest
```

`start` — baseline перед авторизованным job; `panic` — немедленное сохранение при
сбое; `audit` — проверка snapshot/current state; `report` — компактный JSON-handoff.
`selftest` проверяет утилиту в изолированном временном Git fixture.
Для `audit`/`report` доступен `--snapshot <SNAPSHOT_ID>`.

Хранилище: `CEF_Dy_Backup/work_recovery/` (должно уже игнорироваться Git).
Полный порядок действий и ограничения: [WORK_RECOVERY_PROTOCOL](../03_Protocols/WORK_RECOVERY_PROTOCOL.md).
