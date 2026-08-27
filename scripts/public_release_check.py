#!/usr/bin/env python3
"""Fail-closed gate for every public commit and deployment."""
from pathlib import Path
import argparse,math,re,subprocess,sys
ROOT=Path(__file__).resolve().parents[1]
SKIP={".git","node_modules",".next",".venv",".pytest_cache","__pycache__",".vercel"}
BLOCKED={".xlsx",".xls",".parquet",".db",".sqlite",".sqlite3",".zip",".p12",".pfx",".pem",".key"}
PRIVATE=re.compile(r"(?i)(data/private|private[_-]?(seed|data|evidence)|investor[_ -]?(database|intelligence)|sotheby.?s database|warm introduction|outreach history)")
SECRET=re.compile(r"(?i)(api[_-]?key|secret[_-]?key|access[_-]?token|password|cookie|session)\s*[:=]\s*['\"]?([A-Za-z0-9_./+\-=]{8,})")
EMAIL=re.compile(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b")
PUBLIC_ENV=re.compile(r"(?i)NEXT_PUBLIC_[A-Z0-9_]*(PRIVATE|DATABASE|DB_URL|TOKEN|SECRET|COOKIE|SESSION)")
BUNDLE_PRIVATE=re.compile(r"(?i)(private-import://|data/private|pmos-v[0-9].*\.db|PMOS_DB_URL|warm introduction path|outreach history)")
def files(root=ROOT):
    try:return set(subprocess.check_output(["git","ls-files","--cached","--others","--exclude-standard"],cwd=root,text=True).splitlines())
    except Exception:return {str(p.relative_to(root)) for p in root.rglob("*") if p.is_file() and not SKIP.intersection(p.parts)}
def entropy(s):return -sum((s.count(c)/len(s))*math.log2(s.count(c)/len(s)) for c in set(s)) if s else 0
def history_problems(root=ROOT):
    """Inspect reachable historical blobs without printing their contents."""
    problems=[]
    try:objects=subprocess.check_output(["git","rev-list","--objects","--all"],cwd=root,text=True).splitlines()
    except Exception:return ["unable to inspect Git history"]
    seen=set()
    for entry in objects:
        bits=entry.split(" ",1)
        if len(bits)!=2:continue
        oid,rel=bits
        if oid in seen:continue
        seen.add(oid);suffix=Path(rel).suffix.casefold()
        if suffix in BLOCKED:problems.append(f"historical blocked artifact: {rel}");continue
        try:
            kind=subprocess.check_output(["git","cat-file","-t",oid],cwd=root,text=True,stderr=subprocess.DEVNULL).strip()
            if kind!="blob":continue
            size=int(subprocess.check_output(["git","cat-file","-s",oid],cwd=root,text=True,stderr=subprocess.DEVNULL).strip())
            if size>5_000_000:problems.append(f"historical oversized blob: {rel}");continue
            blob=subprocess.check_output(["git","cat-file","blob",oid],cwd=root,stderr=subprocess.DEVNULL)
        except Exception:problems.append(f"unable to inspect historical blob: {rel}");continue
        if b"\x00" in blob[:4096]:continue
        text=blob.decode("utf-8",errors="ignore")
        if rel!="scripts/public_release_check.py":
            for match in SECRET.finditer(text):
                if not any(x in match.group(2).casefold() for x in ("example","placeholder","changeme")) and entropy(match.group(2))>3:
                    problems.append(f"historical possible secret: {rel}");break
        if suffix==".csv" and EMAIL.search(text):problems.append(f"historical email-bearing CSV: {rel}")
    return problems
def bundle_problems(root=ROOT):
    problems=[];static=root/"apps"/"web"/".next"/"static"
    if not static.exists():return problems
    for path in static.rglob("*"):
        if not path.is_file():continue
        rel=str(path.relative_to(root))
        if path.suffix==".map":problems.append(f"browser source map present: {rel}");continue
        if path.suffix not in {".js",".css",".json"}:continue
        text=path.read_text(errors="ignore")
        if BUNDLE_PRIVATE.search(text) or PUBLIC_ENV.search(text) or EMAIL.search(text):problems.append(f"suspicious client bundle content: {rel}")
    return problems
def scan(root=ROOT):
    root=root.resolve();problems=[];candidates=files(root)
    for rel in sorted(candidates):
        p=root/rel
        if not p.is_file() or SKIP.intersection(p.parts):continue
        low=rel.lower()
        if p.suffix.lower() in BLOCKED:problems.append(f"blocked artifact: {rel}")
        if PRIVATE.search(low) and not low.endswith(("public_private_boundary.md","public_release_check.py","security.md","readme.md")):problems.append(f"private/suspicious path: {rel}")
        if p.stat().st_size>5_000_000:problems.append(f"unexpected large file: {rel}")
        if p.suffix.lower() in {".py",".md",".json",".yaml",".yml",".txt",".ts",".tsx",".js",".css",".csv",".toml",".sh"}:
            text=p.read_text(errors="ignore")
            if PUBLIC_ENV.search(text):problems.append(f"unsafe public environment variable: {rel}")
            if rel!="scripts/public_release_check.py" and "BEGIN " in text and "PRIVATE KEY" in text:problems.append(f"private key: {rel}")
            if p.suffix.lower()==".csv" and EMAIL.search(text):problems.append(f"email-bearing CSV: {rel}")
            for m in SECRET.finditer(text):
                if not any(x in m.group(2).lower() for x in ("example","placeholder","changeme")) and entropy(m.group(2))>3:problems.append(f"possible secret: {rel}");break
    problems.extend(history_problems(root));problems.extend(bundle_problems(root))
    return sorted(set(problems)),len(candidates)
def main(root=ROOT):
    problems,count=scan(root)
    if problems:print("PUBLIC RELEASE CHECK FAILED\n"+"\n".join("- "+x for x in problems));return 1
    print(f"Public release check passed ({count} files inspected)");return 0
if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument("--root",type=Path,default=ROOT,help=argparse.SUPPRESS);args=parser.parse_args()
    if not args.root.is_dir() or args.root.is_symlink():raise SystemExit("release-check root is missing or unsafe")
    sys.exit(main(args.root))
