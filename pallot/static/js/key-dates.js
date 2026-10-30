// "When to vote" at the top of the ballot: the election's key dates (ballot.key_dates, from the
// Texas SOS or worked out from the state's election law), each with a calendar file, then a row of buttons: check your
// registration, find where to vote, add every date to a calendar (on one row on a phone, by their
// short labels). The mail-ballot deadline
// sits apart, in a closed "Voting by mail?", since most voters can't vote by mail.

import { extLink, h, phoneWords } from "./dom.js";
import { formatDate } from "./format.js";
import { icon } from "./icons.js";
import { stateInfo } from "./labels.js";
import { sourceNote } from "./view.js";

const DAY = { weekday: "short", month: "short", day: "numeric" };
const SHORT_DAY = { month: "short", day: "numeric" };

// Whole days from today (the browser's date) to an ISO date: 0 today, negative once past.
function daysUntil(iso) {
  const [year, month, day] = iso.split("-").map(Number);
  const now = new Date();
  return Math.round((Date.UTC(year, month - 1, day) - Date.UTC(now.getFullYear(), now.getMonth(), now.getDate())) / 86400000);
}

// The calendar file of the election on ``date`` in ``state`` (Texas's when left out).
function calendarHref(date, state, event) {
  return `/api/key-dates.ics?${new URLSearchParams({ date, ...(state === "TX" ? {} : { state }), ...(event ? { event } : {}) })}`;
}

// The calendar icon after a date ``iso``, which adds ``event`` to a calendar, while it's still to come.
function calendarLink(iso, at, event, label) {
  return daysUntil(iso) >= 0
    ? h("a", { class: "cal-link", href: calendarHref(at.day, at.state, event), download: "", title: label, "aria-label": label }, icon("calendar"))
    : null;
}

// Early voting's last day: with a start and no end, it goes on through Election Day (Alaska's,
// California's).
function earlyEnd(dates) {
  return dates.early_voting_end || (dates.early_voting_start ? dates.election_day : null);
}

// A date (and ``extra`` after it), with its calendar link.
function dateWithCalendar(iso, at, event, what, extra = "") {
  return [formatDate(iso, DAY) + extra, calendarLink(iso, at, event, `Add “${what}” to your calendar`)];
}

// The main list: register by, early voting, Election Day. The first that isn't over is the
// next one, in bold with how far off it is. Once registration's deadline is over in a state that
// still lets voters register (``state.lateRegistration``), the row says how instead of "passed".
// A state with no registration deadline (Vermont) says how to register, undated.
function dateRows(dates, state, at) {
  const day = dates.election_day;
  const rows = [
    dates.register_by && {
      label: "Register by", first: dates.register_by, last: dates.register_by, late: state.lateRegistration,
      value: dateWithCalendar(dates.register_by, at, "register", "Last day to register"),
    },
    !dates.register_by && state.lateRegistration && {
      label: "Register", undated: true, value: extLink(state.lateRegistration.url, state.lateRegistration.label),
    },
    (dates.early_voting_start || dates.early_voting_end) && {
      label: "Early voting", first: dates.early_voting_start || dates.early_voting_end, last: earlyEnd(dates),
      value: [
        dates.early_voting_start ? dateWithCalendar(dates.early_voting_start, at, "early_start", "Early voting begins") : null,
        dates.early_voting_start ? " – " : null,
        dates.early_voting_end ? dateWithCalendar(dates.early_voting_end, at, "early_end", "Last day of early voting") : formatDate(day, DAY),
      ],
    },
    {
      label: "Election Day", first: day, last: day,
      value: dateWithCalendar(day, at, "election", "Election Day", state.pollHours ? `, ${state.pollHours}` : ""),
    },
  ].filter(Boolean);
  let next = null;
  return rows.map((row) => {
    if (row.undated) return h("div", { class: "key-date" }, h("dt", {}, row.label), h("dd", {}, row.value));
    const [untilFirst, untilLast] = [daysUntil(row.first), daysUntil(row.last)];
    const passed = untilLast < 0;
    const late = passed && row.late;
    const isNext = !passed && !next;
    if (isNext) next = row;
    const when = late ? null
      : passed ? "passed"
      : !isNext ? null
      : untilFirst <= 0 ? (row.first === row.last ? "today" : "open now")
      : untilFirst === 1 ? "tomorrow" : `in ${untilFirst} days`;
    return h("div", { class: ["key-date", passed && "passed", isNext && "next"] },
      h("dt", {}, row.label),
      h("dd", {}, row.value, when ? h("span", { class: "when" }, when) : null,
        late ? h("span", { class: "late" }, extLink(late.url, late.label)) : null));
  });
}

