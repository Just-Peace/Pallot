"""Each state's key dates: whose they are and how its calendar files word them, and, for a state
whose deadlines are fixed counts of days from Election Day, the dates worked out from that day
alone, with nothing fetched. Texas's come from its SOS's page (sources/key_dates.py) instead, and
California's from its SOS's (sources/ca_key_dates.py).
Arizona's are entered by hand from its Secretary of State's list, whose site blocks scripts; early
voting in person ends at 5 p.m. the Friday before Election Day (A.R.S. 16-542(E)).

Michigan's rules, as its Department of State gives them: registration online or by mail closes
15 days before Election Day, then it's in person at the clerk's office with proof of residency
through Election Day (MCL 168.497); early voting runs at least from the second Saturday before
through the Sunday before (MCL 168.720a, from Proposal 2 of 2022); any voter can vote absentee,
applying online or by mail by 5 p.m. the Friday before. Only its even-year August primary and
November general are statewide, the elections those rules are for.

Nevada's, for its general election (NRS 293.12755: the first Tuesday after the first Monday of
November in an even year): registration by mail or in person at the county clerk's closes the
fourth Tuesday before, online on Election Day itself (NRS 293.560), and in person at a polling
place it goes on through Election Day (NRS 293.5772 to 293.5887); every active voter is mailed a
ballot, and so is anyone who registers or updates their registration by 14 days before
(NRS 293.269911); early voting runs from the third Saturday before through the Friday before
(NRS 293.3568); a mailed ballot must be postmarked by Election Day and reach the clerk by 5 p.m.
on the fourth day after (NRS 293.269921); polls are open 7 a.m. to 7 p.m. (NRS 293.273).

Georgia's, for its general election (O.C.G.A. 21-2-9: the first Tuesday after the first Monday of
November in an even year): registration closes the fifth Monday before (21-2-224); any voter can
vote absentee, applying by the eleventh day before (21-2-381(a)(1)(A)), and the ballot must reach
the county's registrars by 7 p.m. on Election Day (21-2-386); advance voting runs weekdays from the
fourth Monday before through the Friday before, and on the second and third Saturdays before
(21-2-385(d)(1)), but not on an observed state holiday, so it starts the next day when that
Monday is Columbus Day; polls are open 7 a.m. to 7 p.m. (21-2-403).

Iowa's, for its general election (Iowa Code 39.1: the first Tuesday after the first Monday of
November in an even year), checked on legis.iowa.gov (Iowa Code 2026) on 2026-10-24:
pre-registration closes at 5 p.m. fifteen days before (48A.9), then voters register at the polls
on Election Day with ID and proof of residence (48A.7A); any voter can vote absentee, the written
application reaching the county auditor by 5 p.m. on that same day (53.2(1)(b)), and the ballot
must reach the auditor before the polls close (53.17); absentee voting in person at the auditor's
office starts twenty days before (53.10) and goes on any day but Election Day (53.2(1)(a)); polls
are open 7 a.m. to 8 p.m. (49.73).

Ohio's, for its general election (ORC 3501.01(A): the first Tuesday after the first Monday of
November), checked on codes.ohio.gov on 2026-10-22: registration closes the thirtieth day before
(3503.19), always a Sunday, so the next day that's neither a Sunday nor a legal holiday (1.14,
whose holidays include Columbus Day); early voting in person runs from the day after through 5 p.m.
on the Sunday before (3509.051); any voter can vote absentee, applying by the close of business on
the seventh day before (3509.03(D)), and since SB 293 (effective March 20, 2026) the ballot must
reach the county board by the close of the polls on Election Day (3509.05(D)), except a military or
overseas voter's, counted through the fourth day after (3511.11); polls are open 6:30 a.m. to 7:30
p.m. (3501.32). There's no registration on Election Day.

Wisconsin's, for its general election (Wis. Stat. 5.02(5): the Tuesday after the first Monday of
November in an even year): registration by mail or online closes the third Wednesday before
(6.28(1)), then it's in person at the municipal clerk's office until 5 p.m. the Friday before
(6.29(2)(a)), or at the polling place on Election Day (6.55(2)); any voter can vote absentee,
asking by mail or online by 5 p.m. the fifth day before, or in person at the clerk's office from
the fourteenth day before through the Sunday before (6.86(1)(b)), and the ballot must reach the
polling place by 8 p.m. on Election Day (6.87(6)); polls are open 7 a.m. to 8 p.m. (6.78(1m)).

New York's, for its general election (Election Law 8-100(1)(c): the Tuesday after the first Monday
of November, every year), checked on nysenate.gov on 2026-10-24: a registration must reach the
county board by the tenth day before (5-210(3)); early voting runs from the tenth day before
through the second day before (8-600(1)); an absentee or early mail ballot application online or
by mail must reach the board by the tenth day before, in person by the day before (8-400); a
mailed ballot must be postmarked by Election Day and reach the board within seven days after
(8-412); polls are open 6 a.m. to 9 p.m. (8-100(2)).

New Jersey's, for its general election (N.J.S.A. 19:2-3: the Tuesday after the first Monday of
November): registration closes the twenty-first day before (19:31-6.3); early voting in person
runs from the tenth day before through the second day before (19:15A-1); any voter can vote by
mail, applying by mail so the county clerk has it by the seventh day before, or in person at the
clerk's office until 3 p.m. the day before (19:63-3), and a mailed ballot must be postmarked by
Election Day and reach the county board of elections within 144 hours after the polls close
(19:63-22); polls are open 6 a.m. to 8 p.m. (19:15-2).

Illinois's, for its general election (10 ILCS 5/2A-1.1: the Tuesday after the first Monday of
November in an even year): registration by mail or in person closes the twenty-eighth day before
(5/4-6, 5/6-29), online the sixteenth day before (5/1A-16.5), then grace-period registration and
voting goes on in person through Election Day (5/4-50); early voting runs at the election
authority's offices from the fortieth day before, at its permanent polling places from the
fifteenth, through the day before (5/19A-15); any voter can vote by mail, an application by mail
reaching the election authority by the fifth day before (5/19-2), and the ballot must be
postmarked by Election Day and reach it within fourteen days after (5/19-8); polls are open
6 a.m. to 7 p.m. (5/17-1).

Alaska's, for its general election (AS 15.15.020: the Tuesday after the first Monday of November in
an even year), checked on akleg.gov on 2026-10-25: a registration must be made in person, or
postmarked or sent electronically, at least 30 days before (15.07.070(c), (d)); early voting runs
for the 15 days before and on Election Day (15.20.064(a)); any voter can vote absentee, an
application for a ballot by mail reaching the Division of Elections at least 10 days before
(15.20.081(b)), and a mailed ballot must be postmarked by Election Day and reach the election
supervisor by the close of business on the 10th day after (15.20.081(e)); polls are open 7 a.m.
to 8 p.m.

Colorado's, for its general election (C.R.S. 1-4-201: the Tuesday after the first Monday of
November in an even year): every active voter is mailed a ballot, sent from the twenty-second day
before (1-7.5-107(3)); registering online or by mail by the eighth day before still gets one
(1-2-201(3)), and after that a voter registers and votes in person at a voter service and polling
center through Election Day (1-2-217.7); the centers open the fifteenth day before (1-5-102.9); a
ballot must reach the county clerk by 7 p.m. on Election Day (1-7.5-107(4)); polls and centers are
open 7 a.m. to 7 p.m. on Election Day.

Wyoming's, for its general election (W.S. 22-2-104: the Tuesday after the first Monday of November
in an even year), as its Secretary of State's 2026 Key Election Dates give them: registration by
mail or at the county clerk's closes the fifteenth day before (22-3-102), then voters register in
person at the clerk's while voting absentee, or at the polls on Election Day (22-3-104); absentee
voting, by mail or in person at the clerk's, runs from the twenty-eighth day before through the
day before (22-9-125), a ballot can be asked for any time before Election Day, and it must reach
the clerk by 7 p.m. on Election Day (22-9-119); polls are open 7 a.m. to 7 p.m.
"""

