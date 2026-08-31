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
