from __future__ import annotations

import pytest

from trackaipac_cache.models import ParsedRecord
from trackaipac_cache.parser import (
    SeatInfo,
    extract_sections,
    make_candidate_id,
    normalize_name,
    parse_election_date,
    parse_money,
    parse_seat,
    parse_source,
    split_blocks,
    split_pacs,
)
from trackaipac_cache.parser import _plain


def recs(result, name) -> list[ParsedRecord]:
    return [r for r in result.records if r.name == name]


def rec(result, name) -> ParsedRecord:
    matches = recs(result, name)
    assert len(matches) == 1, f"{name}: {len(matches)} records"
    return matches[0]


# --------------------------------------------------------------------------- nothing dropped


def test_every_list_item_becomes_one_row(parsed):
    for source, count in [("candidates", 54), ("endorsements", 56), ("congress", 535)]:
        result = parsed[source]
        assert result.total_items == count
        assert len(result.records) == count
        assert result.unnamed == []


def test_rows_keep_page_order_and_sections(parsed):
    candidates = parsed["candidates"].records
    assert [r.name for r in candidates[:3]] == ["Mary Peltola", "Amish Shah", "Mark Lamb"]
    assert {r.section for r in candidates} == {None}

    endorsed = parsed["endorsements"].records
    assert [r.section for r in endorsed].count("Candidates Endorsed By Citizens Against AIPAC COrruption") == 36
    assert [r.section for r in endorsed].count("Our Endorsed Incumbents") == 20

    congress = parsed["congress"].records
    assert congress[0].section == "Alabama" and congress[-1].section == "Wyoming"
    assert len({r.section for r in congress}) == 50


def test_every_parsed_value_comes_from_lines(parsed):
    for result in parsed.values():
        for r in result.records:
            plain = [_plain(line) for line in r.lines]
            assert set(r.notes) <= set(r.lines)
            assert r.title is None or r.title in plain
            assert r.seat_text is None or r.seat_text in plain
            for pac in r.pacs:
                assert any(pac in line for line in plain), (r.name, pac)


def test_vacant_seats_are_kept(parsed):
    vacant = recs(parsed["congress"], "Vacant")
    assert [(r.candidate_id, r.seat_text, r.seat) for r in vacant] == [("fl-vacant", "FL-20", "FL-20"), ("tx-vacant", "TX- 23", "TX-23")]
    assert vacant[0].notes == ("Rep. Sheila Cherfilus-McCormick resigned from Congress on April 21, 2026.", "Special Election: TBD")


def test_row_without_seat_line_is_kept_as_shown(parsed):
    r = rec(parsed["congress"], "Chuck Fleischmann")
    assert (r.candidate_id, r.section, r.state) == ("tn-chuck-fleischmann", "Tennessee", "TN")
    assert (r.seat_text, r.seat, r.district, r.chamber, r.party) == (None, None, None, None, None)
    assert (r.israel_lobby_total, r.donations, r.ie, r.pacs) == (63999, 63999, 0, ("AIPAC", "AMP", "PHXED", "USI"))
    assert r.lines == ("Israel Lobby Total: $63,999", "PACs: $63,999", "IE: $0", "AIPAC, AMP, PHXED, USI")


def test_person_listed_twice_keeps_both_rows(parsed):
    challenger, incumbent = recs(parsed["endorsements"], "Analilia Mejia")
    assert challenger.candidate_id == incumbent.candidate_id == "nj-analilia-mejia"
    assert (challenger.title, challenger.seat_text, challenger.party, challenger.incumbent) == (
        "Candidate for U.S. House", "NJ-11 [D]", "D", False,
    )
    assert challenger.campaign_url == "https://www.analiliafornj.com/"
    assert (incumbent.title, incumbent.seat_text, incumbent.party, incumbent.incumbent) == (
        "U.S. Representative", "NJ-11", None, True,
    )
    assert incumbent.campaign_url is None


# --------------------------------------------------------------------------- watchlist


