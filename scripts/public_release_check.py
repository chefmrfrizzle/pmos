#!/usr/bin/env python3
"""Fail-closed gate for every public commit and deployment."""
from pathlib import Path
import math,re,subprocess,sys
ROOT=Path(__file__).resolve().parents[1]
SKIP={".git","node_modules",".next",".venv",".pytest_cache","__pycache__",".vercel"}
BLOCKED={".xlsx",".xls",".parquet",".db",".sqlite",".sqlite3",".zip",".p12",".pfx",".pem",".key"}
PRIVATE=re.compile(r"(?i)(data/private|private[_-]?(seed|data|evidence)|investor[_ -]?(database|intelligence)|sotheby.?s database|warm introduction|outreach history)")
SECRET=re.compile(r"(?i)(api[_-]?key|secret[_-]?key|access[_-]?token|password|cookie|session)\s*[:=]\s*['\"]?([A-Za-z0-9_./+\-=]{8,})")
EMAIL=re.compile(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b")
def files():
    try:return set(subprocess.check_output(["git","ls-files","--cached","--others","--exclude-standard"],cwd=ROOT,text=True).splitlines())
    except Exception:return {str(p.relative_to(ROOT)) for p in ROOT.rglob("*") if p.is_file() and not SKIP.intersection(p.parts)}
def entropy(s):return -sum((s.count(c)/len(s))*math.log2(s.count(c)/len(s)) for c in set(s)) if s else 0
def main():
    problems=[]; candidates=files()
    for rel in sorted(candidates):
        p=ROOT/rel
        if not p.is_file() or SKIP.intersection(p.parts):continue
        low=rel.lower()
        if p.suffix.lower() in BLOCKED:problems.append(f"blocked artifact: {rel}")
        if PRIVATE.search(low) and not low.endswith(("public_private_boundary.md","public_release_check.py","security.md","readme.md")):problems.append(f"private/suspicious path: {rel}")
        if p.stat().st_size>5_000_000:problems.append(f"unexpected large file: {rel}")
        if p.suffix.lower() in {".py",".md",".json",".yaml",".yml",".txt",".ts",".tsx",".js",".css",".csv",".toml",".sh"}:
            text=p.read_text(errors="ignore")
            if rel!="scripts/public_release_check.py" and "BEGIN " in text and "PRIVATE KEY" in text:problems.append(f"private key: {rel}")
            if p.suffix.lower()==".csv" and EMAIL.search(text):problems.append(f"email-bearing CSV: {rel}")
            for m in SECRET.finditer(text):
                if not any(x in m.group(2).lower() for x in ("example","placeholder","changeme")) and entropy(m.group(2))>3:problems.append(f"possible secret: {rel}");break
    if problems:print("PUBLIC RELEASE CHECK FAILED\n"+"\n".join("- "+x for x in sorted(set(problems))));return 1
    print(f"Public release check passed ({len(candidates)} files inspected)");return 0
if __name__=="__main__":sys.exit(main())