from __future__ import annotations

import datetime as dt
import functools
from dataclasses import dataclass
from typing import Callable

from ..models import VoterInfo, VoterLink
from ..sources import ca_key_dates as california
from ..sources import key_dates as texas
from ..sources.key_dates import Deadlines


@dataclass(frozen=True)
class Guide:
    """A state's wording for its key dates, and how to vote there. ``register``, ``mail`` and the
    like are sentences with an ``{election}`` ("the November 3, 2026 election") to fill in; the
    ``check_``, ``where_`` and ``mail_`` fields and ``poll_hours`` are what the ballot's "When to
    vote" shows (voter_info)."""

    name: str
    source: str  # who the dates are from, or who explains the rules they're worked out by
    url: str
    computed: bool  # worked out from the state's election law, not read from a published list
    registration_url: str  # how to register
    mail_url: str  # how to vote by mail
    register: str
    mail_summary: str
    mail: str  # up to the colon before mail_url
    early_where: str
    credit: str  # the calendar file's line before the url
    poll_hours: str  # "7 a.m. – 8 p.m."
    check_url: str  # where voters check their registration
    check_hint: str
    where_url: str  # where voters find where to vote
    where_hint: str
    mail_label: str  # the words of the link to mail_url
    mail_eligibility: str  # who can vote by mail, and how the ballot gets back
    mail_deadline: str | None = None  # the words before the mail_apply_by date, where they aren't the usual
    local_office: str | None = None  # who sets where and when you vote, where it isn't the county elections office
    polls_text: str | None = None  # Election Day's line in the calendar file, where it isn't the usual (polls)

    @property
    def polls(self) -> str:
        """Election Day's line: "Polls are open 7 a.m. to 8 p.m.; if you're in line at 8, you can vote."."""
        if self.polls_text:
            return self.polls_text
        opens, closes = self.poll_hours.split(" – ")
        return f"Polls are open {opens} to {closes}; if you're in line at {closes.removesuffix(' p.m.')}, you can vote."

    def voter_info(self) -> VoterInfo:
        return VoterInfo(
            registration=VoterLink(label="Am I registered?", short="Registered?", url=self.check_url, hint=self.check_hint),
            county_offices=VoterLink(label="Where to vote", short="Where", url=self.where_url, hint=self.where_hint),
            mail_apply=VoterLink(label=self.mail_label, url=self.mail_url),
            mail_eligibility=self.mail_eligibility,
            mail_deadline=self.mail_deadline,
            local_office=self.local_office,
            poll_hours=self.poll_hours,
        )


