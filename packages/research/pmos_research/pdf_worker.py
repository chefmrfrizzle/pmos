from __future__ import annotations

import hashlib,io,json,os,sys

from pypdf import PdfReader

def _limit(name:str,default:int,low:int,high:int)->int:
    try:value=int(os.getenv(name,str(default)))
    except ValueError:value=default
    return max(low,min(value,high))

def extract(content:bytes)->dict:
    max_pages=_limit("PMOS_PDF_MAX_PAGES",200,1,500);max_page_chars=_limit("PMOS_PDF_MAX_PAGE_CHARS",5000,500,10000);max_total_chars=_limit("PMOS_PDF_MAX_TEXT_CHARS",50000,5000,100000)
    reader=PdfReader(io.BytesIO(content),strict=True)
    if reader.is_encrypted:raise ValueError("encrypted PDFs are unsupported")
    if len(reader.pages)>max_pages:raise ValueError("PDF page limit exceeded")
    pages=[];total=0
    for number,page in enumerate(reader.pages,1):
        text=" ".join((page.extract_text() or "").split())[:max_page_chars];remaining=max_total_chars-total
        if remaining<=0:break
        text=text[:remaining];total+=len(text)
        pages.append({"page":number,"text":text,"text_hash":hashlib.sha256(text.encode()).hexdigest()})
    metadata=reader.metadata or {};title=str(metadata.get("/Title","") or "")
    return {"title":title,"page_count":len(reader.pages),"pages":pages}

def main()->int:
    try:result=extract(sys.stdin.buffer.read())
    except Exception as exc:
        sys.stderr.write(type(exc).__name__);return 2
    sys.stdout.write(json.dumps(result,separators=(",",":")));return 0

if __name__=="__main__":raise SystemExit(main())
