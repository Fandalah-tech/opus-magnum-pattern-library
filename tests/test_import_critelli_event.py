import base64

from tools.import_critelli_event import Link, LinkParser, decode_data_uri, discover_file_links, parse_links


def test_discovers_relative_puzzle_and_solution_links():
    html = b'''<html><body>
      <a href="/files/weeklies2026_liquid-perfumes.puzzle" download>download puzzle</a>
      <a href="/download/abc.solution">Player A solution</a>
      <a href="https://example.com/foreign.solution">foreign</a>
      <form action="/submissions/export"></form>
    </body></html>'''
    links, forms, embedded = parse_links(html, "https://events.critelli.technology/event")
    puzzles = discover_file_links(links, embedded, ".puzzle", "https://events.critelli.technology/event")
    solutions = discover_file_links(links, embedded, ".solution", "https://events.critelli.technology/event")
    assert [link.url for link in puzzles] == ["https://events.critelli.technology/files/weeklies2026_liquid-perfumes.puzzle"]
    assert [link.url for link in solutions] == ["https://events.critelli.technology/download/abc.solution"]
    assert forms == ["https://events.critelli.technology/submissions/export"]


def test_download_attribute_can_identify_file_type():
    links = [Link("https://events.critelli.technology/download?id=1", "download", "entry.solution")]
    found = discover_file_links(links, [], ".solution", "https://events.critelli.technology/")
    assert found == links


def test_critelli_inline_puzzle_data_uri_is_discovered_and_decoded():
    payload = b"\x03\x00\x00\x00LIQUID PERFUMES"
    encoded = base64.b64encode(payload).decode("ascii")
    html = f'''<a id="puzzle-link" href="data:application/octet-stream;base64,{encoded}" download="weeklies2026_liquid-perfumes.puzzle">download</a>'''

    parser = LinkParser("https://events.critelli.technology/OM2026Weeklies1_LiquidPerfumes")
    parser.feed(html)
    links = discover_file_links(parser.links, parser.embedded_urls, ".puzzle", parser.base_url)

    assert len(links) == 1
    assert links[0].download_name == "weeklies2026_liquid-perfumes.puzzle"
    data, content_type = decode_data_uri(links[0].url)
    assert content_type == "application/octet-stream"
    assert data == payload