TEXAS = Guide(
    name="Texas",
    source="Texas Secretary of State",
    url=texas.URL,
    computed=False,
    registration_url=texas.REGISTRATION_URL,
    mail_url=texas.MAIL_APPLY_URL,
    register="The last day to register to vote in {election} in Texas.",
    mail_summary="Mail-ballot application due",
    mail="If you vote by mail in {election}, your application must reach your county's early voting clerk today: "
         "received, not postmarked. Who can vote by mail, and how to apply:",
    early_where="Your county elections office lists the places and hours.",
    credit="Dates from the Texas Secretary of State",
    poll_hours="7 a.m. – 7 p.m.",
    check_url=texas.REGISTRATION_URL,
    check_hint="My Voter Portal (Texas SOS): your registration, and your polling place once you log in",
    where_url="https://www.votetexas.gov/voting/where.html",
    where_hint="Every county's elections office (Texas SOS); yours publishes where and when you can vote",
    mail_label="How to apply",
    mail_eligibility="Only if you're 65 or older, sick or disabled, away from your county for all of early voting and "
                     "Election Day, expecting to give birth around Election Day, or in jail but still eligible to vote.",
)

MICHIGAN = Guide(
    name="Michigan",
    source="Michigan Department of State",
    url="https://www.michigan.gov/sos/elections/voting",
    computed=True,
    registration_url="https://mvic.sos.state.mi.us/Voter/Index",
    mail_url="https://www.michigan.gov/sos/elections/voting/absentee-voting",
    register="The last day to register online or by mail for {election} in Michigan. After it, you can still "
             "register in person at your city or township clerk's office, with proof of residency, through Election "
             "Day.",
    mail_summary="Absentee application due",
    mail="If you vote absentee in {election}, an application made online or by mail must reach your city or township "
         "clerk by 5 p.m. today. In person, you can apply at the clerk's office until 4 p.m. the day before Election "
         "Day. Any voter can vote absentee; how to apply:",
    early_where="Your city or township clerk lists the places and hours, and may open early voting sooner.",
    credit="Dates worked out from Michigan's election law; more from the Michigan Department of State",
    poll_hours="7 a.m. – 8 p.m.",
    check_url="https://mvic.sos.state.mi.us/Voter/Index",
    check_hint="Michigan Voter Information Center: your registration and your polling place",
    where_url="https://mvic.sos.state.mi.us/Voter/Index#yourclerk",
    where_hint="Your city or township clerk (Michigan Voter Information Center), who publishes where and when you can "
               "vote early",
    mail_label="How to apply",
    mail_eligibility="Any registered voter can vote absentee, no reason needed. You can also apply in person at your "
                     "clerk's office until 4 p.m. the day before Election Day.",
    mail_deadline="Online and mailed applications must reach your clerk by 5 p.m. on ",
    local_office="Your city or township clerk",
)

CALIFORNIA = Guide(
    name="California",
    source="California Secretary of State",
    url=california.URL,
    computed=False,
    registration_url=california.REGISTRATION_URL,
    mail_url=california.MAIL_URL,
    register="The last day to register online or by mail (postmarked today) for {election} in California. After it, "
             "you can still register and vote at your county elections office or a vote center, through Election "
             "Day.",
    mail_summary="Ask for a replacement mail ballot",
    mail="Every active voter in California is mailed a ballot for {election}. If yours is lost or damaged, today is "
         "the Secretary of State's recommended last day to ask your county elections office for a new one:",
    early_where="Your county elections office takes ballots in person through Election Day; where your county has "
                "vote centers, they open at least 10 days before. Your county lists the places and hours.",
    credit="Dates from the California Secretary of State",
    poll_hours="7 a.m. – 8 p.m.",
    check_url=california.REGISTRATION_URL,
    check_hint="My Voter Status (California SOS): your registration, and where your mail ballot is",
    where_url=california.COUNTY_OFFICES_URL,
    where_hint="Every county's elections office (California SOS); yours lists its vote centers, polling places and drop "
               "boxes",
    mail_label="Voting by mail",
    mail_eligibility="Every active voter is mailed a ballot. Mail it back postmarked by Election Day (it must reach your "
                     "county within 7 days), or drop it off by 8 p.m. on Election Day.",
    mail_deadline="If yours is lost or damaged, the Secretary of State recommends asking your county for a new one by ",
)

