from __future__ import annotations
import hashlib, ipaddress, os, socket, time
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser
import httpx
from bs4 import BeautifulSoup

class UnsafeResearchTarget(ValueError):pass
class ResponseTooLarge(ValueError):pass

class OfficialWebAdapter:
    def __init__(self,resolver=None):
        self.user_agent=os.getenv("PMOS_USER_AGENT","PMOSResearch/0.2 (+public-evidence; respectful crawler)")
        self.delay=max(.5,min(float(os.getenv("PMOS_REQUEST_DELAY_SECONDS","1.5")),30))
        self.max_bytes=max(65536,min(int(os.getenv("PMOS_MAX_RESPONSE_BYTES","2000000")),10000000))
        timeout=httpx.Timeout(20,connect=10,read=20,write=10,pool=5)
        self.client=httpx.Client(headers={"User-Agent":self.user_agent,"Accept":"text/html,application/xhtml+xml"},follow_redirects=False,timeout=timeout,trust_env=False)
        self.resolver=resolver or socket.getaddrinfo
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
        try:addresses={item[4][0].split("%")[0] for item in self.resolver(host,parsed.port or (443 if parsed.scheme=="https" else 80),type=socket.SOCK_STREAM)}
        except OSError as exc:raise UnsafeResearchTarget("target DNS resolution failed") from exc
        if not addresses:raise UnsafeResearchTarget("target has no resolved address")
        for address in addresses:
            ip=ipaddress.ip_address(address)
            if not ip.is_global:raise UnsafeResearchTarget("non-public target address is forbidden")
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
                length=response.headers.get("content-length")
                if length and length.isdigit() and int(length)>self.max_bytes:raise ResponseTooLarge("declared response is too large")
                body=bytearray()
                for chunk in response.iter_bytes():
                    body.extend(chunk)
                    if len(body)>self.max_bytes or response.num_bytes_downloaded>self.max_bytes:raise ResponseTooLarge("streamed response is too large")
                return httpx.Response(response.status_code,headers=response.headers,content=bytes(body),request=response.request)
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
        if "text/html" not in content_type and "application/xhtml+xml" not in content_type:
            return {"url":str(response.url),"status":"unsupported_content_type"}
        if len(response.content)>self.max_bytes:return {"url":str(response.url),"status":"response_too_large"}
        soup=BeautifulSoup(response.text,"html.parser")
        for tag in soup(["script","style","noscript"]):tag.decompose()
        title=soup.title.get_text(" ",strip=True) if soup.title else ""
        normalized=" ".join(" ".join(soup.stripped_strings).split())
        return {"url":str(response.url),"status":"ok","title":title[:500],"text":normalized[:50000],"hash":hashlib.sha256(normalized.encode()).hexdigest(),"html":response.text[:1000000]}
