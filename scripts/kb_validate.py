#!/usr/bin/env python3
from pathlib import Path
import argparse, yaml, re, json, sys, subprocess

ROOT=Path(__file__).resolve().parents[1]
REPORT=ROOT/'VALIDATION_REPORT.json'
RESULT_STATUSES={'candidate','working','reviewed','validated','rejected','superseded'}
HYP_STATUSES={'candidate','working','disfavored','rejected','superseded'}
DECISION_STATUSES={'active','superseded','rejected'}
REPRO_KINDS={'checkpoint','artifact','dataset','code_run'}


def load_yaml(path,issues):
    try:
        with path.open('r',encoding='utf-8') as f: return yaml.safe_load(f)
    except Exception as e:
        issues.append({'level':'error','file':str(path.relative_to(ROOT)),'message':f'YAML parse error: {e}'})
        return None


def strip_fences(text):
    text=re.sub(r'```.*?```','',text,flags=re.S)
    text=re.sub(r'`[^`\n]*`','',text)
    return text


def latex_checks(path,text,issues):
    t=strip_fences(text)
    if t.count('$$')%2:
        issues.append({'level':'error','file':str(path.relative_to(ROOT)),'message':'odd number of $$ delimiters'})
    begins=re.findall(r'\\begin\{([^}]+)\}',t)
    ends=re.findall(r'\\end\{([^}]+)\}',t)
    if sorted(begins)!=sorted(ends):
        issues.append({'level':'error','file':str(path.relative_to(ROOT)),'message':f'LaTeX environment mismatch: begin={begins}, end={ends}'})
    # check math-only envs inside display blocks
    display_spans=[m.span() for m in re.finditer(r'\$\$.*?\$\$',t,flags=re.S)]
    for env in ('aligned','pmatrix','matrix','bmatrix','cases'):
        for m in re.finditer(r'\\begin\{'+env+r'\}',t):
            if not any(a<=m.start()<b for a,b in display_spans):
                issues.append({'level':'error','file':str(path.relative_to(ROOT)),'message':f'{env} environment outside $$ math block'})
    # accidental 4-space code with math marker
    for i,line in enumerate(t.splitlines(),1):
        if re.match(r'^ {4,}\$\$',line):
            issues.append({'level':'warning','file':str(path.relative_to(ROOT)),'message':f'indented display math at line {i}'})


def register_checks(issues):
    paths={
        'results':ROOT/'00_Project/RESULT_REGISTER.yaml',
        'hypotheses':ROOT/'00_Project/HYPOTHESIS_REGISTER.yaml',
        'decisions':ROOT/'00_Project/DECISION_REGISTER.yaml'}
    regs={k:load_yaml(p,issues) or [] for k,p in paths.items()}
    all_ids=[]
    for k,items in regs.items():
        for x in items:
            if 'id' not in x:
                issues.append({'level':'error','file':str(paths[k].relative_to(ROOT)),'message':'record without id'}); continue
            all_ids.append((x['id'],k))
    seen={}
    for id_,k in all_ids:
        if id_ in seen: issues.append({'level':'error','file':'registers','message':f'duplicate ID {id_} in {seen[id_]} and {k}'})
        seen[id_]=k
    # result status/evidence
    for r in regs['results']:
        st=r.get('status')
        if st not in RESULT_STATUSES: issues.append({'level':'error','file':str(paths['results'].relative_to(ROOT)),'message':f"{r.get('id')}: invalid result status {st}"})
        if st in {'reviewed','validated'}:
            if not r.get('evidence'): issues.append({'level':'error','file':str(paths['results'].relative_to(ROOT)),'message':f"{r.get('id')}: {st} requires evidence"})
            if not r.get('review_date'): issues.append({'level':'error','file':str(paths['results'].relative_to(ROOT)),'message':f"{r.get('id')}: {st} requires review_date"})
        if st=='validated':
            if not r.get('validation_criteria'): issues.append({'level':'error','file':str(paths['results'].relative_to(ROOT)),'message':f"{r.get('id')}: validated requires validation_criteria"})
            kinds={e.get('kind') for e in r.get('evidence',[]) if isinstance(e,dict)}
            if not (kinds & REPRO_KINDS): issues.append({'level':'error','file':str(paths['results'].relative_to(ROOT)),'message':f"{r.get('id')}: validated requires reproducible evidence kind {sorted(REPRO_KINDS)}"})
    for h in regs['hypotheses']:
        if h.get('status') not in HYP_STATUSES: issues.append({'level':'error','file':str(paths['hypotheses'].relative_to(ROOT)),'message':f"{h.get('id')}: invalid hypothesis status {h.get('status')}"})
    for d in regs['decisions']:
        if d.get('status') not in DECISION_STATUSES: issues.append({'level':'error','file':str(paths['decisions'].relative_to(ROOT)),'message':f"{d.get('id')}: invalid decision status {d.get('status')}"})
    # cross refs from hypotheses
    result_ids={r.get('id') for r in regs['results']}
    for h in regs['hypotheses']:
        for key in ('supporting_results','conflicting_results'):
            for rid in h.get(key,[]) or []:
                if rid not in result_ids: issues.append({'level':'error','file':str(paths['hypotheses'].relative_to(ROOT)),'message':f"{h.get('id')}: unknown result ID {rid}"})


