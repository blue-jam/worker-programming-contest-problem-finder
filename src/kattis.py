"""Kattis platform scraper module.

Handles fetching user profile, solved problems, and checking problem solver lists.
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
class KattisUserResult:
    username: str
    exists: bool
    solved_problems: Set[str] = field(default_factory=set)
    profile_url: str = ""
    error_message: Optional[str] = None


class KattisScraper:
    BASE_URL = "https://open.kattis.com"

    def __init__(
        self,
        base_delay: float = 1.0,
        max_jitter: float = 0.8,
        session: Optional[requests.Session] = None,
        timeout: int = 15,
        user_agent: Optional[str] = None,
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

        # Memory cache
        self._user_cache: Dict[str, KattisUserResult] = {}
        self._problem_solvers_cache: Dict[str, Set[str]] = {}

    def _sleep_with_jitter(self):
        """Sleep to respect rate limits and prevent bans."""
        duration = self.base_delay + random.uniform(0.1, self.max_jitter)
        time.sleep(duration)

    def fetch_user(self, username: str) -> KattisUserResult:
        """Fetch user profile and extract solved problems from Kattis."""
        lower_user = username.strip().lower()
        if lower_user in self._user_cache:
            return self._user_cache[lower_user]

        url = f"{self.BASE_URL}/users/{username.strip()}"
        logger.debug(f"[Kattis] Fetching user: {username} ({url})")

        self._sleep_with_jitter()
        try:
            resp = self.session.get(url, timeout=self.timeout)
            if resp.status_code == 404:
                result = KattisUserResult(
                    username=username,
                    exists=False,
                    profile_url=url,
                    error_message="User not found (404)",
                )
                self._user_cache[lower_user] = result
                return result

            resp.raise_for_status()

            # Parse HTML for solved problems
            soup = BeautifulSoup(resp.text, "html.parser")
            solved = self._parse_solved_problems(soup)

            result = KattisUserResult(
                username=username,
                exists=True,
                solved_problems=solved,
                profile_url=url,
            )
            self._user_cache[lower_user] = result
            return result

        except requests.RequestException as e:
            logger.warning(f"[Kattis] Request error for {username}: {e}")
            result = KattisUserResult(
                username=username,
                exists=False,
                profile_url=url,
                error_message=str(e),
            )
            self._user_cache[lower_user] = result
            return result

    def _parse_solved_problems(self, soup: BeautifulSoup) -> Set[str]:
        """Extract problem IDs from Kattis user profile page."""
        solved: Set[str] = set()

        # 1. Look for tables or sections labeled "Solved problems"
        for table in soup.find_all("table"):
            # Check headers or surrounding titles
            header_text = table.get_text()
            if "solved" in header_text.lower():
                for a in table.find_all("a", href=True):
                    href = a["href"]
                    m = re.match(r"^/problems/([a-zA-Z0-9_\.\-]+)/?$", href)
                    if m:
                        solved.add(m.group(1).lower())

        # 2. Look for any /problems/<id> links within the main content
        main_content = soup.find("main") or soup.find("body")
        if main_content:
            for a in main_content.find_all("a", href=True):
                href = a["href"]
                # Skip navigation links like /problems
                if href == "/problems" or href.startswith("/problems?"):
                    continue
                m = re.match(r"^/problems/([a-zA-Z0-9_\.\-]+)/?$", href)
                if m:
                    prob_id = m.group(1).lower()
                    # Filter out common UI sub-paths
                    if prob_id not in {"search", "submit", "statistics"}:
                        solved.add(prob_id)

        return solved

    def fetch_problem_solvers(self, problem_id: str) -> Set[str]:
        """Fetch list of user handles who solved a specific problem on Kattis.

        Used as a robust verification mechanism when user profile tabs are restricted.
        """
        prob = problem_id.strip().lower()
        if prob in self._problem_solvers_cache:
            return self._problem_solvers_cache[prob]

        url = f"{self.BASE_URL}/problems/{prob}/statistics"
        logger.debug(f"[Kattis] Fetching problem statistics: {prob} ({url})")

        self._sleep_with_jitter()
        solvers: Set[str] = set()
        try:
            resp = self.session.get(url, timeout=self.timeout)
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, "html.parser")
                for a in soup.find_all("a", href=True):
                    href = a["href"]
                    m = re.match(r"^/users/([a-zA-Z0-9_\.\-]+)/?$", href)
                    if m:
                        solvers.add(m.group(1).lower())
            else:
                logger.debug(f"[Kattis] Statistics page for {prob} returned {resp.status_code}")
        except requests.RequestException as e:
            logger.warning(f"[Kattis] Error fetching problem solvers for {prob}: {e}")

        self._problem_solvers_cache[prob] = solvers
        return solvers