ARIZONA = Guide(
    name="Arizona",
    source="Arizona Secretary of State",
    url="https://azsos.gov/elections",
    computed=False,
    registration_url="https://my.arizona.vote/",
    mail_url="https://my.arizona.vote/",
    register="The last day to register to vote in {election} in Arizona, by 11:59 p.m.",
    mail_summary="Early ballot request due",
    mail="If you vote early by mail in {election}, ask your county recorder for your ballot in time for it to reach "
         "you and come back by Election Day. Any voter can vote early by mail; how to ask:",
    early_where="Your county recorder lists the places and hours.",
    credit="Dates from the Arizona Secretary of State",
    poll_hours="6 a.m. – 7 p.m.",
    check_url="https://my.arizona.vote/",
    check_hint="Arizona.Vote (Arizona Secretary of State): your registration, your polling place and your ballot's "
               "status",
    where_url="https://my.arizona.vote/",
    where_hint="Arizona.Vote: your polling place; Maricopa and Pima counties also have their own lookups",
    mail_label="How to ask",
    mail_eligibility="Any registered voter can vote early by mail, no reason needed. Early ballots go out from "
                     "October 7; ask your county recorder for yours, or join the Active Early Voting List.",
    local_office="Your county recorder",
)

NEVADA = Guide(
    name="Nevada",
    source="Nevada Secretary of State",
    url="https://www.nvsos.gov/sos/elections",
    computed=True,
    registration_url="https://registertovote.nv.gov/",
    mail_url="https://www.nvsos.gov/sos/elections",
    register="The last day to register by mail or in person at your county clerk's office for {election} in Nevada. "
             "After it, you can still register online through Election Day, or in person at a polling place during "
             "early voting or on Election Day.",
    mail_summary="Last day to register and still be mailed a ballot",
    mail="Every active voter in Nevada is mailed a ballot for {election}. Register or update your registration by "
         "today to still be mailed one. Mailed back, it must be postmarked by Election Day and reach your county "
         "clerk by 5 p.m. on the fourth day after; or drop it off at any polling place or drop box by 7 p.m. on "
         "Election Day. More:",
    early_where="Your county clerk lists the places and hours.",
    credit="Dates worked out from Nevada's election law; more from the Nevada Secretary of State",
    poll_hours="7 a.m. – 7 p.m.",
    check_url="https://www.nvsos.gov/votersearch/",
    check_hint="Nevada Secretary of State's voter search: your registration and your polling place",
    where_url="https://www.nvsos.gov/sos/elections",
    where_hint="Nevada Secretary of State's elections page; your county clerk publishes where and when you can vote",
    mail_label="More on voting by mail",
    mail_eligibility="Every active voter is mailed a ballot. Mail it back postmarked by Election Day (it must arrive by "
                     "5 p.m. on the fourth day after), or drop it off at any polling place or drop box by 7 p.m. on "
                     "Election Day.",
    mail_deadline="To still be mailed one, register or update your registration by ",
    local_office="Your county clerk",
)

GEORGIA = Guide(
    name="Georgia",
    source="Georgia Secretary of State",
    url="https://sos.ga.gov/elections",
    computed=True,
    registration_url="https://mvp.sos.ga.gov/s/",
    mail_url="https://securemyabsenteeballot.sos.ga.gov/s/",
    register="The last day to register to vote in {election} in Georgia.",
    mail_summary="Absentee ballot application due",
    mail="If you vote absentee in {election}, your application must reach your county's board of registrars today. "
         "Your ballot must reach them by 7 p.m. on Election Day; one that arrives later isn't counted. Any voter can "
         "vote absentee; how to apply:",
    early_where="Your county's board of registrars lists the places and hours. Early voting is on weekdays, and on "
                "the second and third Saturdays before Election Day; some counties also open on Sundays.",
    credit="Dates worked out from Georgia's election law; more from the Georgia Secretary of State",
    poll_hours="7 a.m. – 7 p.m.",
    check_url="https://mvp.sos.ga.gov/s/",
    check_hint="My Voter Page (Georgia Secretary of State): your registration, your polling place and your sample "
               "ballot",
    where_url="https://mvp.sos.ga.gov/s/",
    where_hint="My Voter Page: your polling place and your county's early voting places",
    mail_label="How to apply",
    mail_eligibility="Any registered voter can vote absentee by mail, no reason needed. Your ballot must reach your "
                     "county by 7 p.m. on Election Day.",
    local_office="Your county's board of registrars",
)

