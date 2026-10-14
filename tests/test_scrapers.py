from bs4 import BeautifulSoup
from src.kattis import KattisScraper
from src.codechef import CodeChefScraper

def test_kattis_parse_solved_problems():
    html = """
    <html>
      <body>
        <main>
          <table class="table">
            <thead><tr><th>Solved problems</th></tr></thead>
            <tbody>
              <tr><td><a href="/problems/bijele">Bijele</a></td></tr>
              <tr><td><a href="/problems/quadrant">Quadrant</a></td></tr>
            </tbody>
          </table>
        </main>
      </body>
    </html>
    """
    soup = BeautifulSoup(html, "html.parser")
    scraper = KattisScraper()
    solved = scraper._parse_solved_problems(soup)
    assert "bijele" in solved
    assert "quadrant" in solved

def test_codechef_parse_solved_problems():
    html = """
    <html>
      <body>
        <section class="problems-solved">
          <h5>Contests</h5>
          <p>
            <span><a href="/problems/FLOW001">FLOW001</a></span>,
            <span><a href="/status/TEST,user">TEST</a></span>
          </p>
        </section>
      </body>
    </html>
    """
    soup = BeautifulSoup(html, "html.parser")
    scraper = CodeChefScraper()
    solved = scraper._parse_solved_problems(soup)
    assert "FLOW001" in solved
    assert "TEST" in solved


def test_kattis_fetch_problem_solvers():
    scraper = KattisScraper()
    # Mocking session response
    class MockResponse:
        status_code = 200
        text = '<html><body><a href="/users/tourist">tourist</a><a href="/users/steve-allen">steve-allen</a></body></html>'
    scraper.session.get = lambda url, **kwargs: MockResponse()
    solvers = scraper.fetch_problem_solvers("bijele")
    assert "tourist" in solvers
    assert "steve-allen" in solvers

