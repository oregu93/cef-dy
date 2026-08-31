#!/usr/bin/env python3
from pathlib import Path
import argparse, yaml, re, sys

ROOT = Path(__file__).resolve().parents[1]
META = ROOT / "00_Project" / "PROJECT_METADATA.yaml"
RESULTS = ROOT / "00_Project" / "RESULT_REGISTER.yaml"
HYP = ROOT / "00_Project" / "HYPOTHESIS_REGISTER.yaml"
STATE = ROOT / "00_Project" / "PROJECT_STATE.md"
CONTROL = ROOT / "00_Project" / "PROJECT_CONTROL.md"


def load_yaml(path):
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def result_map():
    return {x["id"]: x for x in load_yaml(RESULTS) or []}


def hyp_map():
    return {x["id"]: x for x in load_yaml(HYP) or []}


def state_block(meta, results):
    lines = ["# 60-second re-entry", ""]
    lines += [f"**Научный вопрос.** {meta['scientific_question']}", ""]
    cm = meta["current_model"]
    lines += [f"**Текущая модель.** `{cm['id']}` (`{cm['status']}`): {cm['summary']}", ""]
    lines += ["**Наиболее сильные проверенные результаты.**"]
    for rid in meta.get("strongest_result_ids", []):
        r = results.get(rid)
        if r:
            lines.append(f"- `{rid}` (`{r['status']}`): {r['statement']}")
    lines.append("")
    lines += ["**Основные неопределённости.**"]
    for x in meta.get("main_uncertainties", []): lines.append(f"- {x}")
    lines.append("")
    ms=meta['current_milestone']
    lines += [f"**Текущий этап.** `{ms['id']}` (`{ms['status']}`): {ms['title']}", ""]
    na=meta['immediate_next_step']
    lines += [f"**Следующий шаг.** `{na['id']}`: {na['text']}", ""]
    lines += ["**Не следует предполагать.**"]
    for x in meta.get('do_not_assume',[]): lines.append(f"- {x}")
    return "\n".join(lines).rstrip()+"\n"


def control_block(meta, hyps):
    c=meta['control']
    lines=["# 5-minute re-entry", "",
           f"**Сейчас.** {c['now']}", "",
           f"**Почему.** {c['why']}", "",
           f"**Следующий шаг.** {c['next']}", "",
           f"**Следующий Work job.** `{c['next_work_job']}`", "",
           "**Заблокировано.**"]
    for x in c.get('blocked',[]): lines.append(f"- {x}")
    lines += ["", "**Отложено.**"]
    for x in c.get('deferred',[]): lines.append(f"- {x}")
    lines += ["", f"**Последний научный источник.** {c.get('last_scientific_source','—')}", ""]
    cp=c.get('last_work_checkpoint')
    lines += [f"**Последний Work checkpoint.** `{cp}`" if cp else "**Последний Work checkpoint.** Пока не зарегистрирован в новой схеме.", ""]
    lines += ["**Активные гипотезы.**"]
    for hid in c.get('active_hypothesis_ids',[]):
        h=hyps.get(hid)
        if h: lines.append(f"- `{hid}` (`{h['status']}`): {h['statement']}")
    lines += ["", "**Ключевые риски.** " + ", ".join(f"`{x}`" for x in c.get('key_risk_ids',[])) + "."]
    return "\n".join(lines).rstrip()+"\n"


def replace_block(text, name, block):
    start=f"<!-- AUTO:{name}:START -->"
    end=f"<!-- AUTO:{name}:END -->"
    pat=re.compile(re.escape(start)+r".*?"+re.escape(end), re.S)
    replacement=start+"\n"+block+end
    if not pat.search(text):
        raise RuntimeError(f"markers {name} not found")
    return pat.sub(replacement, text, count=1)


def expected():
    meta=load_yaml(META)
    return (replace_block(STATE.read_text(encoding='utf-8'),'STATE_REENTRY',state_block(meta,result_map())),
            replace_block(CONTROL.read_text(encoding='utf-8'),'CONTROL_REENTRY',control_block(meta,hyp_map())))


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--check', action='store_true', help='не менять файлы; вернуть ошибку при рассинхронизации')
    args=ap.parse_args()
    new_state,new_control=expected()
    old_state=STATE.read_text(encoding='utf-8')
    old_control=CONTROL.read_text(encoding='utf-8')
    changed=[]
    if new_state!=old_state: changed.append(str(STATE.relative_to(ROOT)))
    if new_control!=old_control: changed.append(str(CONTROL.relative_to(ROOT)))
    if args.check:
        if changed:
            print('REENTRY_OUT_OF_SYNC')
            for p in changed: print(' -',p)
            return 2
        print('REENTRY_OK')
        return 0
    if new_state!=old_state: STATE.write_text(new_state,encoding='utf-8',newline='\n')
    if new_control!=old_control: CONTROL.write_text(new_control,encoding='utf-8',newline='\n')
    print('UPDATED' if changed else 'NO_CHANGES')
    for p in changed: print(' -',p)
    return 0

if __name__=='__main__':
    raise SystemExit(main())