def test_watchlist_full_record(parsed):
    assert rec(parsed["candidates"], "Mary Peltola").snapshot_row() == {
        "candidate_id": "ak-mary-peltola",
        "source": "candidates",
        "category": "watchlist",
        "section": None,
        "name": "Mary Peltola",
        "title": "Candidate for U.S. Senate",
        "seat_text": "AK [D]",
        "seat": "AK-SEN",
        "state": "AK",
        "district": None,
        "chamber": "senate",
        "party": "D",
        "incumbent": False,
        "israel_lobby_total": 96546,
        "donations": 96546,
        "ie": 0,
        "pacs": ["JSTREET", "JDCA", "AIPAC ('24)", "DMFI ('24)", "JAC ('24)"],
        "election_date": None,
        "campaign_url": None,
        "donate_url": None,
        "notes": [],
        "lines": [
            "Candidate for U.S. Senate",
            "AK [D]",
            "Israel Lobby Total: $96,546",
            "Donations: $96,546",
            "IE: $0",
            "JSTREET, JDCA, AIPAC ('24), DMFI ('24), JAC ('24)",
        ],
    }


def test_watchlist_full_state_names(parsed):
    alme = rec(parsed["candidates"], "Kurt Alme")
    assert (alme.seat_text, alme.state, alme.chamber, alme.seat) == ("Montana [R]", "MT", "senate", "MT-SEN")
    paxton = rec(parsed["candidates"], "Ken Paxton")
    assert (paxton.seat_text, paxton.state, paxton.party, paxton.israel_lobby_total) == ("Texas [R]", "TX", "R", 0)


def test_watchlist_money_irregularities(parsed):
    c = parsed["candidates"]
    pulido = rec(c, "Bobby Pulido")
    assert pulido.israel_lobby_total is None and "Israel Lobby Total: TBD" in pulido.lines
    assert pulido.notes == ("Endorsed by DMFI",)
    sell = rec(c, "Tom Sell")  # no total line at all
    assert (sell.israel_lobby_total, sell.donations, sell.ie, sell.pacs) == (None, 30, 0, ("RJC",))
    fleming = rec(c, "John Fleming")
    assert fleming.donations == 30000 and 'Donations: $30,000"' in fleming.lines
    powell = rec(c, "Denise Powell")
    assert powell.ie == 41211 and "IE: $41,211*" in powell.lines
    jace = rec(c, "Jace Yarbrough")  # no donations line
    assert (jace.israel_lobby_total, jace.donations, jace.ie) == (10000, None, 0)


def test_watchlist_notes_are_verbatim(parsed):
    powell = rec(parsed["candidates"], "Denise Powell")
    assert powell.notes[0].startswith("[Passthrough Alert: New Democrat Majority PAC](https://prospect.org/")
    assert powell.notes[1].startswith("[This candidate is pro-Israel.](https://jewishinsider.com/")
    hernandez = rec(parsed["candidates"], "Melissa Hernandez")
    assert hernandez.pacs == ("AIPAC",)
    assert hernandez.notes[0].startswith("Passthrough PACS: Alameda Come Together PAC")


# --------------------------------------------------------------------------- endorsements


def test_endorsed_challenger(parsed):
    r = rec(parsed["endorsements"], "Robb Ryerse")
    assert (r.title, r.seat, r.party, r.incumbent) == ("Candidate for U.S. House", "AR-03", "D", False)
    assert r.campaign_url == "https://www.robbforcongress.com/"
    assert r.donate_url.startswith("https://secure.actblue.com/donate/robb-rejects-aipac")
    assert r.election_date == "2026-11-03" and r.notes == ("General Election",)
    assert r.israel_lobby_total is None and r.pacs == ()


def test_endorsed_incumbent_nothing_inferred(parsed):
    r = rec(parsed["endorsements"], "Chris Van Hollen")  # "U.S. Senator / Maryland"
    assert (r.seat_text, r.state, r.chamber, r.party, r.incumbent) == ("Maryland", "MD", "senate", None, True)
    assert r.donate_url == "https://vanhollen.org/"
    assert r.campaign_url is None  # the page only links a "Support Chris" button
    assert r.election_date is None and r.notes == ("Next Election: 2028",)