IOWA = Guide(
    name="Iowa",
    source="Iowa Secretary of State",
    url="https://sos.iowa.gov/general-election",
    computed=True,
    registration_url="https://sos.iowa.gov/elections-voting",
    mail_url="https://sos.iowa.gov/elections-voting",
    register="The last day to pre-register for {election} in Iowa, by 5 p.m. After it, you can still register at "
             "your polling place on Election Day, with ID and proof of where you live.",
    mail_summary="Absentee ballot request due",
    mail="If you vote absentee in {election}, your request must reach your county auditor by 5 p.m. today. Your "
         "ballot must reach the auditor before the polls close at 8 p.m. on Election Day; one that arrives later "
         "isn't counted. Any voter can vote absentee; how to ask:",
    early_where="Your county auditor's office, and any satellite sites your county opens; the auditor lists the "
                "places and hours.",
    credit="Dates worked out from Iowa's election law; more from the Iowa Secretary of State",
    poll_hours="7 a.m. – 8 p.m.",
    check_url="https://sos.iowa.gov/elections-voting",
    check_hint="Iowa Secretary of State: check your registration and find your polling place",
    where_url="https://sos.iowa.gov/elections-voting",
    where_hint="Iowa Secretary of State: your polling place, and your county auditor's office for voting early",
    mail_label="How to ask",
    mail_eligibility="Any registered voter can vote absentee by mail, no reason needed. Your ballot must reach your "
                     "county auditor before the polls close at 8 p.m. on Election Day.",
    mail_deadline="Your request must reach your county auditor by 5 p.m. on ",
    local_office="Your county auditor",
)

OHIO = Guide(
    name="Ohio",
    source="Ohio Secretary of State",
    url="https://www.ohiosos.gov/elections/",
    computed=True,
    registration_url="https://olvr.ohiosos.gov/",
    mail_url="https://www.ohiosos.gov/elections/request-an-absentee-ballot",
    register="The last day to register to vote in {election} in Ohio. There's no registration on Election Day.",
    mail_summary="Absentee ballot application due",
    mail="If you vote absentee in {election}, your application must reach your county board of elections by the "
         "close of business today. Your ballot must reach the board by 7:30 p.m. on Election Day; one that arrives "
         "later isn't counted, even if it was mailed in time. Any voter can vote absentee; how to apply:",
    early_where="Your county board of elections lists the place and hours. Early voting ends at 5 p.m. on the Sunday "
                "before Election Day.",
    credit="Dates worked out from Ohio's election law; more from the Ohio Secretary of State",
    poll_hours="6:30 a.m. – 7:30 p.m.",
    check_url="https://voterlookup.ohiosos.gov/voterlookup.aspx",
    check_hint="Ohio Secretary of State's voter lookup: your registration and your polling place",
    where_url="https://www.ohiosos.gov/elections/county-boards-of-elections-directory",
    where_hint="Every county board of elections (Ohio Secretary of State); yours publishes where and when you can vote "
               "early",
    mail_label="How to apply",
    mail_eligibility="Any registered voter can vote absentee by mail, no reason needed. Your ballot must reach your "
                     "county board by 7:30 p.m. on Election Day: one mailed in time but arriving later isn't counted.",
    mail_deadline="Your application must reach your county board by the close of business on ",
    local_office="Your county board of elections",
)

WISCONSIN = Guide(
    name="Wisconsin",
    source="Wisconsin Elections Commission",
    url="https://elections.wi.gov/",
    computed=True,
    registration_url="https://myvote.wi.gov/",
    mail_url="https://myvote.wi.gov/",
    register="The last day to register online or by mail for {election} in Wisconsin. After it, you can still "
             "register in person at your municipal clerk's office until 5 p.m. on the Friday before, or at your "
             "polling place on Election Day, with proof of residence.",
    mail_summary="Absentee ballot request due",
    mail="If you vote absentee in {election}, a request made online or by mail must reach your municipal clerk by "
         "5 p.m. today. Your ballot must reach your polling place or clerk by 8 p.m. on Election Day; one that "
         "arrives later isn't counted. Any voter can vote absentee; how to ask:",
    early_where="Your municipal clerk sets the places and hours, and may start later than the first day allowed.",
    credit="Dates worked out from Wisconsin's election law; more from the Wisconsin Elections Commission",
    poll_hours="7 a.m. – 8 p.m.",
    check_url="https://myvote.wi.gov/",
    check_hint="MyVote Wisconsin (Wisconsin Elections Commission): your registration, your polling place and your "
               "ballot",
    where_url="https://myvote.wi.gov/",
    where_hint="MyVote Wisconsin: your polling place, and your municipal clerk's office for voting early",
    mail_label="How to apply",
    mail_eligibility="Any registered voter can vote absentee by mail, no reason needed. Your ballot must reach your "
                     "polling place or clerk by 8 p.m. on Election Day.",
    mail_deadline="Mailed or online requests must reach your clerk by 5 p.m. on ",
    local_office="Your municipal clerk",
)

