---
title: "CEF Dy — контракты данных"
type: protocol
status: active
version: "1.0"
updated: 2026-08-28
---

# Контракты данных

## 1. TAIPAN CEF observations

Основная таблица наблюдаемых должна содержать как минимум:

```text
scan_id
temperature_K
h
k
l
Q_Ainv
peak_energy_meV
peak_energy_sigma_meV
peak_area
peak_area_sigma
fwhm_meV
background_model
instrument_block_id
monitor
ki_kf_factor
detection_status
upper_limit
fit_window_meV
fit_quality_flag
```

Assignment наблюдаемой линии к конкретному CEF transition хранится отдельно от самого наблюдения.

## 2. Detection status

Рекомендуемые machine values:

```text
detected
censored
not_covered
excluded
```

`censored` означает, что область спектра была доступна экспериментально и отсутствие линии несёт информацию через upper limit/likelihood.

## 3. Work checkpoint output

Каждый checkpoint должен указывать logical input IDs, код/версию, команды, параметры, тесты, файлы результатов и checksum при необходимости.

## 4. Локальные пути

Machine-specific абсолютные пути не следует помещать в публичные project files. Используйте `configs/local_paths.yaml`, добавленный в `.gitignore`.

Пример:

```yaml
EXP-TAIPAN-001:
  path: "C:/.../CEF_Dy_Data/TAIPAN_raw"
```
