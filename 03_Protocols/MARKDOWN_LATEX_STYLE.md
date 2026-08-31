---
title: "Markdown и LaTeX — правила проекта"
type: protocol
status: active
version: "1.1"
updated: 2026-08-28
compatibility: [Obsidian, GitHub, CommonMark]
---

# Markdown и LaTeX — правила проекта

## Цель

Минимизировать случаи, когда физические обозначения в Obsidian показываются как код или plain text, и сохранить переносимость Markdown между Obsidian, GitHub и VS Code.

## 1. Встроенная математика

Стандарт проекта:

```markdown
CEF-параметр $B_l^m$ и энергия $E_1=18.25~\mathrm{meV}$.
```

Не помещайте математические обозначения в backticks, если они должны отображаться как формула.

## 2. Отдельные формулы

Используйте отдельный блок с пустой строкой до и после:

```markdown
$$
\hat H_{\mathrm{CEF}}
=
\sum_{l,m} B_l^m \hat O_l^m.
$$
```

## 3. Многострочные формулы

Окружения LaTeX должны находиться внутри math delimiters:

```markdown
$$
\begin{aligned}
E_1 &= 6.45~\mathrm{meV},\\
E_2 &= 18.20~\mathrm{meV},\\
E_3 &= 27.90~\mathrm{meV}.
\end{aligned}
$$
```

Не используйте standalone `\begin{aligned}` вне `$$...$$`.

## 4. Матрицы

```markdown
$$
U=
\begin{pmatrix}
1 & 0 & 0\\
0 & 0 & -1\\
0 & 1 & 0
\end{pmatrix}.
$$
```

## 5. Формулы внутри списков

Избыточный отступ может превратить display math в code block. Предпочтительный формат:

```markdown
1. Первый пункт.

   Используется соотношение

   $$
   E=\hbar\omega.
   $$

2. Второй пункт.
```

Если конкретный renderer отображает это нестабильно, вынесите формулу из списка в отдельный абзац.

## 6. Код и математика

Machine labels:

```text
B20, B2n2, instrument_block_id
```

Физические объекты:

$$
B_2^0,\qquad B_2^{-2},\qquad \mathbf Q.
$$

## 7. Единицы

Предпочтительно:

```latex
18.25~\mathrm{meV}
3.5~\mathrm{K}
2.26~\text{\AA}^{-1}
```

## 8. Проверка перед commit

- [ ] Число `$$` чётное.
- [ ] Каждому `\begin{...}` соответствует `\end{...}`.
- [ ] `aligned`, `matrix`, `pmatrix` находятся внутри math blocks.
- [ ] Математика не окружена backticks по ошибке.
- [ ] Формулы не получили случайный четырёхпробельный отступ.
- [ ] Сложные формулы spot-checked в Obsidian preview.

Автоматическая проверка:

```powershell
python scripts/kb_validate.py
```