NEW_YORK = Guide(
    name="New York",
    source="New York State Board of Elections",
    url="https://elections.ny.gov/",
    computed=True,
    registration_url="https://elections.ny.gov/register-vote",
    mail_url="https://absenteeballot.elections.ny.gov/",
    register="The last day for your registration to reach your county board of elections for {election} in New York.",
    mail_summary="Early mail or absentee ballot application due",
    mail="If you vote by mail in {election}, an application made online or by mail must reach your county board of "
         "elections today; in person, you can apply until the day before Election Day. Your ballot must be "
         "postmarked by Election Day and reach the board within 7 days after. Any voter can vote early by mail; "
         "how to apply:",
    early_where="Your county board of elections sets the places and hours.",
    credit="Dates worked out from New York's Election Law; more from the New York State Board of Elections",
    poll_hours="6 a.m. – 9 p.m.",
    check_url="https://voterlookup.elections.ny.gov/",
    check_hint="New York State Board of Elections' voter lookup: your registration and your polling place",
    where_url="https://voterlookup.elections.ny.gov/",
    where_hint="The voter lookup: your polling place; your county board of elections publishes its early voting places",
    mail_label="How to apply",
    mail_eligibility="Any registered voter can vote early by mail, no reason needed. Your ballot must be postmarked by "
                     "Election Day and reach your county board within 7 days after.",
    mail_deadline="Online or mailed applications must reach your county board by ",
    local_office="Your county board of elections",
)

NEW_JERSEY = Guide(
    name="New Jersey",
    source="New Jersey Division of Elections",
    url="https://www.nj.gov/state/elections/",
    computed=True,
    registration_url="https://voter.svrs.nj.gov/register",
    mail_url="https://www.nj.gov/state/elections/vote-by-mail.shtml",
    register="The last day to register to vote in {election} in New Jersey, online, by mail or in person. There's no "
             "registration on Election Day.",
    mail_summary="Mail-in ballot application due by mail",
    mail="If you vote by mail in {election}, an application sent by mail must reach your county clerk today. In "
         "person, you can apply at the clerk's office until 3 p.m. the day before Election Day. Your ballot must be "
         "postmarked by Election Day and reach your county board of elections within six days, or be dropped in a "
         "drop box by 8 p.m. on Election Day. Any voter can vote by mail; how to apply:",
    early_where="Your county lists the places. Early voting is open 10 a.m. to 8 p.m. Monday to Saturday, and 10 a.m. "
                "to 6 p.m. on Sunday.",
    credit="Dates worked out from New Jersey's election law; more from the New Jersey Division of Elections",
    poll_hours="6 a.m. – 8 p.m.",
    check_url="https://voter.svrs.nj.gov/registration-check",
    check_hint="New Jersey's voter registration check (Division of Elections)",
    where_url="https://voter.svrs.nj.gov/polling-place-search",
    where_hint="New Jersey's polling place search; your county lists its early voting places",
    mail_label="How to apply",
    mail_eligibility="Any registered voter can vote by mail, no reason needed. Your ballot must be postmarked by "
                     "Election Day and reach your county within six days, or be dropped in a drop box by 8 p.m. on "
                     "Election Day.",
    mail_deadline="An application sent by mail must reach your county clerk by ",
    local_office="Your county clerk",
)

WYOMING = Guide(
    name="Wyoming",
    source="Wyoming Secretary of State",
    url="https://sos.wyo.gov/Elections/",
    computed=True,
    registration_url="https://sos.wyo.gov/Elections/State/RegisteringToVote.aspx",
    mail_url="https://sos.wyo.gov/Elections/State/AbsenteeVoting.aspx",
    register="The last day to register by mail or at your county clerk's office for {election} in Wyoming. After it, "
             "you can still register in person at the clerk's office while voting absentee, or at your polling place "
             "on Election Day.",
    mail_summary="Absentee ballot request due",
    mail="If you vote absentee in {election}, ask your county clerk for your ballot by today. Your ballot must reach "
         "the clerk by 7 p.m. on Election Day; one that arrives later isn't counted. Any voter can vote absentee; how "
         "to ask:",
    early_where="Your county clerk's office: vote absentee in person there. The clerk lists the places and hours.",
    credit="Dates worked out from Wyoming's election law; more from the Wyoming Secretary of State",
    poll_hours="7 a.m. – 7 p.m.",
    check_url="https://sos.wyo.gov/Elections/State/RegisteringToVote.aspx",
    check_hint="Wyoming Secretary of State: how to register; your county clerk can check your registration",
    where_url="https://sos.wyo.gov/Elections/State/AbsenteeVoting.aspx",
    where_hint="Every county clerk's website (Wyoming Secretary of State); yours publishes your polling place",
    mail_label="How to ask",
    mail_eligibility="Any registered voter can vote absentee by mail, no reason needed. Your ballot must reach your "
                     "county clerk by 7 p.m. on Election Day.",
    mail_deadline="Ask your county clerk for your ballot by ",
    local_office="Your county clerk",
)

