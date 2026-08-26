from __future__ import annotations
import hashlib, ipaddress, json, os, socket, subprocess, sys, time
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser
import httpcore,httpx
from bs4 import BeautifulSoup
from pmos_research.runtime_isolation import ResourceLimits,apply_resource_limits,sanitized_environment

class UnsafeResearchTarget(ValueError):pass
class ResponseTooLarge(ValueError):pass

def _public_addresses(resolver,host:str,port:int)->list[str]:
    try:addresses={item[4][0].split("%")[0] for item in resolver(host,port,type=socket.SOCK_STREAM)}
    except OSError as exc:raise UnsafeResearchTarget("target DNS resolution failed") from exc
    if not addresses:raise UnsafeResearchTarget("target has no resolved address")
    parsed=[]
    for address in addresses:
        ip=ipaddress.ip_address(address)
        if not ip.is_global:raise UnsafeResearchTarget("non-public target address is forbidden")
        parsed.append(ip)
    return [str(x) for x in sorted(parsed,key=lambda value:(value.version,int(value)))]

class PinnedNetworkBackend(httpcore.NetworkBackend):
    """Resolve, validate, and connect to the same public IP to prevent DNS rebinding."""
    def __init__(self,resolver,backend=None):self.resolver=resolver;self.backend=backend or httpcore.SyncBackend()
    def connect_tcp(self,host,port,timeout=None,local_address=None,socket_options=None):
        normalized=host.decode("ascii") if isinstance(host,bytes) else str(host);pinned=_public_addresses(self.resolver,normalized,int(port))[0]
        return self.backend.connect_tcp(pinned,port,timeout=timeout,local_address=local_address,socket_options=socket_options)
    def connect_unix_socket(self,*args,**kwargs):raise UnsafeResearchTarget("unix sockets are forbidden")
    def sleep(self,seconds):return self.backend.sleep(seconds)

class PinnedHTTPTransport(httpx.HTTPTransport):
    def __init__(self,resolver,**kwargs):
        super().__init__(**kwargs)
        pool=getattr(self,"_pool",None)
        if pool is None or not hasattr(pool,"_network_backend"):raise RuntimeError("HTTP transport cannot install fail-closed DNS pinning")
        pool._network_backend=PinnedNetworkBackend(resolver)

