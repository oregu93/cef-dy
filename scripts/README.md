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

## Проверить Scientific Understanding schema

```powershell
python scripts/scientific_understanding_validate.py
python scripts/scientific_understanding_validate.py --selftest
```

До отдельно авторизованного concept pilot отсутствие каталога
`06_Scientific_Understanding/` является валидным состоянием с нулём notes.
Frozen contract находится в
[SCIENTIFIC_UNDERSTANDING_SCHEMA_V1_0](../03_Protocols/SCIENTIFIC_UNDERSTANDING_SCHEMA_V1_0.md).

## Восстановление после сбоя Work-сессии

`work_recovery.py` — утилита для Windows/Linux, использующая только стандартную
библиотеку Python. Она сохраняет локальные игнорируемые Git-снимки и диагностирует продолжение, не восстанавливая файлы
автоматически и не меняя tracked-файлы или Git index.

```text
python scripts/work_recovery.py start --job <JOB_ID>
python scripts/work_recovery.py panic --job <JOB_ID>
python scripts/work_recovery.py audit --job <JOB_ID>
python scripts/work_recovery.py report --job <JOB_ID>
python scripts/work_recovery.py selftest
```

`start` — исходное состояние перед авторизованной задачей; `panic` — немедленное
сохранение при сбое; `audit` — проверка снимка и текущего состояния; `report` —
компактная передача состояния в формате JSON. `selftest` проверяет утилиту
в изолированном временном тестовом Git-репозитории.
Для `audit`/`report` доступен `--snapshot <SNAPSHOT_ID>`.

Хранилище: `CEF_Dy_Backup/work_recovery/` (должно уже игнорироваться Git).
Полный порядок действий и ограничения: [WORK_RECOVERY_PROTOCOL](../03_Protocols/WORK_RECOVERY_PROTOCOL.md).

Настройка окружения, локальных путей и внешних данных описана в
[RESEARCH_INFRASTRUCTURE_GUIDE](../03_Protocols/RESEARCH_INFRASTRUCTURE_GUIDE.md).

## Локальный deterministic task orchestrator

Контракт: [TASK_ORCHESTRATOR_CONTRACT_V1_0](../03_Protocols/TASK_ORCHESTRATOR_CONTRACT_V1_0.md).
Конфигурация по умолчанию является `shadow`, GitHub polling выключен, а LLM
dispatch отсутствует. Сначала скопируйте example в ignored machine-local config:

```text
cp configs/task_orchestrator.example.yaml configs/task_orchestrator.yaml
python scripts/orchestrate_tasks.py --config configs/task_orchestrator.yaml integrity-check
python scripts/orchestrate_tasks.py --config configs/task_orchestrator.yaml poll-once
python -m unittest discover -s scripts/task_orchestrator/tests -t scripts -v
```

### M2 production routing and operator dashboard

M2 extends M1b; it does not replace the M1b controller, durable state, quota
lane, or timer. Enable `routing.enabled` to register roles 00/01/02/03/04/07
from the exact canonical sections in `03_Protocols/CHAT_BOOTSTRAPS.md` and to
prefer deterministic local work before bounded AI work. Tasks in
`WAITING_USER` remain visible and do not block unrelated READY tasks.

Resource routing keeps five independent lanes: `LOCAL_DETERMINISTIC`,
`LOCAL_OSS_MODEL`, `NON_WORK_AI`, `WORK_CODEX`, and `HUMAN_DECISION`. Semantic
tasks declare `inputs.resource_requirement` and may provide ordered
`inputs.allowed_lanes`. Local OSS and non-Work lanes remain disabled until a
real programmatic interface is explicitly verified; persistent chats are never
claimed as autonomous workers. Exhausting `WORK_CODEX` moves only that lane to
quota wait and leaves every verified non-Work lane schedulable.

The operator dashboard is a separate service and reads the existing SQLite
state with SQLite query-only mode. Enable `dashboard.enabled`, then run:

```bash
python scripts/orchestrate_tasks.py --config configs/task_orchestrator.yaml dashboard-serve
```

The stable default URL is <http://127.0.0.1:8765/>; JSON is available at
<http://127.0.0.1:8765/api/status>. The server accepts only GET/HEAD, binds only
to `127.0.0.1`, has no write API, and is intentionally deployed as a separate
systemd service so a dashboard failure cannot stop orchestration.

`poll-once` только читает GitHub Issues и локально отслеживает labelled tasks,
включая их ручное закрытие и изменение через web UI. `shadow` и `dry-run`
никогда не исполняют READY tasks. Для bounded deterministic pilot
оператор вручную меняет mode на `pilot`, оставляя `llm.dispatch_enabled: false`,
после отдельного review. `approve` и `resume` являются локальными auditable
операциями; quota reset сам по себе ничего не возобновляет.
