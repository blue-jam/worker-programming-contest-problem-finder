"""CodeChef platform scraper module.

Handles fetching user profile, solved problems from static HTML and recent submissions API.
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
        base_delay: float = 1.0,
        max_jitter: float = 0.8,
        session: Optional[requests.Session] = None,
        timeout: int = 15,
        user_agent: Optional[str] = None,
        use_headless: bool = False,
    ):
        self.base_delay = base_delay
        self.max_jitter = max_jitter
        self.timeout = timeout
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
        })
        self.use_headless = use_headless
        self._user_cache: Dict[str, CodeChefUserResult] = {}

    def _sleep_with_jitter(self):
        """Sleep to respect rate limits and prevent bans."""
        duration = self.base_delay + random.uniform(0.1, self.max_jitter)
        time.sleep(duration)

    def fetch_user(self, username: str) -> CodeChefUserResult:
        """Fetch user profile and extract solved problems from CodeChef."""
        lower_user = username.strip().lower()
        if lower_user in self._user_cache:
            return self._user_cache[lower_user]

        url = f"{self.BASE_URL}/users/{username.strip()}"
        logger.debug(f"[CodeChef] Fetching user: {username} ({url})")

        self._sleep_with_jitter()
        try:
            resp = self.session.get(url, timeout=self.timeout, allow_redirects=True)
            if resp.status_code == 404:
                result = CodeChefUserResult(
                    username=username,
                    exists=False,
                    profile_url=url,
                    error_message="User not found (404)",
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
            # This fetches verified AC problem codes (e.g., TEST, FLOW001, MAXHAMDIST)
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
            # Fallback to any container with relevant header
            for header in soup.find_all(["h3", "h4", "h5"]):
                if re.search(r"(fully solved|problems solved)", header.get_text(), re.I):
                    parent = header.find_parent("section") or header.find_parent("div")
                    if parent:
                        sections.append(parent)

        for sec in sections:
            # Look for <a> tags pointing to problems or status
            for a in sec.find_all("a", href=True):
                href = a["href"]
                # Patterns: /problems/FLOW001 or /status/FLOW001,username or /START123/problems/FLOW001
                m = re.search(r"/(?:[A-Z0-9_]+/)?problems/([a-zA-Z0-9_\.\-]+)", href)
                if m:
                    solved.add(m.group(1).upper())
                m_status = re.search(r"/status/([a-zA-Z0-9_\.\-]+),", href)
                if m_status:
                    solved.add(m_status.group(1).upper())

            # Also check text/spans inside <p> or <article> under contest/practice headers
            # CodeChef lists problem titles and codes inside <span> tags
            for span in sec.find_all("span"):
                txt = span.get_text().strip()
                # Split comma-separated lists
                parts = [p.strip() for p in re.split(r"[,;]+", txt) if p.strip()]
                for part in parts:
                    # If looks like a problem code (alphanumeric, e.g. TEST, FLOW001)
                    if re.match(r"^[A-Z0-9_\.\-]{2,20}$", part, re.I):
                        solved.add(part.upper())
                    # Also store exact text uppercase for title/name matches
                    solved.add(part.upper())

        return solved

    def _fetch_recent_ac_submissions(self, username: str, max_pages: int = 2) -> Set[str]:
        """Query CodeChef's recent user submissions endpoint to extract AC problem codes."""
        solved: Set[str] = set()
        for page in range(max_pages):
            api_url = f"{self.BASE_URL}/recent/user?page={page}&user_handle={username.strip()}"
            try:
                self._sleep_with_jitter()
                resp = self.session.get(api_url, timeout=self.timeout)
                if resp.status_code != 200:
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
                for tr in rows[1:]:  # Skip header
                    cells = tr.find_all(["td", "th"])
                    if len(cells) >= 3:
                        prob_cell = cells[1]
                        result_cell = cells[2]
                        result_text = result_cell.get_text().strip()
                        # Check if result is AC (100 pts or tick mark)
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

                # If no more pages
                if data.get("max_page", 0) <= page + 1:
                    break
            except Exception as e:
                logger.debug(f"[CodeChef] recent submissions error for {username} on page {page}: {e}")
                break

        return solved
