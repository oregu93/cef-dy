#!/usr/bin/env python3
from pathlib import Path
import argparse
import re
import yaml

ROOT = Path(__file__).resolve().parents[1]

META = ROOT / "00_Project" / "PROJECT_METADATA.yaml"
HYP = ROOT / "00_Project" / "HYPOTHESIS_REGISTER.yaml"

STATE = ROOT / "00_Project" / "PROJECT_STATE.md"
CONTROL = ROOT / "00_Project" / "PROJECT_CONTROL.md"
README = ROOT / "README.md"


def load_yaml(path):
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def hyp_map():
    data = load_yaml(HYP) or []
    if not isinstance(data, list):
        raise RuntimeError(f"{HYP.relative_to(ROOT)} must contain a YAML list")
    return {
        x["id"]: x
        for x in data
        if isinstance(x, dict) and "id" in x
    }


def wrapped(text):
    if text is None:
        return "—"
    return " ".join(str(text).split())


def state_block(meta):
    lines = ["# 60-second re-entry", ""]

    lines += [
        f"**Научная задача.** {wrapped(meta['scientific_question'])}",
        "",
        f"**Что непосредственно поддерживают экспериментальные данные.** "
        f"{wrapped(meta['experimental_evidence_summary'])}",
        "",
        f"**Что является физической интерпретацией.** "
        f"{wrapped(meta['interpretation_summary'])}",
        "",
        f"**Что показывает текущая модельная картина.** "
        f"{wrapped(meta['model_status_summary'])}",
        "",
    ]

    lines += ["**Основные неопределённости.**"]
    for item in meta.get("main_uncertainties", []):
        lines.append(f"- {wrapped(item)}")
    lines.append("")

    milestone = meta["current_milestone"]
    lines += [
        f"**Текущий этап.** `{milestone['id']}` (`{milestone['status']}`): "
        f"{wrapped(milestone['title'])}",
        "",
    ]

    next_step = meta["immediate_next_step"]
    lines += [
        f"**Следующий шаг.** `{next_step['id']}`: "
        f"{wrapped(next_step['text'])}",
        "",
    ]

    lines += ["**Не следует предполагать.**"]
    for item in meta.get("do_not_assume", []):
        lines.append(f"- {wrapped(item)}")

    return "\n".join(lines).rstrip() + "\n"


def control_block(meta, hyps):
    control = meta["control"]

    lines = [
        "# 5-minute re-entry",
        "",
        f"**Сейчас.** {wrapped(control['now'])}",
        "",
        f"**Почему.** {wrapped(control['why'])}",
        "",
        f"**Следующий шаг.** {wrapped(control['next'])}",
        "",
    ]

    next_work = control.get("next_work_job")
    if next_work:
        lines += [
            f"**Следующий Work job.** `{wrapped(next_work)}`",
            "",
        ]
    else:
        lines += [
            "**Следующий Work job.** Не назначен. Production Work заблокирован "
            "до завершения текущего scientific review cycle.",
            "",
        ]

    lines += ["**Заблокировано.**"]
    for item in control.get("blocked", []):
        lines.append(f"- {wrapped(item)}")

    lines += ["", "**Отложено.**"]
    for item in control.get("deferred", []):
        lines.append(f"- {wrapped(item)}")

    lines += [
        "",
        f"**Последний научный источник.** "
        f"{wrapped(control.get('last_scientific_source', '—'))}",
        "",
    ]

    checkpoint = control.get("last_work_checkpoint")
    if checkpoint:
        lines += [
            f"**Последний Work checkpoint.** `{wrapped(checkpoint)}`",
            "",
        ]
    else:
        lines += [
            "**Последний Work checkpoint.** Для текущего этапа "
            "вычислительный checkpoint ещё не зафиксирован.",
            "",
        ]

    lines += ["**Активные гипотезы.**"]
    active_ids = control.get("active_hypothesis_ids", [])

    if not active_ids:
        lines.append("- Нет.")
    else:
        for hid in active_ids:
            hyp = hyps.get(hid)
            if hyp:
                lines.append(
                    f"- `{hid}` (`{hyp.get('status', 'unknown')}`): "
                    f"{wrapped(hyp.get('statement', ''))}"
                )
            else:
                lines.append(
                    f"- `{hid}`: запись не найдена в HYPOTHESIS_REGISTER."
                )

    risks = control.get("key_risk_ids", [])

    lines += [
        "",
        "**Ключевые риски.** "
        + (
            ", ".join(f"`{x}`" for x in risks) + "."
            if risks
            else "Не указаны."
        ),
    ]

    return "\n".join(lines).rstrip() + "\n"


def readme_status_block(meta):
    milestone = meta["current_milestone"]
    next_step = meta["immediate_next_step"]

    lines = [
        "## Текущий статус проекта",
        "",
        f"**Stage:** `{milestone['id']}` — "
        f"{wrapped(milestone['title'])} "
        f"(`{milestone['status']}`).",
        "",
        f"**Current focus:** {wrapped(meta['control']['now'])}",
        "",
        f"**Next:** {wrapped(next_step['text'])}",
        "",
        f"**Metadata updated:** `{meta.get('updated', 'unknown')}`.",
    ]

    return "\n".join(lines).rstrip() + "\n"


def markers(name):
    return (
        f"<!-- AUTO:{name}:START -->",
        f"<!-- AUTO:{name}:END -->",
    )


def has_block(text, name):
    start, end = markers(name)
    return start in text and end in text


def replace_block(text, name, block):
    start, end = markers(name)

    pattern = re.compile(
        re.escape(start) + r".*?" + re.escape(end),
        re.S,
    )

    replacement = start + "\n" + block + end

    if not pattern.search(text):
        raise RuntimeError(f"markers {name} not found")

    return pattern.sub(replacement, text, count=1)


def expected_files():
    meta = load_yaml(META)

    if not isinstance(meta, dict):
        raise RuntimeError(
            f"{META.relative_to(ROOT)} must contain a YAML mapping"
        )

    hyps = hyp_map()

    expected = {
        STATE: replace_block(
            STATE.read_text(encoding="utf-8"),
            "STATE_REENTRY",
            state_block(meta),
        ),
        CONTROL: replace_block(
            CONTROL.read_text(encoding="utf-8"),
            "CONTROL_REENTRY",
            control_block(meta, hyps),
        ),
    }

    # README status generation becomes active automatically once README
    # contains AUTO:README_STATUS markers. Until then README is untouched.
    if README.exists():
        readme_text = README.read_text(encoding="utf-8")

        if has_block(readme_text, "README_STATUS"):
            expected[README] = replace_block(
                readme_text,
                "README_STATUS",
                readme_status_block(meta),
            )

    return expected


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--check",
        action="store_true",
        help="не менять файлы; вернуть ошибку при рассинхронизации",
    )

    args = parser.parse_args()

    expected = expected_files()
    changed = []

    for path, new_text in expected.items():
        old_text = path.read_text(encoding="utf-8")

        if new_text != old_text:
            changed.append(path)

    if args.check:
        if changed:
            print("REENTRY_OUT_OF_SYNC")

            for path in changed:
                print(" -", path.relative_to(ROOT))

            return 2

        print("REENTRY_OK")
        return 0

    for path in changed:
        path.write_text(
            expected[path],
            encoding="utf-8",
            newline="\n",
        )

    print("UPDATED" if changed else "NO_CHANGES")

    for path in changed:
        print(" -", path.relative_to(ROOT))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())