def test_endorsed_seat_variants(parsed):
    e = parsed["endorsements"]
    casar = rec(e, "Greg Casar")
    assert (casar.seat_text, casar.seat) == ("TX-35 (TX-37 2026)", "TX-35")
    assert rec(e, "Becca Balint").seat == "VT-AL"
    rabb = rec(e, "Chris Rabb")
    assert (rabb.title, rabb.chamber, rabb.seat) == ("Candidate for U.S. Congress", "house", "PA-03")
    frost = rec(e, "Maxwell Frost")
    assert frost.election_date is None and frost.notes == ("Running Unopposed",)
    assert rec(e, "Ayanna Pressley").election_date == "2026-09-01"


def test_accented_names(parsed):
    r = rec(parsed["endorsements"], "Angélica Dueñas")
    assert r.candidate_id == "ca-angelica-duenas"


# --------------------------------------------------------------------------- congress


def test_congress_label_and_seat_variants(parsed):
    c = parsed["congress"]
    bell = rec(c, "Wesley Bell")
    assert (bell.seat_text, bell.seat, bell.party) == ("MO-01 (D)", "MO-01", "D")
    assert (bell.israel_lobby_total, bell.donations, bell.ie) == (18126578, 4396533, 13730045)
    fedorchak = rec(c, "Julie Fedorchak")
    assert (fedorchak.seat_text, fedorchak.seat, fedorchak.party) == ("ND-At Large", "ND-AL", None)
    meng = rec(c, "Grace Meng")
    assert meng.israel_lobby_total == 998167 and "Lobby Total: $998,167" in meng.lines
    assert rec(c, "Salud Carbajal").donations == 50945  # "PACs:" label
    assert {r.incumbent for r in c.records} == {None}  # the page carries no office title
    assert sum(1 for r in c.records if r.chamber == "senate") == 100


def test_congress_pacs_as_written(parsed):
    c = parsed["congress"]
    markey = rec(c, "Ed Markey")  # curly quotes and a missing comma on the site
    assert markey.pacs[2:5] == ("AUSD (‘14)", "BIC (‘14)", "BICOUNTY (‘04)")
    bynum = rec(c, "Janelle Bynum")
    assert bynum.pacs == ("MSTD", "314 Action*")
    assert bynum.lines[-1].startswith("MSTD, [314 Action](https://readsludge.com/")
    assert rec(c, "Jake Ellzey").pacs == ()


def test_congress_notes_are_verbatim(parsed):
    c = parsed["congress"]
    khanna = rec(c, "Ro Khanna")
    assert khanna.israel_lobby_total is None
    assert khanna.notes[:2] == ("[Track AIPAC Approved!](/endorsements)", "[✔ Signed the PEACE Pledge](https://pledge.trackaipac.com/)")
    assert rec(c, "Haley Stevens").notes == ("[Running for U.S. Senate 2026](/haley-stevens)",)
    assert rec(c, "Ashley Moody").notes == ("2026 Special Election",)


def test_name_collision_across_states(parsed):
    ids = {rec(parsed["congress"], "Mike Rogers").candidate_id, rec(parsed["candidates"], "Mike Rogers").candidate_id}
    assert ids == {"al-mike-rogers", "mi-mike-rogers"}


# --------------------------------------------------------------------------- page structure


def test_page_chrome_is_ignored():
    html = """<h2>Pro-Israel candidates</h2><nav><a href="/x">Menu</a></nav>
    <ul><li class="list-item"><h2 class="list-item-content__title">Jane Doe</h2>
    <p>Candidate for U.S. House<br>OH-09 [D]</p><p>Israel Lobby Total: $5</p></li></ul>
    <footer><h2>Footer heading</h2><p>Copyright</p></footer>"""
    result = parse_source("candidates", html)
    assert [(r.name, r.seat, r.israel_lobby_total, r.notes, r.lines) for r in result.records] == [
        ("Jane Doe", "OH-09", 5, (), ("Candidate for U.S. House", "OH-09 [D]", "Israel Lobby Total: $5"))
    ]


