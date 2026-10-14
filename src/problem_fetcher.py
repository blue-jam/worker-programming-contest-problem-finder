"""Module for automatically finding and fetching contest problem candidates from CodeChef and Kattis.

Supports balanced difficulty selection across AtCoder rating tiers (Brown to Red),
primarily using CodeChef with automatic fallback/supplementation from Kattis.
"""

from dataclasses import dataclass, field
import logging
import random
import time
from typing import Dict, List, Optional, Set, Tuple
from bs4 import BeautifulSoup
import requests

logger = logging.getLogger(__name__)


@dataclass
class DifficultyTier:
    """Represents a difficulty tier mapped to AtCoder color levels."""
    tier: int
    name: str
    atcoder_target: str
    codechef_min_rating: int
    codechef_max_rating: int
    codechef_page_range: Tuple[int, int]  # (start_page, end_page) for limit=50
    kattis_min_diff: float
    kattis_max_diff: float
    kattis_filter_str: str


# Default 5 tiers covering AtCoder Brown (400) to Red (2800+)
DEFAULT_TIERS: List[DifficultyTier] = [
    DifficultyTier(
        tier=1,
        name="Tier 1 (Easy)",
        atcoder_target="茶色 (400 - 799) 相当",
        codechef_min_rating=1000,
        codechef_max_rating=1399,
        codechef_page_range=(82, 95),
        kattis_min_diff=1.8,
        kattis_max_diff=2.8,
        kattis_filter_str="1-3",
    ),
    DifficultyTier(
        tier=2,
        name="Tier 2 (Medium-Low)",
        atcoder_target="緑色 (800 - 1199) 相当",
        codechef_min_rating=1400,
        codechef_max_rating=1699,
        codechef_page_range=(71, 82),
        kattis_min_diff=2.9,
        kattis_max_diff=4.2,
        kattis_filter_str="3-5",
    ),
    DifficultyTier(
        tier=3,
        name="Tier 3 (Medium)",
        atcoder_target="水色 (1200 - 1599) 相当",
        codechef_min_rating=1700,
        codechef_max_rating=2099,
        codechef_page_range=(55, 71),
        kattis_min_diff=4.3,
        kattis_max_diff=5.6,
        kattis_filter_str="4-6",
    ),
    DifficultyTier(
        tier=4,
        name="Tier 4 (Hard)",
        atcoder_target="青・黄色 (1600 - 2399) 相当",
        codechef_min_rating=2100,
        codechef_max_rating=2499,
        codechef_page_range=(38, 55),
        kattis_min_diff=5.7,
        kattis_max_diff=7.0,
        kattis_filter_str="6-8",
    ),
    DifficultyTier(
        tier=5,
        name="Tier 5 (Very Hard)",
        atcoder_target="橙・赤色 (2400 - 2800+) 相当",
        codechef_min_rating=2500,
        codechef_max_rating=3200,
        codechef_page_range=(10, 38),
        kattis_min_diff=7.1,
        kattis_max_diff=9.0,
        kattis_filter_str="7-9",
    ),
]


@dataclass
class CandidateProblem:
    """Problem candidate metadata."""
    platform: str  # "codechef" or "kattis"
    code: str
    name: str
    tier: int
    tier_name: str
    atcoder_target: str
    rating: Optional[int] = None
    kattis_diff: Optional[float] = None
    solves_count: int = 0
    url: str = ""

    def __hash__(self):
        return hash((self.platform, self.code.lower()))

    def __eq__(self, other):
        if not isinstance(other, CandidateProblem):
            return False
        return self.platform == other.platform and self.code.lower() == other.code.lower()


