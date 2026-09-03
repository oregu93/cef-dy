---
title: "CEF Dy — восстановление контекста Work-сессии"
type: protocol
status: active
version: "1.0"
updated: 2026-09-04
---

# Work recovery: сохранение и диагностика

Сбой Work-chat, backend 404, браузера или сессии не означает, что файловая работа
потеряна или что научный job нужно повторить. `scripts/work_recovery.py` сохраняет
локальные данные и диагностирует продолжение; ничего автоматически не восстанавливает.
Этот протокол не авторизует B-001 или другой научный job и не меняет Project Control.

## NORMAL ATOMIC JOB START

В обычной оболочке внутри репозитория, непосредственно перед уже авторизованным job:

```text
python scripts/work_recovery.py start --job <JOB_ID>
```

Сохранить выведенные snapshot ID, HEAD, branch и путь; затем выполнять только
авторизованный job. Утилита допускает dirty worktree: staged, unstaged и untracked
работа сохраняется. Требование чистого canonical HEAD определяется конкретным job,
а не общей recovery-утилитой.

## EMERGENCY / WORK-CHAT FAILURE

1. Не запускать `reset`, `restore`, `checkout`, `clean`, `stash` или `pull`.
2. Открыть обычную оболочку в репозитории.
3. Выполнить PANIC-снимок:

   ```text
   python scripts/work_recovery.py panic --job <JOB_ID>
   ```

4. Перезапустить или переподключить Work-chat.
5. Выполнить проверку и вывести компактный отчёт:

   ```text
   python scripts/work_recovery.py audit --job <JOB_ID>
   python scripts/work_recovery.py report --job <JOB_ID>
   ```

6. Передать JSON-отчёт восстановленной Work-сессии.
7. Продолжать только с первого проверенного незавершённого шага, после сверки
   authorization, checkpoint и provenance.
8. Не перезапускать научный job целиком из-за сбоя сессии, если scientific/control
   review явно не потребовал rerun.

## Снимки и целостность

Хранилище: `CEF_Dy_Backup/work_recovery/<JOB_ID>/<UTC_TIMESTAMP>_<MODE>/`.
UTC-идентификатор включает случайный суффикс для исключения коллизий; MODE —
`start` или `panic`. Перед записью проверяется существующее Git ignore-правило.
Если каталог не игнорируется или уже содержит tracked-пути, утилита останавливается.
Она не изменяет `.gitignore` и не выбирает запасное хранилище.

Снимок содержит metadata, status, binary diff рабочего дерева и index, обе
whitespace-проверки, diff stat, списки путей, точные рабочие и staged-версии,
а также текущие `PROJECT_CONTROL.md` и `PROJECT_METADATA.yaml` в `control_context/`.
Untracked non-ignored файлы обязательны; ignored data trees не копируются.
Удалённые пути фиксируются без выдуманной копии. Index читается непосредственно
из Git: его версия не подменяется рабочим файлом. При конфликтах доступные stages
сохраняются отдельно в `index_conflicts/`; бинарная копия index также сохраняется.
Списки путей используют JSON-quoted строки, чтобы не потерять пробелы и спецсимволы.

`snapshot_manifest.json` содержит упорядоченные пути, byte size и SHA-256 всех
артефактов, кроме самого manifest и COMPLETE. COMPLETE дополнительно запечатывает
SHA-256 manifest. Снимок действителен только при наличии COMPLETE и успешной
проверке всех хэшей и полноты списка файлов.
`latest_start.json` — переносимый относительный указатель, не symlink.

При ошибке команды, копирования, хэширования, whitespace-check или изменении
данных во время capture возвращается ненулевой код; COMPLETE не публикуется.
Частичный материал не удаляется. Symlink/junction и изменённый submodule требуют
ручного сохранения: утилита отказывается следовать им или молча пропускать их.

## Интерпретация AUDIT / REPORT

По умолчанию проверяется последний complete PANIC, иначе последний complete START.
Можно указать `--snapshot <SNAPSHOT_ID>` для того же job. Повреждённый выбранный
снимок не заменяется молча более старым. Более новый partial snapshot блокирует
автоматическое признание продолжения безопасным.

- `SAFE_TO_RESUME: yes`: integrity PASS, HEAD/branch прежние, нет Git operation
  или unresolved index, whitespace-checks PASS, captured files/status/index совпадают.
- `review_required`: integrity и Git baseline безопасны, но файлы/status/index
  изменились после выбранного снимка; нужна ручная сверка.
- `no`: нарушение integrity, смена HEAD/branch, merge/rebase/cherry-pick или другой
  обнаруженный опасный Git state, whitespace failure либо ненадёжная идентификация.

Коды выхода: 0 — yes; 1 — review_required; 2 — no/ошибка.
`FILES_RECOVERED` означает число сохранённых копий; `restored` всегда 0.
Отчёт не раскрывает полный diff по умолчанию. PANIC отдельно показывает изменение
HEAD/branch относительно последнего START: эти сведения также требуют review.
`yes` не является научным review, разрешением на execution или доказательством
завершённости какого-либо вычислительного шага.

## Границы безопасности и срок хранения

Production-команды выполняют только read-only Git inspection и записывают данные
в проверенное ignored-хранилище. Optional Git locks и автоматический refresh
index отключены. Нет автоматического fix/restore; tracked-файлы и index не меняются.
Решение о ручном восстановлении остаётся у пользователя / восстановленного Work-chat.

Recovery snapshots локальны, игнорируются Git и не являются каноническими научными
результатами. Не удалять последний полезный START/PANIC, пока затронутый job не
прошёл review и его canonical capture не committed/pushed. Work recovery никогда
не отменяет canonical Git/provenance rules.

Проверка инфраструктуры:

```text
python scripts/work_recovery.py selftest
```

Selftest использует только собственный временный Git fixture с фиксированными
тестовыми объектами/index; никакие Git write-команды не запускаются. Искусственные
изменения и corruption выполняются исключительно в этом disposable fixture,
не в CEF-Dy. После теста временный fixture удаляется стандартным tempfile cleanup.
Это единственное исключение из сохранения временного материала: реальные recovery
снимки утилита не удаляет.
