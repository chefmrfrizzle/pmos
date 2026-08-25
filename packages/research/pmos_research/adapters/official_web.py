from __future__ import annotations
import hashlib, os, time
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser
import httpx
from bs4 import BeautifulSoup

class OfficialWebAdapter:
    def __init__(self):
        self.user_agent = os.getenv("PMOS_USER_AGENT", "PMOSResearch/0.1")
        self.delay = float(os.getenv("PMOS_REQUEST_DELAY_SECONDS", "1.5"))
        self.client = httpx.Client(headers={"User-Agent": self.user_agent}, follow_redirects=True, timeout=20)

    def allowed(self, url: str) -> bool:
        parsed = urlparse(url)
        robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
        rp = RobotFileParser()
        try:
            rp.set_url(robots_url)
            rp.read()
            return rp.can_fetch(self.user_agent, url)
        except Exception:
            return True

    def fetch(self, url: str) -> dict:
        if not self.allowed(url):
            return {"url": url, "status": "robots_blocked"}
        time.sleep(self.delay)
        r = self.client.get(url)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()
        title = soup.title.get_text(" ", strip=True) if soup.title else ""
        text = " ".join(soup.stripped_strings)
        normalized = " ".join(text.split())
        return {
            "url": str(r.url),
            "status": "ok",
            "title": title[:500],
            "text": normalized[:50000],
            "hash": hashlib.sha256(normalized.encode("utf-8")).hexdigest(),
            "html": r.text[:1000000],
        }