ILLINOIS = Guide(
    name="Illinois",
    source="Illinois State Board of Elections",
    url="https://www.elections.il.gov/",
    computed=True,
    registration_url="https://ova.elections.il.gov/",
    mail_url="https://www.elections.il.gov/",
    register="The last day to register online for {election} in Illinois; by mail, registration closed 12 days "
             "earlier. After it, you can still register and vote in person, with two forms of ID, at your election "
             "authority's office or an early voting site, through Election Day.",
    mail_summary="Vote-by-mail application by mail due",
    mail="If you vote by mail in {election}, an application sent by mail must reach your election authority today. "
         "Your ballot must be postmarked by Election Day and reach the election authority within 14 days after. Any "
         "voter can vote by mail; how to apply:",
    early_where="Your election authority's offices from the first day; its other early voting sites from 15 days "
                "before Election Day. Your election authority lists the places and hours.",
    credit="Dates worked out from Illinois's Election Code; more from the Illinois State Board of Elections",
    poll_hours="6 a.m. – 7 p.m.",
    check_url="https://ova.elections.il.gov/RegistrationLookup.aspx",
    check_hint="Illinois's voter registration lookup (State Board of Elections): your registration and your polling "
               "place",
    where_url="https://ova.elections.il.gov/RegistrationLookup.aspx",
    where_hint="The registration lookup: your polling place; your election authority lists its early voting sites",
    mail_label="How to apply",
    mail_eligibility="Any registered voter can vote by mail, no reason needed. Your ballot must be postmarked by "
                     "Election Day and reach your election authority within 14 days after.",
    mail_deadline="An application sent by mail must reach your election authority by ",
    local_office="Your election authority (county clerk or board of election commissioners)",
)

ALASKA = Guide(
    name="Alaska",
    source="Alaska Division of Elections",
    url="https://www.elections.alaska.gov/",
    computed=True,
    registration_url="https://voterregistration.alaska.gov/",
    mail_url="https://absenteeballotapplication.alaska.gov/",
    register="The last day to register to vote in {election} in Alaska: in person, online, or by mail postmarked "
             "today. There's no registration on Election Day.",
    mail_summary="Absentee ballot application due",
    mail="If you vote absentee by mail in {election}, your application must reach the Division of Elections today. "
         "Your ballot must be postmarked by Election Day and reach the Division within 10 days after. Any voter can "
         "vote absentee; how to apply:",
    early_where="The Division of Elections lists the places and hours. Early voting goes on through Election Day.",
    credit="Dates worked out from Alaska's election law; more from the Alaska Division of Elections",
    poll_hours="7 a.m. – 8 p.m.",
    check_url="https://myvoterinformation.alaska.gov/",
    check_hint="Alaska Division of Elections' My Voter Information: your registration and your polling place",
    where_url="https://www.elections.alaska.gov/voter-information/absentee-and-early-voting/",
    where_hint="Alaska Division of Elections: early and in-person absentee voting places",
    mail_label="How to apply",
    mail_eligibility="Any registered voter can vote absentee by mail, no reason needed. Your ballot must be postmarked "
                     "by Election Day and reach the Division of Elections within 10 days after.",
    mail_deadline="Your application must reach the Division of Elections by ",
    local_office="The Division of Elections' regional office",
)

COLORADO = Guide(
    name="Colorado",
    source="Colorado Secretary of State",
    url="https://www.coloradosos.gov/pubs/elections/main.html",
    computed=True,
    registration_url="https://www.govotecolorado.gov/",
    mail_url="https://www.govotecolorado.gov/",
    register="The last day to register online or by mail for {election} in Colorado and still be mailed a ballot. "
             "After it, you can still register and vote in person at a voter service and polling center, through "
             "Election Day.",
    mail_summary="Mail ballots go out",
    mail="Every active voter in Colorado is mailed a ballot for {election}. Your county clerk must have it back by "
         "7 p.m. on Election Day, by mail or in a drop box or at a voter service and polling center; a postmark "
         "doesn't count. More:",
    early_where="Your county clerk lists the voter service and polling centers and their hours; you can register and "
                "vote there in person.",
    credit="Dates worked out from Colorado's election law; more from the Colorado Secretary of State",
    poll_hours="7 a.m. – 7 p.m.",
    check_url="https://www.govotecolorado.gov/",
    check_hint="GoVoteColorado (Colorado Secretary of State): your registration, your ballot's status and where to vote",
    where_url="https://www.govotecolorado.gov/",
    where_hint="GoVoteColorado: your county's voter service and polling centers and drop boxes",
    mail_label="Track your ballot",
    mail_eligibility="Every active voter is mailed a ballot, from 22 days before Election Day. It must reach your county "
                     "clerk by 7 p.m. on Election Day, by mail, in a drop box or at a voter service and polling center; "
                     "a postmark doesn't count.",
    local_office="Your county clerk",
    polls_text="Voter service and polling centers are open 7 a.m. to 7 p.m. on Election Day; if you're in line at 7, "
               "you can vote.",
)

GUIDES = {
    "TX": TEXAS, "MI": MICHIGAN, "CA": CALIFORNIA, "AZ": ARIZONA, "NV": NEVADA, "GA": GEORGIA, "WI": WISCONSIN,
    "OH": OHIO, "IA": IOWA, "NJ": NEW_JERSEY, "NY": NEW_YORK, "CO": COLORADO, "WY": WYOMING, "IL": ILLINOIS,
    "AK": ALASKA,
}


def first_tuesday_after_first_monday(year: int, month: int) -> dt.date:
    first = dt.date(year, month, 1)
    return first + dt.timedelta(days=(0 - first.weekday()) % 7 + 1)


