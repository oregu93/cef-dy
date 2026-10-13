# Work checkpoints

Для каждой содержательно значимой Work-задачи создаётся отдельный Markdown-checkpoint на основе `Templates/TEMPLATE_WORK_CHECKPOINT.md`.

Рекомендуемое имя:

```text
W03-03D-A-001.md
```

После научного рецензирования checkpoint не переписывается, кроме явно оформленных метаданных erratum.

## Работа на нескольких компьютерах

Work checkpoint является переносимым состоянием вычислительной задачи и не
должен зависеть от истории конкретного Work-чата.

Допустимые локальные обозначения среды выполнения включают, например:

```text
W02-win
W02-Lin
```

Они относятся только к среде выполнения.

По умолчанию одна Work-задача выполняется только в одном контексте выполнения.
Переключаться между компьютерами желательно между атомарными Work-задачами.

Для продолжения на другой машине источником состояния являются:

```text
canonical Git commit
approved job specification
tracked analysis code
reviewed Work checkpoint
tracked small artifacts
checksums of external artifacts
verified logical dataset identity
```

`configs/local_paths.yaml` остаётся локальным и не переносится через Git.

Если один и тот же логический набор данных существует на нескольких компьютерах,
его идентичность подтверждается по каноническим относительным путям, размерам
и контрольным суммам, а не по абсолютному пути.

## Индекс directory checkpoints

- [`ORCH-M1B-RELIABILITY-REBUILD-001`](ORCH-M1B-RELIABILITY-REBUILD-001/) —
  historical M1b implementation, deployment and recovery evidence.
- [`ORCH-M2-DATAFLOW-00-FANIN-CLOSURE-001`](ORCH-M2-DATAFLOW-00-FANIN-CLOSURE-001/) —
  M2 dependency/result fan-in implementation evidence.
- [`ORCH-M2-SEMANTIC-RESULT-REVIEW-FIX-001`](ORCH-M2-SEMANTIC-RESULT-REVIEW-FIX-001/) —
  semantic-result review correction evidence.
- [`CEF-WKB-CANONICAL-AUDIT-RECOVERY-2026-10-12`](CEF-WKB-CANONICAL-AUDIT-RECOVERY-2026-10-12/AUDIT_REPORT.md) —
  current-state audit and minimal repair candidate.
- [`CEF-WKB-CURRENT-STATE-REFRESH-2026-10-13`](CEF-WKB-CURRENT-STATE-REFRESH-2026-10-13/REFRESH_REPORT.md) —
  bounded operational refresh after timer recovery and RESULT publication.
