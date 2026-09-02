---
title: "CEF Dy — руководство по ведению базы знаний"
type: protocol
status: active
version: "1.1"
updated: 2026-09-02
---

# Руководство по ведению базы знаний исследования

## 1. Основной принцип

База знаний должна отвечать на четыре разные группы вопросов:

- **Что мы сейчас считаем научно установленным или рабочим?** → `PROJECT_STATE.md`.
- **Что мы делаем сейчас, почему и в каком порядке?** → `PROJECT_CONTROL.md`.
- **Что именно было выполнено вычислительно и как это воспроизвести?** → `WORK_CHECKPOINTS`.
- **Как развивалась логика исследования?** → `RESEARCH_LOGBOOK`.

Смешивать эти функции в одном документе не следует.

### Каноническое текущее состояние

Для Git-tracked слоя проекта каноническим текущим состоянием считается:

```text
GitHub repository: oregu93/cef-dy
branch: main
```

после успешной проверки Knowledge Base и `git push`.

Приоритет источников текущего project state:

```text
1. явно предоставленный пользователем более новый локальный файл;
2. текущий committed GitHub main;
3. File Library snapshots;
4. Archive/legacy.
```

Файлы `PROJECT_STATE`, `PROJECT_CONTROL`, registers и protocols,
сохранённые ранее в ChatGPT File Library, считаются historical snapshots и
не предполагаются актуальными, если существует более новая версия в GitHub.

File Library используется прежде всего для литературы, книг, внешних
документов, experimental files и исторических snapshots.

Незакоммиченные локальные изменения не видны через GitHub и до `git push`
не считаются каноническим repository state.

## 2. Когда обновлять PROJECT_STATE

Обновляйте `PROJECT_STATE.md` только если изменилось текущее научное знание, например:

- появился новый `reviewed` или `validated` результат, важный для текущей модели;
- изменилось понимание экспериментального наблюдения;
- изменена operator/frame convention;
- закрыт существенный открытый вопрос;
- изменена текущая иерархия физических моделей;
- предыдущий результат `rejected` или `superseded`.

Не обновляйте `PROJECT_STATE` после каждого optimizer run, smoke test или технического исправления.

## 3. Когда обновлять PROJECT_CONTROL

Обновляйте `PROJECT_CONTROL.md`, если:

- меняется текущая задача или порядок задач;
- появляется/снимается blocker;
- принято стратегическое или методологическое решение;
- завершён review Work checkpoint;
- разрешён следующий Work job;
- изменился Definition of Done или существенный риск.

## 4. RESULT_REGISTER

Каждый существенный проектный результат получает устойчивый `id: R-###`.

### Статусы результатов

| Status | Смысл |
|---|---|
| `candidate` | Результат существует, но ещё не прошёл содержательную проверку. |
| `working` | Результат используется как рабочий ориентир, но validation неполна. |
| `reviewed` | Проверены смысл, метод, область применимости и provenance в доступном объёме. |
| `validated` | Выполнены заранее определённые validation criteria и сохранён воспроизводимый evidence. |
| `rejected` | Результат признан неприемлемым для заявленной интерпретации. |
| `superseded` | Исторически корректный результат заменён более новой версией. |

`reviewed` не означает `validated`.

### Требования к reviewed

Минимум:

```yaml
id: R-###
status: reviewed
statement: "..."
evidence:
  - kind: ...
    source: ...
review_date: YYYY-MM-DD
```

### Требования к validated

Дополнительно требуются:

```yaml
validation_criteria:
  - "..."
```

и хотя бы один evidence вида `checkpoint`, `artifact`, `dataset` или эквивалентный воспроизводимый источник. Простого пересказа старого Project State недостаточно.

## EVIDENCE_REGISTER

`EVIDENCE_REGISTER.yaml` содержит экспериментальные и внешние
свидетельства, которые используются как основания научного inference.

Основное правило:

> observation и physical assignment являются разными сущностями.

Experimental feature может иметь `review_status: reviewed`, в то время как
его CEF assignment остаётся `working` hypothesis.

Для существенного evidence рекомендуется хранить:

```yaml
id: EV-###
origin_type:
review_status:
provenance_status:
```

а также dataset/source/artifact metadata, достаточные для восстановления
его происхождения.

## MODEL_REGISTER

`MODEL_REGISTER.yaml` является канонической картой физических моделей
проекта.

Для каждой модели фиксируются:

```text
model_id
class
status
purpose
parameters
what it can establish
what it cannot establish
```

MODEL_REGISTER описывает научную роль модели, а не историю конкретного
optimizer run.

Конкретный запуск модели хранится в Work checkpoint / result artifact.

## 5. HYPOTHESIS_REGISTER

Гипотеза получает `id: H-###`, если она влияет на постановку эксперимента, fit, assignment или интерпретацию.

Рекомендуемые статусы:

```text
candidate
working
disfavored
rejected
superseded
```