def test_sections_and_unnamed_items():
    html = """<section id="a"><div class="list-section-title" id="1"><p>Ohio</p></div>
    <ul><li class="list-item"><h2 class="list-item-content__title">No Seat</h2><p>Israel Lobby Total: $1</p></li>
    <li class="list-item"><p>orphan text</p></li></ul></section>
    <section id="b"><ul><li class="list-item"><h2 class="list-item-content__title">Nowhere Person</h2></li></ul></section>"""
    assert [(title, len(items)) for title, items in extract_sections(html)] == [("Ohio", 2), (None, 1)]
    result = parse_source("congress", html)
    assert [(r.candidate_id, r.section, r.state) for r in result.records] == [
        ("oh-no-seat", "Ohio", "OH"),
        ("unk-nowhere-person", None, None),
    ]
    assert result.unnamed == ["* orphan text"]
    assert result.total_items == 3


# --------------------------------------------------------------------------- helpers


@pytest.mark.parametrize(
    "text, expected",
    [("$96,546", 96546), ("$ 0", 0), ('$30,000"', 30000), ("$41,211*", 41211), ("TBD", None), ("", None), (None, None)],
)
def test_parse_money(text, expected):
    assert parse_money(text) == expected


@pytest.mark.parametrize(
    "line, expected",
    [
        ("AZ-01 [D]", SeatInfo("AZ", "01", False, "D", None)),
        ("AK [D]", SeatInfo("AK", None, False, "D", None)),
        ("Montana [R]", SeatInfo("MT", None, False, "R", None)),
        ("New Hampshire [R]", SeatInfo("NH", None, False, "R", None)),
        ("AL-SEN [R]", SeatInfo("AL", None, True, "R", None)),
        ("ND-At Large", SeatInfo("ND", "AL", False, None, None)),
        ("VT-AL", SeatInfo("VT", "AL", False, None, None)),
        ("MO-01 (D)", SeatInfo("MO", "01", False, "D", None)),
        ("TX- 23", SeatInfo("TX", "23", False, None, None)),
        ("TX-35 (TX-37 2026)", SeatInfo("TX", "35", False, None, "TX-37 2026")),
        ("TX-35 [D] (TX-37 2026)", SeatInfo("TX", "35", False, "D", "TX-37 2026")),
        ("ME-SEN [I]", SeatInfo("ME", None, True, "I", None)),
    ],
)
def test_parse_seat(line, expected):
    assert parse_seat(line) == expected


@pytest.mark.parametrize("line", ["Israel Lobby Total: $5", "ZZ-01 [D]", "Atlantis [R]", "AIPAC, JSTREET", ""])
def test_parse_seat_rejects(line):
    assert parse_seat(line) is None


@pytest.mark.parametrize(
    "line, expected",
    [
        ("JSTREET, JDCA, AIPAC ('24)", ["JSTREET", "JDCA", "AIPAC ('24)"]),
        ("AIPAC (UDP), AMP, MAGA KY", ["AIPAC (UDP)", "AMP", "MAGA KY"]),
        ("BIC (‘14) BICOUNTY (‘04)", ["BIC (‘14)", "BICOUNTY (‘04)"]),
        ("MSTD, 314 Action*", ["MSTD", "314 Action*"]),
        ("Endorsed by DMFI", None),
        ("Retiring 2026", None),
        ("Up for Re-Election", None),
        ("This representative is newly elected.", None),
    ],
)
def test_split_pacs(line, expected):
    assert split_pacs(line) == expected


def test_ids_and_name_normalization():
    assert make_candidate_id("CA", "Angélica Dueñas") == "ca-angelica-duenas"
    assert make_candidate_id("TN", "Justin J. Pearson") == "tn-justin-j-pearson"
    assert make_candidate_id("TX", "Frederick Haynes III") == "tx-frederick-haynes-iii"
    assert make_candidate_id(None, "Al Green") == "unk-al-green"
    assert normalize_name("  ANGÉLICA   dueñas ") == normalize_name("Angelica Duenas") == "angelica duenas"


def test_parse_election_date():
    assert parse_election_date("November 3, 2026") == "2026-11-03"
    assert parse_election_date("September 1 2026") == "2026-09-01"
    assert parse_election_date("February 30, 2026") is None
    assert parse_election_date("Next Election: 2028") is None


def test_split_blocks_drops_preamble():
    text = "nav stuff\n\n* ## One\n\nAK [D]\n\n* ## Two\n\nAL-SEN [R]\n"
    assert [b.split("\n", 1)[0] for b in split_blocks(text)] == ["One", "Two"]