function mailVoting(dates, state, at) {
  const deadline = dates?.mail_apply_by;
  return h("details", { class: "mail-voting" },
    h("summary", {}, "Voting by mail?"),
    h("p", {}, state.mailEligibility, " ", extLink(state.mailApply.url, state.mailApply.label)),
    deadline ? h("p", {},
      state.mailDeadline || "Your application must be received (not postmarked) by ", formatDate(deadline, DAY),
      daysUntil(deadline) < 0 ? " (passed)." : ".",
      calendarLink(deadline, at, "mail", "Add the mail-ballot deadline to your calendar")) : null);
}

// The card's contents, or null when Pallot has nothing for the address's state. A state with only
// its election office's site gets the link: its registration, dates and polling places are there.
export function keyDatesCard(ballot) {
  const state = stateInfo(ballot);
  if (!state) return null;
  if (!state.registration) {
    return [
      h("h2", { id: "key-dates-title" }, "When to vote"),
      h("p", {}, "Check your registration, the key dates and where to vote with the state's election office: ",
        extLink(state.site.url, state.site.label), "."),
    ];
  }
  const dates = ballot.key_dates;
  const at = dates && { day: dates.election_day, state: ballot.location.state };
  const upcoming = dates && [dates.register_by, dates.early_voting_start, dates.early_voting_end, dates.election_day]
    .some((iso) => iso && daysUntil(iso) >= 0);
  const action = (link, iconName) =>
    extLink(link.url, [icon(iconName), phoneWords(link.label, link.short || link.label)], { class: "btn ghost small with-icon", title: link.hint });
  const actions = [
    action(state.registration, "user-check"),
    action(state.countyOffices, "pin"),
    upcoming
      ? h("a", { class: "btn ghost small with-icon", href: calendarHref(at.day, at.state), download: "" },
        icon("calendar"), phoneWords("Add all to calendar", "Calendar"))
      : null,
  ];
  const more = state.site ? [" More at ", extLink(state.site.url, state.site.label), "."] : [];
  const credit = !dates ? null
    : dates.computed ? ["Dates worked out from the state's election law; the ", extLink(dates.source_url, dates.source), " explains it. "]
    : ["Dates from the ", extLink(dates.source_url, dates.source), ". "];
  return [
    h("h2", { id: "key-dates-title" }, "When to vote"),
    dates ? h("dl", { class: "key-date-list" }, dateRows(dates, state, at)) : null,
    h("div", { class: "button-row key-actions" }, actions),
    mailVoting(dates, state, at),
    sourceNote(credit, `${state.localOffice || "Your county elections office"} sets where and when you vote.`, more),
  ];
}

// The card in a line, for a phone (ballot-top.js): "Early voting Oct 19–30 · Election Day Nov 3",
// early voting only until it's over.
export function keyDatesSummary(ballot) {
  const dates = ballot.key_dates;
  if (!dates) return "Registration and where to vote";
  const start = dates.early_voting_start || dates.early_voting_end;
  const end = earlyEnd(dates) || start;
  const early = end && daysUntil(end) >= 0
    ? !dates.early_voting_end ? `Early voting from ${formatDate(start, SHORT_DAY)}`
      : `Early voting ${formatDate(start, SHORT_DAY)}${start === end ? ""
        : start.slice(0, 7) === end.slice(0, 7) ? `–${Number(end.slice(8))}` : ` – ${formatDate(end, SHORT_DAY)}`}`
    : null;
  return [early, `Election Day ${formatDate(dates.election_day, SHORT_DAY)}`].filter(Boolean).join(" · ");
}

// "Early voting: Mon, Oct 19 – Fri, Oct 30" for the printed sheet (``short``: "Early voting
// Oct 19 – Oct 30", for the wallet card), or null.
export function earlyVotingText(ballot, { short = false } = {}) {
  const dates = ballot.key_dates;
  if (!dates?.early_voting_start) return null;
  const format = short ? SHORT_DAY : DAY;
  return `Early voting${short ? "" : ":"} ${formatDate(dates.early_voting_start, format)} – ${formatDate(earlyEnd(dates), format)}`;
}
