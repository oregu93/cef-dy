# Work checkpoints

Каждый meaningful Work job получает отдельный Markdown checkpoint на основе `Templates/TEMPLATE_WORK_CHECKPOINT.md`.

Рекомендуемое имя:

```text
W03-03D-A-001.md
```

Checkpoint не переписывается после научного review, кроме явного erratum metadata.

## Multi-machine continuity

Work checkpoint является переносимым состоянием вычислительной задачи и не
должен зависеть от истории конкретного Work-чата.

Допустимые machine-local execution labels включают, например:

```text
W02-win
W02-Lin
```

Они относятся только к execution environment.

По умолчанию один Work job выполняется только в одном execution context.
Переключение между компьютерами желательно делать между атомарными Work jobs.

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

Если один и тот же logical dataset существует на нескольких компьютерах,
равенство dataset подтверждается по canonical relative paths, sizes и
checksums, а не по абсолютному пути.