class OfficialWebAdapter:
    def __init__(self,resolver=None):
        self.resolver=resolver or socket.getaddrinfo
        self.user_agent=os.getenv("PMOS_USER_AGENT","PMOSResearch/0.2 (+public-evidence; respectful crawler)")
        self.delay=max(.5,min(float(os.getenv("PMOS_REQUEST_DELAY_SECONDS","1.5")),30))
        self.max_bytes=max(65536,min(int(os.getenv("PMOS_MAX_RESPONSE_BYTES","2000000")),10000000))
        self.max_pdf_bytes=max(65536,min(int(os.getenv("PMOS_MAX_PDF_BYTES","10000000")),20000000))
        timeout=httpx.Timeout(20,connect=10,read=20,write=10,pool=5)
        transport=PinnedHTTPTransport(self.resolver,trust_env=False,retries=0)
        self.client=httpx.Client(headers={"User-Agent":self.user_agent,"Accept":"text/html,application/xhtml+xml,application/pdf"},follow_redirects=False,timeout=timeout,trust_env=False,transport=transport)
        self._robots={};self._last_request={}

    def _validate_url(self,url:str)->str:
        parsed=urlparse(url)
        if parsed.scheme not in {"http","https"} or not parsed.hostname or parsed.username or parsed.password:
            raise UnsafeResearchTarget("only credential-free public HTTP(S) URLs are allowed")
        expected_port=443 if parsed.scheme=="https" else 80
        if parsed.port is not None and parsed.port!=expected_port:raise UnsafeResearchTarget("alternate network ports are forbidden")
        host=parsed.hostname.rstrip(".").casefold()
        if host in {"localhost","localhost.localdomain"} or host.endswith((".local",".internal",".home",".lan")):
            raise UnsafeResearchTarget("local network targets are forbidden")
        _public_addresses(self.resolver,host,parsed.port or (443 if parsed.scheme=="https" else 80))
        return url

    def _wait(self,host:str):
        elapsed=time.monotonic()-self._last_request.get(host,0);remaining=self.delay-elapsed
        if remaining>0:time.sleep(remaining)
        self._last_request[host]=time.monotonic()

    def _get(self,url:str,max_redirects:int=4)->httpx.Response:
        current=self._validate_url(url)
        for _ in range(max_redirects+1):
            host=urlparse(current).hostname or "";self._wait(host)
            with self.client.stream("GET",current) as response:
                if response.status_code in {301,302,303,307,308}:
                    location=response.headers.get("location")
                    if not location:raise httpx.HTTPStatusError("redirect missing location",request=response.request,response=response)
                    current=self._validate_url(urljoin(current,location));continue
                response.raise_for_status()
                content_type=response.headers.get("content-type","").casefold();limit=self.max_pdf_bytes if "application/pdf" in content_type else self.max_bytes
                length=response.headers.get("content-length")
                if length and length.isdigit() and int(length)>limit:raise ResponseTooLarge("declared response is too large")
                body=bytearray()
                for chunk in response.iter_bytes():
                    body.extend(chunk)
                    if len(body)>limit or response.num_bytes_downloaded>limit:raise ResponseTooLarge("streamed response is too large")
                # iter_bytes() returns decoded bytes. Do not carry wire-encoding or
                # length headers into the reconstructed in-memory response.
                headers={k:v for k,v in response.headers.items() if k.casefold() not in {"content-encoding","content-length","transfer-encoding"}}
                return httpx.Response(response.status_code,headers=headers,content=bytes(body),request=response.request)
        raise httpx.TooManyRedirects("too many redirects")

    def allowed(self,url:str)->bool:
        target=self._validate_url(url);parsed=urlparse(target);origin=f"{parsed.scheme}://{parsed.netloc}"
        if origin in self._robots:return self._robots[origin].can_fetch(self.user_agent,target)
        robots_url=f"{origin}/robots.txt";parser=RobotFileParser();parser.set_url(robots_url)
        try:
            response=self._get(robots_url)
            if len(response.content)>self.max_bytes:raise ValueError("robots response too large")
            parser.parse(response.text.splitlines());self._robots[origin]=parser
            return parser.can_fetch(self.user_agent,target)
        except Exception:
            return False

    def fetch(self,url:str)->dict:
        if not self.allowed(url):return {"url":url,"status":"robots_blocked_or_unavailable"}
        response=self._get(url)
        content_type=response.headers.get("content-type","").lower()
        if "application/pdf" in content_type:
            if not response.content.startswith(b"%PDF-"):return {"url":str(response.url),"status":"invalid_pdf_signature"}
            try:pdf=self._extract_pdf(response.content)
            except (subprocess.SubprocessError,ValueError,json.JSONDecodeError):return {"url":str(response.url),"status":"pdf_extraction_failed"}
            if not pdf.get("pages") or not any(x.get("text","").strip() for x in pdf["pages"]):return {"url":str(response.url),"status":"pdf_no_extractable_text"}
            text=" ".join(x["text"] for x in pdf["pages"] if x.get("text"))[:50000]
            return {"url":str(response.url),"status":"ok","title":pdf.get("title","")[:500],"text":text,"pages":pdf["pages"],"hash":hashlib.sha256(response.content).hexdigest(),"media_type":"application/pdf"}
        if "text/html" not in content_type and "application/xhtml+xml" not in content_type:
            return {"url":str(response.url),"status":"unsupported_content_type"}
        if len(response.content)>self.max_bytes:return {"url":str(response.url),"status":"response_too_large"}
        soup=BeautifulSoup(response.text,"html.parser")
        for tag in soup(["script","style","noscript"]):tag.decompose()
        title=soup.title.get_text(" ",strip=True) if soup.title else ""
        normalized=" ".join(" ".join(soup.stripped_strings).split())
        return {"url":str(response.url),"status":"ok","title":title[:500],"text":normalized[:50000],"hash":hashlib.sha256(normalized.encode()).hexdigest(),"html":response.text[:1000000]}

    def _extract_pdf(self,content:bytes)->dict:
        command=[sys.executable,"-m","pmos_research.pdf_worker"]
        preexec=lambda:apply_resource_limits(ResourceLimits(cpu_seconds=20,file_bytes=10_000_000,open_files=64,processes=512))
        result=subprocess.run(command,input=content,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,env=sanitized_environment(),timeout=25,check=False,preexec_fn=preexec)
        if result.returncode or len(result.stdout)>1_000_000:raise ValueError("PDF extractor failed or exceeded output limit")
        return json.loads(result.stdout)
