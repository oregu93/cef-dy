---
title: "Markdown and LaTeX Style"
type: protocol
status: active
version: "1.0"
updated: 2026-08-27
compatibility: [Obsidian, GitHub, CommonMark]
---

# Markdown and LaTeX Style

## Goal

Минимизировать случаи, когда физические обозначения в Obsidian отображаются как code/plain text, и сохранить разумную переносимость в GitHub/VS Code.

## 1. Inline math

Project standard:

```markdown
CEF parameter $B_l^m$ and energy $E_1=18.25~\mathrm{meV}$.
```

Не помещать математические обозначения в backticks, если они должны render as math.

## 2. Display math

Использовать отдельный block с пустой строкой до и после:

```markdown
$$
\hat H_{\mathrm{CEF}}
=
\sum_{l,m} B_l^m \hat O_l^m.
$$
```

## 3. Multi-line equations

LaTeX environments должны быть внутри math delimiters:

```markdown
$$
\begin{aligned}
E_1 &= 6.45~\mathrm{meV},\\
E_2 &= 18.20~\mathrm{meV},\\
E_3 &= 27.90~\mathrm{meV}.
\end{aligned}
$$
```

Не использовать standalone `\begin{aligned}` вне `$$...$$`.

## 4. Matrices

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

## 5. Markdown lists and display equations

Внутри list item display math может render inconsistently при лишних отступах. Preferred style:

```markdown
1. First statement.

   The relation is

   $$
   E=\hbar\omega.
   $$

2. Second statement.
```

Если конкретный renderer ломает этот формат, вынести equation block из списка в отдельный paragraph.

## 6. Avoid accidental code blocks

Четыре ведущих пробела могут превратить строку в Markdown code block. Не использовать indentation для обычного текста и формул, кроме осознанных list nesting cases.

## 7. Code vs math

Machine labels:

```text
B20, B2n2, instrument_block_id
```

Physical objects:

$$
B_2^0,\qquad B_2^{-2},\qquad \mathbf Q.
$$

## 8. Preferred units

Inside math:

```latex
18.25~\mathrm{meV}
3.5~\mathrm{K}
2.26~\text{\AA}^{-1}
```

## 9. Environment checks before commit

For any generated `.md` with mathematics:

- [ ] `$$` count is even.
- [ ] Every `\begin{...}` has matching `\end{...}`.
- [ ] `aligned`, `pmatrix`, etc. occur inside math blocks.
- [ ] No intended math is surrounded by backticks.
- [ ] Display equations are not accidentally indented as code.
- [ ] Obsidian preview was spot-checked for complex equations.

## 10. Compatibility note

GitHub math rendering may differ slightly from Obsidian MathJax. Critical equations should remain syntactically valid LaTeX even when not rendered by a given Markdown viewer.