Для гипотезы сохраняйте supporting/conflicting results и конкретные tests_required.

## 6. DECISION_REGISTER

Решение получает `id: D-###`, если оно меняет:

- физическую постановку;
- статистическую модель;
- convention;
- критерии fit/validation;
- порядок вычислительных этапов;
- политику данных/репозитория.

Решение не должно заменять научный результат: `D-005` может сказать «не использовать F004 как обязательный target», но не доказывает физическую природу F004.

## 7. WORK_CHECKPOINT

Checkpoint создаётся после каждого meaningful Work job.

Он отвечает на вопрос: **что было запущено, с какими входами, что получилось и можно ли это воспроизвести?**

Не следует превращать checkpoint в научную статью. Поле `scientific_interpretation_status` по умолчанию должно быть `not_reviewed`.

После review checkpoint либо:

- создаётся/обновляется запись `RESULT_REGISTER`;
- меняется hypothesis/decision;
- либо вычисление остаётся только техническим и не поднимается выше.

## 8. RESEARCH_LOGBOOK

Отдельная запись нужна, когда меняется логика исследования. Рекомендуемая структура:

```text
Контекст
Вопрос
Evidence
Результат
Интерпретация
Решение
Отклонено / отложено
Следующий шаг
Ссылки
```

Не создавать отдельную запись для каждого мелкого технического действия.

## Promotion workflow

Для experiment-derived knowledge:

```text
raw measurement
       ↓
analysis artifact / checkpoint
       ↓
EVIDENCE_REGISTER
       ↓
physical interpretation
       ↓
HYPOTHESIS_REGISTER
       ↓
model test
       ↓
RESULT_REGISTER
       ↓
scientific review
       ↓
PROJECT_STATE
```

Для model calculations:

```text
model definition
    ↓
MODEL_REGISTER
    ↓
Work checkpoint
    ↓
RESULT_REGISTER
    ↓
scientific review
    ↓
PROJECT_STATE, если результат меняет текущее знание
```

Ни один из переходов не является автоматическим.

## 10. Краткие re-entry blocks

Не редактировать вручную текст между markers:

```text
AUTO:STATE_REENTRY
AUTO:CONTROL_REENTRY
```

Изменяйте `PROJECT_METADATA.yaml`, затем запускайте:

```powershell
python scripts/kb_refresh.py
```

### Routine operational transitions

Для небольших declarative transitions operational/project-control state
используйте временный machine-local YAML payload и
`scripts/project_transition.py`:

```powershell
python scripts/project_transition.py /tmp/cef_project_transition.yaml --check
python scripts/project_transition.py /tmp/cef_project_transition.yaml --apply
```

Payload рекомендуется хранить в `/tmp/cef_project_transition.yaml` или другом
ignored/local location, а не
добавлять в Git для каждого шага. `project_transition.py` обновляет только
разрешённые operational/governance fields и строки существующей очереди,
после чего вызывает `kb_refresh.py`. Сам `kb_refresh.py` остаётся единственным
generator AUTO re-entry blocks.

Scientific promotion остаётся review-controlled и **не выполняется**
`project_transition.py`: script не изменяет scientific registers, не создаёт
решения и не повышает статус научных результатов.

## 11. Перед существенным Git commit

Рекомендуемый порядок:

```powershell
python scripts/kb_refresh.py
python scripts/kb_validate.py --strict
git status
git diff
git add <нужные файлы>
git commit -m "..."
```

## 12. Языковое правило

Содержательный текст, физические объяснения и методологические описания пишутся преимущественно по-русски.

Английский используется прежде всего для:

- `filenames`;
- YAML keys и значений перечислимых machine statuses;
- `IDs`;
- `labels`;
- `model_id`, `dataset_id`, `checkpoint_id`;
- имён функций, команд, программ и API;
- терминов, перевод которых создаёт реальную неоднозначность;
- machine-facing LLM bootstrap prompts и executable instruction contracts.

### Markdown и math portability

- Chemical/material names и ions в обычном тексте и headings записываются
  plain text: `Dy3+`, `Fe3+`, `DyFeO3`, `RFeO3`.
- LaTeX используется только для genuine mathematical notation.
- Inline mathematical quantities могут использовать `$...$`.
- Display equations используют standalone `$$` delimiters на отдельных
  строках.
- Canonical Markdown не использует `\[` / `\]` как display delimiters.
- Math delimiters не используются в Markdown headings.
- Code fence не должен случайно охватывать весь Markdown document.
- Canonical Markdown должен переносимо отображаться в Obsidian и GitHub.

### Lean governance

Generic project rules фиксируются один раз в shared protocols. Future Work
specifications должны содержать только job-specific delta и ссылаться на
общие contracts вместо их копирования.

Практический target для обычной будущей Work specification — примерно
200–500 строк и примерно 10–20 job-specific mandatory tests, когда это
реалистично. Это guidance, а не hard validator limit. Frozen A-001/A-002
specifications ретроспективно не сокращаются.

