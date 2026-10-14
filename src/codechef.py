"""CodeChef platform scraper module.

Handles fetching user profile, solved problems from static HTML and recent submissions API.
Includes automatic exponential backoff retry for HTTP 429 (Too Many Requests).
"""

from dataclasses import dataclass, field
import logging
import random
import re
import time
from typing import Dict, List, Optional, Set
from bs4 import BeautifulSoup
import requests

logger = logging.getLogger(__name__)


@dataclass
class CodeChefUserResult:
    username: str
    exists: bool
    solved_problems: Set[str] = field(default_factory=set)
    profile_url: str = ""
    error_message: Optional[str] = None


class CodeChefScraper:
    BASE_URL = "https://www.codechef.com"

    def __init__(
        self,
        base_delay: float = 1.5,
        max_jitter: float = 1.0,
        session: Optional[requests.Session] = None,
        timeout: int = 15,
        user_agent: Optional[str] = None,
        max_retries: int = 3,
    ):
        self.base_delay = base_delay
        self.max_jitter = max_jitter
        self.timeout = timeout
        self.max_retries = max_retries
        self.session = session or requests.Session()
        self.user_agent = user_agent or (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        )
        self.session.headers.update({
            "User-Agent": self.user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9,ja;q=0.8",
            "Referer": "https://www.codechef.com/",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
        })
        self._user_cache: Dict[str, CodeChefUserResult] = {}

    def _sleep_with_jitter(self, multiplier: float = 1.0):
        """Sleep to respect rate limits and prevent bans."""
        duration = (self.base_delay * multiplier) + random.uniform(0.2, self.max_jitter)
        time.sleep(duration)

    def _request_with_retry(self, url: str) -> Optional[requests.Response]:
        """Execute GET request with exponential backoff on 429 Too Many Requests."""
        for attempt in range(self.max_retries + 1):
            self._sleep_with_jitter(multiplier=1.0 + (attempt * 1.5))
            try:
                resp = self.session.get(url, timeout=self.timeout, allow_redirects=True)
                if resp.status_code == 429:
                    backoff = (attempt + 1) * 4.0 + random.uniform(1.0, 3.0)
                    logger.warning(
                        f"[CodeChef] Rate limited (429) for {url}. "
                        f"Backing off for {backoff:.1f}s (attempt {attempt + 1}/{self.max_retries + 1})..."
                    )
                    time.sleep(backoff)
                    continue
                return resp
            except requests.RequestException as e:
                if attempt == self.max_retries:
                    raise e
                time.sleep(2.0)
        return None

    def fetch_user(self, username: str) -> CodeChefUserResult:
        """Fetch user profile and extract solved problems from CodeChef."""
        lower_user = username.strip().lower()
        if lower_user in self._user_cache:
            return self._user_cache[lower_user]

        url = f"{self.BASE_URL}/users/{username.strip()}"
        logger.debug(f"[CodeChef] Fetching user: {username} ({url})")

        try:
            resp = self._request_with_retry(url)
            if resp is None or resp.status_code == 404:
                result = CodeChefUserResult(
                    username=username,
                    exists=False,
                    profile_url=url,
                    error_message="User not found (404)",
                )
                self._user_cache[lower_user] = result
                return result

            if resp.status_code == 429:
                result = CodeChefUserResult(
                    username=username,
                    exists=False,
                    profile_url=url,
                    error_message="Rate limited (429)",
                )
                self._user_cache[lower_user] = result
                return result

            # Check if redirected to 404 or home page when user doesn't exist
            if "User not found" in resp.text or resp.url.rstrip("/").endswith("/404"):
                result = CodeChefUserResult(
                    username=username,
                    exists=False,
                    profile_url=url,
                    error_message="User not found",
                )
                self._user_cache[lower_user] = result
                return result

            resp.raise_for_status()

            # 1. Parse solved problems from user profile HTML
            soup = BeautifulSoup(resp.text, "html.parser")
            solved = self._parse_solved_problems(soup)

            # 2. Also check recent submission activity API for accurate Problem Codes
            recent_solved = self._fetch_recent_ac_submissions(username)
            solved.update(recent_solved)

            result = CodeChefUserResult(
                username=username,
                exists=True,
                solved_problems=solved,
                profile_url=resp.url,
            )
            self._user_cache[lower_user] = result
            return result

        except requests.RequestException as e:
            logger.warning(f"[CodeChef] Request error for {username}: {e}")
            result = CodeChefUserResult(
                username=username,
                exists=False,
                profile_url=url,
                error_message=str(e),
            )
            self._user_cache[lower_user] = result
            return result

    def _parse_solved_problems(self, soup: BeautifulSoup) -> Set[str]:
        """Extract problem codes from CodeChef user profile page."""
        solved: Set[str] = set()

        # Find problems-solved section (or sections containing "fully solved" or "problems solved")
        sections = soup.find_all("section", class_=re.compile(r"problems-solved", re.I))
        if not sections:
            for header in soup.find_all(["h3", "h4", "h5"]):
                if re.search(r"(fully solved|problems solved)", header.get_text(), re.I):
                    parent = header.find_parent("section") or header.find_parent("div")
                    if parent:
                        sections.append(parent)

        for sec in sections:
            for a in sec.find_all("a", href=True):
                href = a["href"]
                m = re.search(r"/(?:[A-Z0-9_]+/)?problems/([a-zA-Z0-9_\.\-]+)", href)
                if m:
                    solved.add(m.group(1).upper())
                m_status = re.search(r"/status/([a-zA-Z0-9_\.\-]+),", href)
                if m_status:
                    solved.add(m_status.group(1).upper())

            # Text/spans inside section
            for span in sec.find_all("span"):
                txt = span.get_text().strip()
                parts = [p.strip() for p in re.split(r"[,;]+", txt) if p.strip()]
                for part in parts:
                    if re.match(r"^[A-Z0-9_\.\-]{2,20}$", part, re.I):
                        solved.add(part.upper())
                    solved.add(part.upper())

        return solved

    def _fetch_recent_ac_submissions(self, username: str, max_pages: int = 2) -> Set[str]:
        """Query CodeChef's recent user submissions endpoint to extract AC problem codes."""
        solved: Set[str] = set()
        for page in range(max_pages):
            api_url = f"{self.BASE_URL}/recent/user?page={page}&user_handle={username.strip()}"
            try:
                resp = self._request_with_retry(api_url)
                if resp is None or resp.status_code != 200:
                    break
                data = resp.json()
                html_content = data.get("content", "")
                if not html_content:
                    break

                soup = BeautifulSoup(html_content, "html.parser")
                table = soup.find("table")
                if not table:
                    break

                rows = table.find_all("tr")
                for tr in rows[1:]:
                    cells = tr.find_all(["td", "th"])
                    if len(cells) >= 3:
                        prob_cell = cells[1]
                        result_cell = cells[2]
                        result_text = result_cell.get_text().strip()
                        is_ac = (
                            "(100)" in result_text
                            or "tick" in str(result_cell).lower()
                            or "correct" in str(result_cell).lower()
                            or "100 pts" in result_text.lower()
                        )
                        if is_ac:
                            a = prob_cell.find("a", href=True)
                            if a:
                                href = a["href"]
                                m = re.search(r"problems/([a-zA-Z0-9_\.\-]+)", href)
                                if m:
                                    solved.add(m.group(1).upper())
                            code = prob_cell.get_text().strip()
                            if code:
                                solved.add(code.upper())

                if data.get("max_page", 0) <= page + 1:
                    break
            except Exception as e:
                logger.debug(f"[CodeChef] recent submissions error for {username} on page {page}: {e}")
                break

        return solved