class CodeChefProblemFetcher:
    """Fetches candidate problems from CodeChef by difficulty rating."""

    API_URL = "https://www.codechef.com/api/list/problems"

    def __init__(
        self,
        session: Optional[requests.Session] = None,
        timeout: int = 15,
        user_agent: Optional[str] = None,
    ):
        self.session = session or requests.Session()
        self.timeout = timeout
        self.user_agent = user_agent or (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        )
        self.session.headers.update({
            "User-Agent": self.user_agent,
            "Accept": "application/json, text/plain, */*",
        })
        self._page_cache: Dict[int, List[dict]] = {}

    def fetch_page(self, page: int, limit: int = 50) -> List[dict]:
        """Fetch a page of rated problems."""
        if page in self._page_cache:
            return self._page_cache[page]

        params = {
            "page": page,
            "limit": limit,
            "sort_by": "difficulty_rating",
            "sort_order": "desc",
            "category": "rated",
        }
        try:
            resp = self.session.get(self.API_URL, params=params, timeout=self.timeout)
            if resp.status_code == 200:
                data = resp.json()
                items = data.get("data", [])
                self._page_cache[page] = items
                return items
            else:
                logger.warning("CodeChef API returned HTTP %s for page %d", resp.status_code, page)
                return []
        except Exception as e:
            logger.error("Failed to fetch CodeChef problems for page %d: %s", page, e)
            return []

    def fetch_tier_candidates(
        self,
        tier: DifficultyTier,
        min_solves: int = 15,
        max_solves: int = 10000,
        sample_pages: int = 4,
    ) -> List[CandidateProblem]:
        """Fetch problems belonging to the specified tier."""
        p_start, p_end = tier.codechef_page_range
        available_pages = list(range(p_start, p_end + 1))
        random.shuffle(available_pages)
        pages_to_check = available_pages[:sample_pages]

        results: List[CandidateProblem] = []
        seen_codes: Set[str] = set()

        for page in pages_to_check:
            items = self.fetch_page(page)
            for it in items:
                code = it.get("code", "").strip()
                if not code or code in seen_codes:
                    continue

                raw_rating = it.get("difficulty_rating")
                if not raw_rating or raw_rating in ("-1", "9999"):
                    continue

                try:
                    rating = int(raw_rating)
                except ValueError:
                    continue

                if not (tier.codechef_min_rating <= rating <= tier.codechef_max_rating):
                    continue

                # Filter by solves to avoid unsolvable edge cases or universal trivial problems
                try:
                    solves = int(it.get("distinct_successful_submissions") or it.get("successful_submissions") or 0)
                except (ValueError, TypeError):
                    solves = 0

                if solves < min_solves or (max_solves and solves > max_solves):
                    continue

                seen_codes.add(code)
                prob = CandidateProblem(
                    platform="codechef",
                    code=code,
                    name=it.get("name", code),
                    tier=tier.tier,
                    tier_name=tier.name,
                    atcoder_target=tier.atcoder_target,
                    rating=rating,
                    solves_count=solves,
                    url=f"https://www.codechef.com/problems/{code}",
                )
                results.append(prob)

        random.shuffle(results)
        return results


class KattisProblemFetcher:
    """Fetches candidate problems from Kattis by difficulty filter."""

    BASE_URL = "https://open.kattis.com/problems"

    def __init__(
        self,
        session: Optional[requests.Session] = None,
        timeout: int = 15,
        user_agent: Optional[str] = None,
    ):
        self.session = session or requests.Session()
        self.timeout = timeout
        self.user_agent = user_agent or (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        )
        self.session.headers.update({
            "User-Agent": self.user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        })
        self._filter_cache: Dict[str, List[CandidateProblem]] = {}

    def fetch_tier_candidates(
        self,
        tier: DifficultyTier,
        min_solves: int = 10,
        max_solves: int = 10000,
    ) -> List[CandidateProblem]:
        """Fetch Kattis problems matching tier difficulty."""
        filter_str = tier.kattis_filter_str
        if filter_str in self._filter_cache:
            return list(self._filter_cache[filter_str])

        url = f"{self.BASE_URL}?f_difficulty={filter_str}"
        results: List[CandidateProblem] = []

        try:
            resp = self.session.get(url, timeout=self.timeout)
            if resp.status_code != 200:
                logger.warning("Kattis problems list returned HTTP %s", resp.status_code)
                return []

            soup = BeautifulSoup(resp.text, "html.parser")
            tables = soup.find_all("table", class_="table2")
            if len(tables) < 2:
                return []

            table = tables[1]
            rows = table.find_all("tr")[1:]

            for row in rows:
                tds = row.find_all("td")
                if len(tds) < 7:
                    continue

                link = tds[0].find("a")
                if not link or not link.get("href", "").startswith("/problems/"):
                    continue

                code = link["href"].split("/")[-1].strip()
                name = link.text.strip()

                diff_text = tds[6].text.strip().split()[0] if len(tds) > 6 else ""
                try:
                    diff = float(diff_text)
                except ValueError:
                    continue

                if not (tier.kattis_min_diff <= diff <= tier.kattis_max_diff):
                    continue

                solves_text = tds[4].text.strip().replace(",", "") if len(tds) > 4 else "0"
                try:
                    solves = int(solves_text)
                except ValueError:
                    solves = 0

                if solves < min_solves or (max_solves and solves > max_solves):
                    continue

                prob = CandidateProblem(
                    platform="kattis",
                    code=code,
                    name=name,
                    tier=tier.tier,
                    tier_name=tier.name,
                    atcoder_target=tier.atcoder_target,
                    kattis_diff=diff,
                    solves_count=solves,
                    url=f"https://open.kattis.com/problems/{code}",
                )
                results.append(prob)

            random.shuffle(results)
            self._filter_cache[filter_str] = results
            return results

        except Exception as e:
            logger.error("Failed to fetch Kattis problems for filter %s: %s", filter_str, e)
            return []