def michigan(day: dt.date) -> Deadlines | None:
    """The dates of Michigan's statewide election on ``day``, or None when there's none."""
    if day.year % 2 or day.month not in (8, 11) or day != first_tuesday_after_first_monday(day.year, day.month):
        return None
    return Deadlines(
        day, "General Election" if day.month == 11 else "Primary Election",
        register_by=day - dt.timedelta(days=15),
        mail_apply_by=day - dt.timedelta(days=4),
        early_start=day - dt.timedelta(days=10),
        early_end=day - dt.timedelta(days=2),
        state="MI",
    )


ARIZONA_DATES = {
    dt.date(2026, 11, 3): Deadlines(
        dt.date(2026, 11, 3), "General Election", register_by=dt.date(2026, 10, 5),
        early_start=dt.date(2026, 10, 7), early_end=dt.date(2026, 10, 30), state="AZ",
    ),
}


def arizona(day: dt.date) -> Deadlines | None:
    """The dates of Arizona's statewide election on ``day``, as its Secretary of State lists them."""
    return ARIZONA_DATES.get(day)


@dataclass(frozen=True)
class Counts:
    """A state whose deadlines are each a fixed count of days before its general election (the
    module's docstring gives each state's law): None where there's no such date (no application
    to make, early voting through Election Day)."""

    register: int
    mail: int | None
    early_start: int
    early_end: int | None
    every_year: bool = False  # a general election every November, not only in even years

    def on(self, state: str, day: dt.date) -> Deadlines | None:
        """The dates of the general election on ``day``, or None when there's none."""
        if (day.year % 2 and not self.every_year) or day != first_tuesday_after_first_monday(day.year, 11):
            return None

        def before(days: int | None) -> dt.date | None:
            return None if days is None else day - dt.timedelta(days=days)

        return Deadlines(
            day, "General Election", register_by=before(self.register), mail_apply_by=before(self.mail),
            early_start=before(self.early_start), early_end=before(self.early_end), state=state,
        )


COUNTS = {
    "NV": Counts(28, 14, 17, 4),  # mail: register by then to still be mailed a ballot
    "IA": Counts(15, 15, 20, 1),
    "WI": Counts(20, 5, 14, 2),
    "NJ": Counts(21, 7, 10, 2, every_year=True),
    "NY": Counts(10, 10, 10, 2, every_year=True),
    "CO": Counts(8, None, 15, 1),  # every voter is mailed a ballot
    "WY": Counts(15, 1, 28, 1),
    "IL": Counts(16, 5, 40, 1),
    "AK": Counts(30, 10, 15, None),
}


def columbus_day(year: int) -> dt.date:
    """The second Monday of October, a state holiday in Georgia and a legal holiday in Ohio."""
    first = dt.date(year, 10, 1)
    return first + dt.timedelta(days=(0 - first.weekday()) % 7 + 7)


def georgia(day: dt.date) -> Deadlines | None:
    """The dates of Georgia's general election on ``day``, or None when there's none: register by
    the fifth Monday before, apply to vote absentee by the eleventh day before, early voting the
    fourth Monday before (the Tuesday when that's Columbus Day) through the Friday before."""
    if day.year % 2 or day != first_tuesday_after_first_monday(day.year, 11):
        return None
    early = day - dt.timedelta(days=22)
    if early == columbus_day(day.year):
        early += dt.timedelta(days=1)
    return Deadlines(
        day, "General Election",
        register_by=day - dt.timedelta(days=29),
        mail_apply_by=day - dt.timedelta(days=11),
        early_start=early,
        early_end=day - dt.timedelta(days=4),
        state="GA",
    )


def ohio(day: dt.date) -> Deadlines | None:
    """The dates of Ohio's general election on ``day``, or None when there's none: register by
    the thirtieth day before, moved past a Sunday or Columbus Day, early voting from the day after
    through the Sunday before, apply to vote absentee by the seventh day before."""
    if day != first_tuesday_after_first_monday(day.year, 11):
        return None
    register = day - dt.timedelta(days=30)
    while register.weekday() == 6 or register == columbus_day(day.year):
        register += dt.timedelta(days=1)
    return Deadlines(
        day, "General Election",
        register_by=register,
        mail_apply_by=day - dt.timedelta(days=7),
        early_start=register + dt.timedelta(days=1),
        early_end=day - dt.timedelta(days=2),
        state="OH",
    )


RULES: dict[str, Callable[[dt.date], Deadlines | None]] = {
    "MI": michigan, "AZ": arizona, "GA": georgia, "OH": ohio,
    **{state: functools.partial(counts.on, state) for state, counts in COUNTS.items()},
}
PAGES = {"TX": texas.SOURCE, "CA": california.SOURCE}  # the states whose dates are read from their office's page


def computed(state: str | None, day: dt.date) -> Deadlines | None:
    """The state's key dates for the election on ``day``, when they're worked out by rule or entered by hand."""
    rule = RULES.get(state or "")
    return rule(day) if rule else None
