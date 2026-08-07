"""Parsing and allocation logic. No network — the API client is exercised by
running `ingestion.fetch`, not by a test that would be slow and flaky."""

from ingestion.arxiv_api import _parse, _strip_version
from ingestion.fetch import MIN_PER_YEAR, allocate

ATOM_FIXTURE = b"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom"
      xmlns:opensearch="http://a9.com/-/spec/opensearch/1.1/">
  <opensearch:totalResults>1234</opensearch:totalResults>
  <entry>
    <id>http://arxiv.org/abs/2608.06377v2</id>
    <published>2026-08-06T17:59:12Z</published>
    <title>Learning When
  to Trust</title>
    <summary>  We study when a model should defer.
  Line wrapped, as arXiv ships it.
</summary>
    <author><name>A. Author</name></author>
    <author><name>B. Author</name></author>
    <category term="cs.CL"/>
    <category term="cs.AI"/>
  </entry>
  <entry>
    <id>http://arxiv.org/abs/1706.03762v5</id>
    <published>2017-06-12T00:00:00Z</published>
    <title>No summary here</title>
    <author><name>C. Author</name></author>
    <category term="cs.LG"/>
  </entry>
</feed>
"""


def test_version_suffix_is_stripped():
    # v2 and v5 of one paper must not become two rows with two primary keys.
    assert _strip_version("http://arxiv.org/abs/2608.06377v2") == "2608.06377"
    assert _strip_version("http://arxiv.org/abs/1706.03762v15") == "1706.03762"


def test_id_without_a_version_survives_intact():
    assert _strip_version("http://arxiv.org/abs/2608.06377") == "2608.06377"


def test_parse_reads_total_and_fields():
    papers, total = _parse(ATOM_FIXTURE)
    assert total == 1234

    paper = papers[0]
    assert paper.id == "2608.06377"
    assert paper.authors == "A. Author, B. Author"
    assert paper.categories == "cs.CL cs.AI"
    assert paper.published == "2026-08-06"


def test_entries_without_an_abstract_are_skipped():
    """A paper with no summary cannot be retrieved against, so it is not a paper."""
    papers, _ = _parse(ATOM_FIXTURE)
    assert [p.id for p in papers] == ["2608.06377"]


def test_allocation_totals_exactly_the_limit():
    counts = {y: 1000 * (y - 2014) for y in range(2015, 2027)}
    assert sum(allocate(counts, 10_000).values()) == 10_000


def test_allocation_gives_every_year_at_least_the_floor():
    counts = {2015: 6_796, 2020: 44_901, 2026: 81_541}
    quota = allocate(counts, 10_000)
    assert all(n >= MIN_PER_YEAR for n in quota.values())


def test_allocation_never_asks_for_more_than_a_year_has():
    counts = {2015: 40, 2026: 90_000}
    quota = allocate(counts, 10_000)
    assert quota[2015] <= 40


def test_allocation_still_works_when_the_limit_is_below_the_floors():
    counts = {y: 50_000 for y in range(2015, 2027)}
    quota = allocate(counts, 100)
    assert sum(quota.values()) <= 100
    assert all(n >= 1 for n in quota.values())
