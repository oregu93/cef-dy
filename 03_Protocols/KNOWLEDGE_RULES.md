---
title: "CEF Dy — правила статусов знания"
type: protocol
status: active
version: "2.0"
updated: 2026-09-01
---

# Правила статусов знания

## 1. Основной принцип

Проект должен явно различать происхождение утверждения, его научный статус
и полноту provenance.

Наличие числа, графика или результата вычисления само по себе не определяет
его роль в научной аргументации.

Для существенного утверждения необходимо понимать:

```text
откуда оно получено
        ↓
что именно утверждается
        ↓
какую проверку оно прошло
        ↓
можно ли воспроизвести его происхождение
```

## 2. Типы знания

| Type | Назначение |
|---|---|
| `FACT` | Общепринятый или независимо установленный background fact. |
| `EVIDENCE` | Экспериментальное, литературное или иное свидетельство, используемое как основание для inference. |
| `RESULT` | Результат анализа, расчёта или model diagnostic внутри проекта. |
| `HYPOTHESIS` | Проверяемая физическая интерпретация, assignment или предположение. |
| `MODEL` | Явно определённая физическая или статистическая модель с установленным назначением и ограничениями. |
| `DECISION` | Принятое методологическое или организационное правило дальнейшей работы. |
| `OPEN_QUESTION` | Существенный нерешённый научный вопрос. |

`EVIDENCE`, `RESULT` и `HYPOTHESIS` не являются взаимозаменяемыми категориями.

Пример:

```text
F002 около 18.25 meV
    = experimental evidence

assignment F002 → Dy3+ CEF transition
    = hypothesis

PCM transition near the same energy
    = model result
```

Совпадение этих трёх объектов не превращает их автоматически в один
validated scientific fact.

## 3. Provenance triplet

Для существенных evidence/results рекомендуется разделять три независимых
характеристики:

```yaml
origin_type:
review_status:
provenance_status:
```

### 3.1. `origin_type`

Допустимые основные значения:

```text
experiment_raw
experiment_derived
literature
model_calculation
hypothesis
methodological_decision
```

Поле отвечает на вопрос:

> Откуда возникло утверждение или величина?

### 3.2. `review_status`

Основные значения:

```text
candidate
working
reviewed
validated
rejected
superseded
```

Поле отвечает на вопрос:

> Какой уровень содержательной проверки пройден внутри проекта?

`reviewed` не означает `validated`.

### 3.3. `provenance_status`

Основные значения:

```text
complete
partial
legacy_only
missing
```

Поле отвечает на вопрос:

> Насколько полно можно восстановить происхождение утверждения?

Например:

```yaml
origin_type: experiment_derived
review_status: reviewed
provenance_status: partial
```

означает, что результат научно просмотрен, но его reproducibility chain
ещё не полностью восстановлена.

## 4. EVIDENCE_REGISTER

Каждое существенное свидетельство может получить устойчивый ID:

```text
EV-###
```

В `EVIDENCE_REGISTER` следует хранить прежде всего:

- experimental observations;
- experiment-derived spectral parameters;
- upper limits;
- externally sourced quantitative constraints;
- literature-derived numerical values, если они непосредственно влияют
  на проектный inference.

Физический assignment наблюдения не должен скрываться внутри evidence.

Предпочтительно:

```yaml
interpretation:
  hypothesis_id: H-001
```

а не формулировка evidence как уже установленного assignment.

## 5. RESULT_REGISTER

Каждый существенный проектный результат анализа или расчёта получает:

```text
R-###
```

Примеры:

- numerical convention benchmark;
- model diagnostic;
- identifiability result;
- statistical diagnostic;
- воспроизводимый результат fit.

Экспериментальная спектральная особенность как таковая предпочтительно
хранится в `EVIDENCE_REGISTER`, а не маскируется под model result.

## 6. HYPOTHESIS_REGISTER

Гипотеза получает:

```text
H-###
```

если она влияет на:

- assignment;
- физическую интерпретацию;
- модельную постановку;
- выбор targeted test;
- дальнейший experimental или computational design.

Для гипотезы сохраняются supporting/conflicting evidence/results и
конкретные tests required.

## 7. MODEL_REGISTER

Существенная модель получает устойчивый:

```text
MOD-...
```

Для модели должны быть определены как минимум:

```text
purpose
class
status
parameters
what it can establish
what it cannot establish
```

Более общая или более параметрическая модель не считается автоматически
более физически правильной.

Модель должна отвечать на конкретный научный вопрос.

## 8. DECISION_REGISTER

Решение получает:

```text
D-###
```

если оно меняет:

- физическую постановку;
- statistical model;
- convention;
- критерии fit/validation;
- порядок вычислительных этапов;
- политику данных или репозитория.

Решение не является evidence.

Например:

> Не использовать F004 как обязательный CEF target

является methodological decision и ничего само по себе не доказывает
о физической природе F004.

## 9. Запрещённые подмены

- `RESULT` не становится `FACT` из-за низкого loss.
- `DECISION` не является доказательством физической истины.
- `HYPOTHESIS` не следует переписывать как established assignment.
- Spectral feature не является автоматически CEF transition.
- CEF transition не является автоматически CEF level assignment.
- Non-detection не означает отсутствие уровня без sensitivity analysis.
- Совпадение энергий не гарантирует правильность wavefunctions.
- Effective-charge parameter не является непосредственно измеренным
  ионным зарядом.
- Numerical optimum не доказывает identifiability.
- `reviewed` не означает `validated`.

## 10. Требования к `reviewed`

Для существенного `reviewed` результата должно быть известно:

```text
ID
statement / quantity
origin
evidence
review date
scope
limitations
provenance status
```

Если исходный artifact отсутствует, результат может оставаться `reviewed`,
но `provenance_status` не должен быть `complete`.

## 11. Требования к `validated`

`validated` допустим только после выполнения заранее определённых
validation criteria и сохранения reproducible evidence.

Для вычислительного результата это обычно означает наличие как минимум
одного:

```text
checkpoint
artifact
dataset
code_run
```

или эквивалентного воспроизводимого источника.

Legacy summary сам по себе недостаточен для `validated`.

## 12. Superseding

Исторически важные записи не удаляются.

Они получают:

```yaml
review_status: superseded
```

или соответствующий status конкретного register и ссылку на новый ID.

Это позволяет сохранять историю развития проекта без смешения старого и
текущего состояния.