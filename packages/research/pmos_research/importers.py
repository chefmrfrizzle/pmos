from __future__ import annotations
from pathlib import Path
import csv
from openpyxl import load_workbook
from .db import Contact, Entity
from .entity_resolution import canonicalize_name

def _val(x):
    return "" if x is None else str(x).strip()

def import_csv(session, path: Path) -> int:
    count=0
    with path.open("r", encoding="utf-8-sig", errors="ignore", newline="") as f:
        reader=csv.DictReader(f)
        for row in reader:
            lowered={str(k).strip().lower(): _val(v) for k,v in row.items() if k}
            name=lowered.get("name") or lowered.get("contact") or lowered.get("contact name")
            email=lowered.get("email")
            phone=lowered.get("phone") or lowered.get("phone number")
            if name:
                session.add(Contact(name=name,email=email or None,phone=phone or None,source=str(path)))
                count+=1
    return count

def import_xlsx(session, path: Path) -> int:
    wb=load_workbook(path, read_only=True, data_only=True)
    count=0
    for ws in wb.worksheets:
        rows=list(ws.iter_rows(values_only=True))
        if not rows:
            continue
        # Find a likely header row in the first 15 rows.
        header_i=None; mapping={}
        for i,row in enumerate(rows[:15]):
            labels=[_val(x).lower() for x in row]
            if any(x in labels for x in ("name","investor name","contact name")) or ("email" in labels and any("name" in x for x in labels)):
                header_i=i; mapping={label:j for j,label in enumerate(labels) if label}; break
        if header_i is None:
            continue
        for row in rows[header_i+1:]:
            def get(*keys):
                for k in keys:
                    if k in mapping and mapping[k] < len(row): return _val(row[mapping[k]])
                return ""
            contact=get("name","contact name","contact")
            firm=get("investor name","firm","organization","company")
            email=get("email")
            phone=get("phone","phone number")
            title=get("title","position / role","position")
            if firm:
                entity=Entity(name=firm,canonical_name=canonicalize_name(firm),universe="imported_private",verification_status="needs_verification")
                session.add(entity); session.flush()
                if contact:
                    session.add(Contact(entity_id=entity.id,name=contact,title=title or None,email=email or None,phone=phone or None,source=str(path)))
                count+=1
            elif contact:
                session.add(Contact(name=contact,title=title or None,email=email or None,phone=phone or None,source=str(path)))
                count+=1
    return count