## 13. Принцип переносимости

Obsidian — интерфейс, а Markdown/YAML/Git — основной переносимый формат. Критически важная информация не должна существовать только внутри Obsidian-specific plugin syntax.

## 14. Работа с проектом на нескольких компьютерах

GitHub используется как центральная синхронизируемая версия текстового и программного слоя проекта.

ChatGPT при подключённом GitHub repository также использует committed
`main` как canonical current Knowledge Base. Это позволяет сохранять один
и тот же project context независимо от конкретного компьютера или браузера.

Для каждого компьютера существует отдельная локальная копия репозитория. Obsidian открывает локальную папку репозитория как vault.

Рекомендуемый цикл исследовательской сессии:

```text
START SESSION
    ↓
git pull
    ↓
python scripts/kb_refresh.py --check
    ↓
работа
    ↓
python scripts/kb_refresh.py
    ↓
python scripts/kb_validate.py --strict
    ↓
git status
    ↓
git diff
    ↓
git add <нужные файлы>
    ↓
git commit
    ↓
git push
```

Перед началом работы на другом компьютере следует сначала выполнить `git pull`.

Не рекомендуется вести длительные несинхронизированные изменения одного и того же файла одновременно на нескольких компьютерах.

Machine-specific пути к внешним данным должны храниться только в `configs/local_paths.yaml`, который исключён из Git. На разных компьютерах один и тот же `dataset_id` может указывать на разные физические пути.

## 15. Разделение Git и внешних данных

Git/GitHub является основным механизмом истории версий для:

- Markdown/YAML knowledge base;
- исходного кода;
- конфигураций воспроизводимых расчётов;
- небольших таблиц результатов;
- небольших reproducibility artifacts.

Большие или локальные данные хранятся отдельно, например в `CEF_Dy_Data/`:

- raw TAIPAN data;
- raw XRD data;
- крупные optimizer outputs;
- промежуточные массивы;
- приватные материалы;
- большие бинарные файлы.

Для больших данных может использоваться Yandex.Disk или другое внешнее хранилище.

GitHub и Yandex.Disk не должны выступать двумя независимыми источниками истории одного и того же Git-репозитория:

- GitHub — version control и источник истины для Git-tracked layer;
- Yandex.Disk — синхронизация/резервирование внешних данных и при необходимости резервная копия.

В knowledge base внешние данные идентифицируются устойчивыми `dataset_id`, а не абсолютными локальными путями.

## 16. QR-коды

QR-коды являются необязательным средством связи физического или статического объекта с устойчивым цифровым ресурсом.

Уместные случаи:

- постер или печатный отчёт;
- laboratory sheet;
- sample label;
- publication/supplement;
- ссылка на immutable Git commit/release;
- DOI или dataset landing page.

QR-коды не следует использовать:

- внутри обычной навигации Obsidian;
- для каждого результата, гипотезы или checkpoint;
- для временных URL;
- для локальных путей;
- вместо обычных Markdown links.

Предпочтительно кодировать в QR только устойчивый URL. Научные данные непосредственно в QR не помещать.

Генерация QR должна выполняться только по необходимости и не является обязательной частью базового workflow.

## 17. Git commit convention

Для истории проекта используется формат, основанный на Conventional Commits:

`type(scope): short description`

Заголовок commit пишется по-английски, поскольку является технической
машинно-ориентированной меткой. Научное объяснение при необходимости
помещается в расширенное тело commit.

Основные типы:

| Type | Назначение |
|---|---|
| `docs` | документация и knowledge base |
| `feat` | новая программная функциональность |
| `fix` | исправление ошибки |
| `refactor` | изменение структуры кода без изменения физического результата |
| `test` | тесты и проверки |
| `perf` | оптимизация производительности |
| `chore` | инфраструктура, конфигурация и служебные изменения |
| `build` | зависимости и build environment |
| `ci` | CI/CD и GitHub Actions |
| `revert` | отмена предыдущего изменения |

Дополнительные типы проекта:

| Type | Назначение |
|---|---|
| `data` | добавление или изменение отслеживаемых experimental/derived data |
| `analysis` | reviewed scientific analysis |
| `checkpoint` | фиксация Work checkpoint |

Рекомендуемые scopes:

`repo`, `obsidian`, `state`, `control`, `logbook`, `taipan`,
`cef`, `stage03d`, `conventions`, `pcm`, `mcphase`.

Примеры:

`docs(state): update current CEF project state`

`analysis(stage03d): review M0 and M1 fit results`

`checkpoint(w03): add W03-03D-A-001`

`fix(conventions): correct direct-to-canonical metadata`

`chore(obsidian): add shared vault configuration`

Основной принцип: один commit должен соответствовать одному логически цельному изменению. Не следует объединять в один commit независимые изменения научной модели, инфраструктуры и экспериментальных данных.
