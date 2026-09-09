# Руководство по исследовательской инфраструктуре

## Назначение и границы

Это руководство описывает переносимый инфраструктурный слой проекта CEF Dy /
DyFeO3: получение Git-репозитория, минимальное Python-окружение, локальные пути,
подключение внешних данных, границы Work recovery, резервное копирование и
процедуру будущей проверки на чистой машине.

Руководство не изменяет научные, provenance или authorization semantics. Оно не
подтверждает прохождение fresh-clone test, не выполняет резервное копирование и
не делает физическое расположение данных частью их канонической идентичности.

Текущее состояние подготовки:

```yaml
implementation_ready_for_fresh_clone_test: true
fresh_clone_test_passed: false
```

## Канонический tracked-слой

Канонический Git-tracked слой находится в:

```text
repository: oregu93/cef-dy
branch: main
```

`git clone` восстанавливает committed Markdown/YAML, исходный код, небольшие
reviewed-артефакты и историю Git. Канонические правила ведения базы знаний
заданы в [RESEARCH_KB_GUIDE](RESEARCH_KB_GUIDE.md).

`git clone` не восстанавливает:

- внешние raw и крупные derived data;
- игнорируемый `configs/local_paths.yaml`;
- `.venv` и другие локальные окружения;
- ignored Work-recovery snapshots;
- приватные материалы, credentials и secrets;
- независимую off-machine backup copy.

Абсолютный путь, mount point, sync-folder или cloud-provider path не являются
канонической идентичностью dataset/artifact.

## Tier 1: Linux bootstrap

Tier 1 — Linux Mint / Ubuntu-family Linux. Минимальный инфраструктурный слой:
Git, Python 3, `venv`, `pip` и tracked `requirements.txt`.

После получения канонического `main`:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt

python scripts/kb_refresh.py --check
python scripts/kb_validate.py
python scripts/kb_validate.py --strict
```

`requirements.txt` — только KB/infrastructure dependency baseline. Он не
описывает будущие научные fitting environments. Конкретный диапазон minor
версий Python этим руководством не объявляется; при будущем fresh-clone test
нужно записать фактические версии Python и PyYAML.

## Machine-local configuration

Логические идентификаторы постоянны:

```text
EXP-TAIPAN-001
EXP-XRD-001
WORK-OUTPUTS
PRIVATE-DATA
```

Физические пути задаются отдельно на каждой машине:

```bash
cp configs/local_paths.example.yaml configs/local_paths.yaml
```

После копирования замените нейтральные примеры реальными путями и проверьте,
что файл остаётся локальным и игнорируемым:

```bash
git check-ignore -q configs/local_paths.yaml
git status --short
```

`dataset_id` — каноническая логическая идентичность. Значение `path` в
`local_paths.yaml` — только machine-local physical resolution и не является
scientific provenance.

## Архитектура внешних данных

Raw и крупные данные находятся вне Git. При подключении и FC-07 verification
`EXP-TAIPAN-001` используется только read-only. Режим доступа к другим внешним
или derived-data областям определяется их соответствующим contract/job и этим
руководством не переопределяется. Контракт полей
и доступа задаёт [DATA_CONTRACTS](DATA_CONTRACTS.md). При наличии reviewed
inventory идентичность определяется сочетанием:

```text
dataset_id / artifact_id
dataset-root-relative POSIX path
byte size
SHA-256
canonical provenance record
```

Для `EXP-TAIPAN-001` канонический источник проверки —
[A-002 file inventory](../04_Results/Stage02R/W02-02R-A-002/file_inventory.csv)
с полями `dataset_id`, `source_file`, `file_size_bytes`, `source_checksum`.

### Документированная FC-07 verification procedure

Следующая команда предназначена только для будущего отдельно авторизованного
FC-07. В текущей реализации она не запускается. Она читает mapping и данные, но
ничего в dataset root не записывает.

```bash
python - <<'PY'
from __future__ import annotations