class AutoProblemSelector:
    """Selects balanced problem sets across difficulty tiers.
    
    CodeChef is prioritized as the primary source, with Kattis serving as
    a fallback or complementary source when CodeChef problem pool is insufficient.
    """

    def __init__(
        self,
        tiers: Optional[List[DifficultyTier]] = None,
        prefer_codechef: bool = True,
        use_kattis_fallback: bool = True,
        min_solves: int = 15,
        max_solves: int = 8000,
    ):
        self.tiers = tiers or DEFAULT_TIERS
        self.prefer_codechef = prefer_codechef
        self.use_kattis_fallback = use_kattis_fallback
        self.min_solves = min_solves
        self.max_solves = max_solves

        self.codechef_fetcher = CodeChefProblemFetcher()
        self.kattis_fetcher = KattisProblemFetcher()

        # Cache of candidate pools per tier
        self._pools: Dict[int, List[CandidateProblem]] = {}

    def get_candidate_pool_for_tier(self, tier: DifficultyTier) -> List[CandidateProblem]:
        """Get candidate problem list for a specific tier."""
        if tier.tier in self._pools and self._pools[tier.tier]:
            return self._pools[tier.tier]

        candidates: List[CandidateProblem] = []

        # 1. Fetch from CodeChef first
        if self.prefer_codechef:
            cc_probs = self.codechef_fetcher.fetch_tier_candidates(
                tier=tier,
                min_solves=self.min_solves,
                max_solves=self.max_solves,
            )
            candidates.extend(cc_probs)

        # 2. If candidates are low or fallback is enabled
        if self.use_kattis_fallback and len(candidates) < 10:
            kattis_probs = self.kattis_fetcher.fetch_tier_candidates(
                tier=tier,
                min_solves=self.min_solves,
                max_solves=self.max_solves,
            )
            # Add Kattis problems to pool
            candidates.extend(kattis_probs)

        self._pools[tier.tier] = candidates
        return candidates

    def get_next_candidate(
        self,
        tier: DifficultyTier,
        excluded_codes: Set[str],
    ) -> Optional[CandidateProblem]:
        """Fetch the next available candidate problem for this tier not in excluded_codes."""
        pool = self.get_candidate_pool_for_tier(tier)
        for prob in pool:
            if prob.code.lower() not in excluded_codes:
                return prob

        # If pool exhausted, try forcing Kattis fetch if not already done
        if self.use_kattis_fallback:
            kattis_probs = self.kattis_fetcher.fetch_tier_candidates(
                tier=tier,
                min_solves=self.min_solves,
                max_solves=self.max_solves,
            )
            for prob in kattis_probs:
                if prob.code.lower() not in excluded_codes:
                    pool.append(prob)
                    return prob

        return None