def markdown_links(path,text,issues):
    # normal relative markdown links only; skip external URLs and anchors
    for target in re.findall(r'\[[^\]]+\]\(([^)]+)\)',text):
        if re.match(r'^[a-z]+://',target) or target.startswith('#') or target.startswith('mailto:'): continue
        tgt=target.split('#',1)[0]
        if not tgt: continue
        p=(path.parent/tgt).resolve()
        try: p.relative_to(ROOT.resolve())
        except Exception: continue
        if not p.exists(): issues.append({'level':'warning','file':str(path.relative_to(ROOT)),'message':f'broken relative link: {target}'})


def path_leak_checks(path,text,issues):
    if 'Archive/legacy/' in str(path.relative_to(ROOT)): return
    # Ignore example placeholder paths under configs/local_paths.example.yaml
    if path.name=='local_paths.example.yaml': return
    if re.search(r'(?i)\b[A-Z]:\\Users\\[^\\\s]+\\',text):
        issues.append({'level':'warning','file':str(path.relative_to(ROOT)),'message':'possible absolute Windows user path'})


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--strict',action='store_true')
    args=ap.parse_args()
    issues=[]
    # YAML
    for p in ROOT.rglob('*.yaml'):
        if 'Archive/legacy' in str(p): continue
        load_yaml(p,issues)
        path_leak_checks(p,p.read_text(encoding='utf-8'),issues)
    register_checks(issues)
    # MD checks
    for p in ROOT.rglob('*.md'):
        if 'Archive/legacy' in str(p): continue
        text=p.read_text(encoding='utf-8')
        latex_checks(p,text,issues)
        markdown_links(p,text,issues)
        path_leak_checks(p,text,issues)
    # Re-entry consistency by invoking refresh --check
    proc=subprocess.run([sys.executable,str(ROOT/'scripts/kb_refresh.py'),'--check'],capture_output=True,text=True)
    if proc.returncode!=0:
        issues.append({'level':'error','file':'reentry','message':'generated re-entry blocks are out of sync; run scripts/kb_refresh.py'})
    # File sizes > 10MB tracked-ish area warning
    for p in ROOT.rglob('*'):
        if p.is_file() and 'Archive/legacy' not in str(p):
            if p.stat().st_size>10*1024*1024:
                issues.append({'level':'warning','file':str(p.relative_to(ROOT)),'message':'file larger than 10 MiB; check Git policy'})
    report={'root':str(ROOT),'schema_version':'2.1','errors':sum(i['level']=='error' for i in issues),'warnings':sum(i['level']=='warning' for i in issues),'issues':issues}
    REPORT.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8',newline='\n')
    print(json.dumps({'errors':report['errors'],'warnings':report['warnings']},ensure_ascii=False))
    for i in issues: print(f"{i['level'].upper()}: {i['file']}: {i['message']}")
    if report['errors'] or (args.strict and report['warnings']): return 2
    return 0

if __name__=='__main__':
    raise SystemExit(main())