import csv
import hashlib
import os
import stat
import sys
from pathlib import Path, PurePosixPath

import yaml

DATASET_ID = "EXP-TAIPAN-001"
INVENTORY = Path(
    "04_Results/Stage02R/W02-02R-A-002/file_inventory.csv"
)
LOCAL_PATHS = Path("configs/local_paths.yaml")
REQUIRED_FIELDS = {
    "dataset_id",
    "source_file",
    "file_size_bytes",
    "source_checksum",
}


def fail(message: str) -> None:
    raise RuntimeError(message)


if os.name == "nt" and not hasattr(os.path, "isjunction"):
    fail("junction detection unavailable; refusing ambiguous Windows traversal")
is_junction = getattr(os.path, "isjunction", lambda _path: False)

mapping = yaml.safe_load(LOCAL_PATHS.read_text(encoding="utf-8"))
try:
    configured_root = Path(mapping[DATASET_ID]["path"]).expanduser()
except (KeyError, TypeError) as exc:
    fail(f"invalid mapping for {DATASET_ID}: {exc}")

lexical_root = Path(os.path.abspath(configured_root))
cursor = Path(lexical_root.anchor)
for part in lexical_root.parts[1:]:
    cursor /= part
    if cursor.exists() and (cursor.is_symlink() or is_junction(cursor)):
        fail(f"link-like mapped-root component: {cursor}")

if not lexical_root.is_dir():
    fail(f"dataset root is not a directory: {lexical_root}")
if lexical_root.is_symlink() or is_junction(lexical_root):
    fail(f"dataset root is link-like: {lexical_root}")
root = lexical_root.resolve(strict=True)

with INVENTORY.open("r", encoding="utf-8", newline="") as stream:
    reader = csv.DictReader(stream)
    if reader.fieldnames is None or not REQUIRED_FIELDS.issubset(reader.fieldnames):
        fail("canonical inventory fields are incomplete")
    rows = [row for row in reader if row["dataset_id"] == DATASET_ID]
    if not rows:
        fail(f"canonical inventory has no rows for {DATASET_ID}")

canonical = {}
for row in rows:
    rel = PurePosixPath(row["source_file"])
    if rel.is_absolute() or ".." in rel.parts or "\\" in row["source_file"]:
        fail(f"unsafe canonical source_file: {row['source_file']}")
    key = rel.as_posix()
    if key in canonical:
        fail(f"duplicate canonical source_file: {key}")
    canonical[key] = row

actual = {}
stack = [root]
while stack:
    directory = stack.pop()
    with os.scandir(directory) as entries:
        for entry in sorted(entries, key=lambda item: item.name):
            path = Path(entry.path)
            if entry.is_symlink() or is_junction(path):
                fail(f"link-like object in dataset tree: {path}")
            mode = entry.stat(follow_symlinks=False).st_mode
            resolved = path.resolve(strict=True)
            try:
                relative = resolved.relative_to(root).as_posix()
            except ValueError:
                fail(f"path escapes dataset root: {path}")
            if stat.S_ISDIR(mode):
                stack.append(path)
            elif stat.S_ISREG(mode):
                if relative in actual:
                    fail(f"duplicate actual relative path: {relative}")
                actual[relative] = path
            else:
                fail(f"unsupported filesystem object: {path}")

canonical_files = set(canonical)
actual_files = set(actual)
missing = sorted(canonical_files - actual_files)
extra = sorted(actual_files - canonical_files)
size_mismatch = []
sha256_mismatch = []

for relative in sorted(canonical_files & actual_files):
    row = canonical[relative]
    path = actual[relative]
    if path.stat().st_size != int(row["file_size_bytes"]):
        size_mismatch.append(relative)
        continue
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    if digest.hexdigest() != row["source_checksum"]:
        sha256_mismatch.append(relative)

status = "PASS" if not (
    missing or extra or size_mismatch or sha256_mismatch
) else "FAIL"

