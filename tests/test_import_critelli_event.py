from tools.import_critelli_event import Link, discover_file_links, parse_links


def test_discovers_relative_puzzle_and_solution_links():
    html = b'''<html><body>
      <a href="/files/weeklies2026_liquid-perfumes.puzzle" download>download puzzle</a>
      <a href="/download/abc.solution">Player A solution</a>
      <a href="https://example.com/foreign.solution">foreign</a>
      <form action="/submissions/export"></form>
    </body></html>'''
    links, forms = parse_links(html, "https://events.critelli.technology/event")
    puzzles = discover_file_links(links, ".puzzle", "https://events.critelli.technology/event")
    solutions = discover_file_links(links, ".solution", "https://events.critelli.technology/event")
    assert [link.url for link in puzzles] == ["https://events.critelli.technology/files/weeklies2026_liquid-perfumes.puzzle"]
    assert [link.url for link in solutions] == ["https://events.critelli.technology/download/abc.solution"]
    assert forms == ["https://events.critelli.technology/submissions/export"]


def test_download_attribute_can_identify_file_type():
    links = [Link("https://events.critelli.technology/download?id=1", "download", "entry.solution")]
    found = discover_file_links(links, ".solution", "https://events.critelli.technology/")
    assert found == links