print(f"DATASET_ID={DATASET_ID}")
print(f"EXPECTED_FILES={len(canonical_files)}")
print(f"ACTUAL_FILES={len(actual_files)}")
print(f"MISSING={len(missing)}")
print(f"EXTRA={len(extra)}")
print(f"SIZE_MISMATCH={len(size_mismatch)}")
print(f"SHA256_MISMATCH={len(sha256_mismatch)}")
for label, values in (
    ("MISSING_PATHS", missing),
    ("EXTRA_PATHS", extra),
    ("SIZE_MISMATCH_PATHS", size_mismatch),
    ("SHA256_MISMATCH_PATHS", sha256_mismatch),
):
    for value in values:
        print(f"{label}={value}")
print(f"STATUS={status}")
sys.exit(0 if status == "PASS" else 1)
PY
```

Здесь:

```text
CANONICAL_FILES =
the complete A-002 file inventory for dataset_id == EXP-TAIPAN-001

ACTUAL_FILES =
all regular files recursively under the mapped EXP-TAIPAN-001 dataset root,
represented by dataset-root-relative POSIX paths
```

`MISSING` — canonical path, отсутствующий в `ACTUAL_FILES`; `EXTRA` — любой
regular file полного actual recursive census, отсутствующий в canonical
inventory. `SIZE_MISMATCH` и `SHA256_MISMATCH` сравниваются для общих путей.

Extension-only filter (например, `*.dat`) не может сужать ни один universe.
Symlink/junction, неразрешённый link-like object, path escape или неоднозначность
границы dataset root приводят к fail-closed остановке. Списки расхождений
сортируются; результат детерминирован. Процедура не выполняет scientific
re-analysis и не использует provider/absolute path как identity.

## Work recovery и disaster recovery

`work_recovery.py` — сохранение прерванного Work/session state и диагностика
возобновления. Подробный поведенческий контракт находится в
[WORK_RECOVERY_PROTOCOL](WORK_RECOVERY_PROTOCOL.md), а команды — в
[scripts/README](../scripts/README.md).

В рамках действующего контракта recovery snapshot может сохранять staged,
unstaged и non-ignored untracked Work state, index, diffs, hashes, control context
и diagnostics. Он не гарантирует восстановление после потери workstation/disk,
off-machine или raw/private-data backup, Git hosting, scientific validation,
scientific authorization либо automatic restoration.

Disaster recovery требует независимо восстановить Git-tracked слой, локальную
конфигурацию и внешние данные по их canonical identity. Work recovery не заменяет
эту процедуру.

## Backup и synchronization

Минимальная политика для незаменимых non-Git данных:

```text
irreplaceable non-Git data
=
primary working copy
+
independent off-machine copy
```

Копии не должны зависеть от одного физического диска или устройства.

```text
synchronization != backup
```

Synchronization переносит изменения и удаления и потому сама по себе не
доказывает независимость backup. Sync-provider может быть одним off-machine
слоем, но не становится canonical identity или единственным каноническим
источником.

Третья независимая копия особо ценных данных полезна, но не обязательна.
Периодический Git bundle вне GitHub также полезен, но не обязателен; GitHub
остаётся canonical source для tracked repository. Это руководство не выполняет
backup и не настраивает конкретного provider.

## Будущая fresh-clone проверка

FC-01…FC-09 — отдельная будущая операция. Ни один этап ниже не выполнен этой
реализацией.

### FC-01 — чистый Tier-1 Linux context

Не использовать прежние clone, `.venv`, `local_paths.yaml`, backup tree или
рабочий каталог исходной машины.

**PASS:** чистый context явно идентифицирован, состояние исходной машины не
унаследовано. **FAIL:** любой обязательный шаг неявно зависит от прежней машины.

### FC-02 — canonical clone

```bash
git clone https://github.com/oregu93/cef-dy.git
cd cef-dy
git switch main
git pull --ff-only
git rev-parse HEAD
git rev-parse origin/main
git status --short
```

**PASS:** `main`, `HEAD == origin/main`, tracked worktree clean; tested commit
записан. **FAIL:** clone/branch/identity check не проходит или имеется unexpected
tracked modification.

### FC-03 — venv и requirements

Записать Python/PyYAML versions и выполнить Tier-1 bootstrap из этого
руководства.

**PASS:** venv и installation из tracked `requirements.txt` успешны, скрытые
infrastructure dependencies отсутствуют. **FAIL:** требуется незадокументированный
package или ручной repair.

### FC-04 — KB validation

```bash
python scripts/kb_refresh.py --check
python scripts/kb_validate.py
python scripts/kb_validate.py --strict
git diff --check
git status --short
```

**PASS:** checks проходят (либо strict точно соответствует отдельно frozen
accepted-warning policy) и tracked files не меняются. **FAIL:** новая ошибка,
warning, generated change или dirty tracked state.

### FC-05 — Work recovery selftest

```bash
python scripts/work_recovery.py selftest
```

**PASS:** disposable fixture selftest успешен, canonical project files неизменны.
**FAIL:** selftest не проходит, меняет project/index или требует скрытую platform
dependency.

### FC-06 — local paths reconstruction

Создать `configs/local_paths.yaml` из tracked example, заполнить реальные пути и
выполнить `git check-ignore -q configs/local_paths.yaml`.

**PASS:** logical IDs сохранены, mapping игнорируется, old-machine knowledge не
требуется. **FAIL:** mapping попадает в Git или меняет canonical dataset identity.

### FC-07 — external-data reconnection

Подключить `EXP-TAIPAN-001` и выполнить документированную выше read-only
verification procedure.

**PASS:** `MISSING=0`, `EXTRA=0`, `SIZE_MISMATCH=0`, `SHA256_MISMATCH=0`,
`STATUS=PASS`; raw files неизменны. **FAIL:** любое расхождение, link/path
ambiguity, сужение census или raw write.

### FC-08 — отсутствие hidden knowledge

Компетентный оператор должен восстановить repository, Python, local mapping,
external-data identity, recovery/backup boundaries и FC-01…FC-09 только по
tracked документации. Секретные credentials и физический адрес private backup
могут оставаться вне Git.

**PASS:** обязательный процесс не зависит от chat history, personal path или
неявного знания. **FAIL:** такой dependency существует.

### FC-09 — финальная чистота

```bash
git status --short
git diff --check
```

**PASS:** нет unexpected tracked changes, local config/environment игнорируются,
test commit записан. **FAIL:** reconstruction создала неожиданную repository
mutation.

## Tier 2: Windows

Tier 2 означает reasonable compatibility tracked Markdown/YAML/Git architecture
и сохранение существующей Windows-compatible recovery behavior. Эта версия не
требует Windows fresh-clone test или CI matrix и не заявляет полную эквивалентность
Windows scientific workflow. Будущие scientific environments определяют свою
platform support отдельно.

## Канонические ссылки

- [RESEARCH_KB_GUIDE](RESEARCH_KB_GUIDE.md)
- [WORK_RECOVERY_PROTOCOL](WORK_RECOVERY_PROTOCOL.md)
- [DATA_CONTRACTS](DATA_CONTRACTS.md)
- [CHAT_BOOTSTRAPS](CHAT_BOOTSTRAPS.md)
- [scripts/README](../scripts/README.md)
- [A-002 checkpoint](../02_Work_Checkpoints/W02-02R-A-002.md)
- [A-002 file inventory](../04_Results/Stage02R/W02-02R-A-002/file_inventory.csv)

## Состояние реализации

```yaml
implementation_ready_for_fresh_clone_test: true
fresh_clone_test_passed: false
```

Это состояние означает готовность инструкций к отдельной проверке, а не
фактическое прохождение FC-01…FC-09.
