// "When to vote" at the top of the ballot: the election's key dates from the Texas SOS
// (ballot.key_dates), each with a calendar file, then a row of buttons: check your
// registration, find where to vote, add every date to a calendar. The mail-ballot deadline
// sits apart, in a closed "Voting by mail?", since most voters can't vote by mail.

import { extLink, h } from "./dom.js";
import { formatDate } from "./format.js";
import { icon } from "./icons.js";
import { STATES } from "./labels.js";

const DAY = { weekday: "short", month: "short", day: "numeric" };
const SHORT_DAY = { month: "short", day: "numeric" };

// Whole days from today (the browser's date) to an ISO date: 0 today, negative once past.
function daysUntil(iso) {
  const [year, month, day] = iso.split("-").map(Number);
  const now = new Date();
  return Math.round((Date.UTC(year, month - 1, day) - Date.UTC(now.getFullYear(), now.getMonth(), now.getDate())) / 86400000);
}

function calendarHref(date, event) {
  return `/api/key-dates.ics?${new URLSearchParams({ date, ...(event ? { event } : {}) })}`;
}

// The calendar icon after a date ``iso``, which adds ``event`` to a calendar, while it's still to come.
function calendarLink(iso, electionDay, event, label) {
  return daysUntil(iso) >= 0
    ? h("a", { class: "cal-link", href: calendarHref(electionDay, event), download: "", title: label, "aria-label": label }, icon("calendar"))
    : null;
}

// A date (and ``extra`` after it), with its calendar link.
function dateWithCalendar(iso, electionDay, event, what, extra = "") {
  return [formatDate(iso, DAY) + extra, calendarLink(iso, electionDay, event, `Add “${what}” to your calendar`)];
}

// The main list: register by, early voting, Election Day. The first that isn't over is the
// next one, in bold with how far off it is.
function dateRows(dates, state) {
  const day = dates.election_day;
  const rows = [
    dates.register_by && {
      label: "Register by", first: dates.register_by, last: dates.register_by,
      value: dateWithCalendar(dates.register_by, day, "register", "Last day to register"),
    },
    (dates.early_voting_start || dates.early_voting_end) && {
      label: "Early voting", first: dates.early_voting_start || dates.early_voting_end, last: dates.early_voting_end || dates.early_voting_start,
      value: [
        dates.early_voting_start ? dateWithCalendar(dates.early_voting_start, day, "early_start", "Early voting begins") : null,
        dates.early_voting_start && dates.early_voting_end ? " – " : null,
        dates.early_voting_end ? dateWithCalendar(dates.early_voting_end, day, "early_end", "Last day of early voting") : null,
      ],
    },
    {
      label: "Election Day", first: day, last: day,
      value: dateWithCalendar(day, day, "election", "Election Day", state.pollHours ? `, ${state.pollHours}` : ""),
    },
  ].filter(Boolean);
  let next = null;
  return rows.map((row) => {
    const [untilFirst, untilLast] = [daysUntil(row.first), daysUntil(row.last)];
    const passed = untilLast < 0;
    const isNext = !passed && !next;
    if (isNext) next = row;
    const when = passed ? "passed"
      : !isNext ? null
      : untilFirst <= 0 ? (row.first === row.last ? "today" : "open now")
      : untilFirst === 1 ? "tomorrow" : `in ${untilFirst} days`;
    return h("div", { class: ["key-date", passed && "passed", isNext && "next"] },
      h("dt", {}, row.label),
      h("dd", {}, row.value, when ? h("span", { class: "when" }, when) : null));
  });
}

function mailVoting(dates, state) {
  const deadline = dates?.mail_apply_by;
  return h("details", { class: "mail-voting" },
    h("summary", {}, "Voting by mail?"),
    h("p", {}, state.mailEligibility, " ", extLink(state.mailApply.url, state.mailApply.label)),
    deadline ? h("p", {},
      "Your application must be received (not postmarked) by ", formatDate(deadline, DAY),
      daysUntil(deadline) < 0 ? " (passed)." : ".",
      calendarLink(deadline, dates.election_day, "mail", "Add the mail-ballot deadline to your calendar")) : null);
}

// The card's contents, or null when Pallot has nothing for the address's state.
export function keyDatesCard(ballot) {
  const state = STATES[ballot.location.state];
  if (!state?.registration) return null;
  const dates = ballot.key_dates;
  const upcoming = dates && [dates.register_by, dates.early_voting_start, dates.early_voting_end, dates.election_day]
    .some((iso) => iso && daysUntil(iso) >= 0);
  const action = (link, iconName) =>
    extLink(link.url, [icon(iconName), link.label], { class: "btn ghost small with-icon", title: link.hint });
  const actions = [
    action(state.registration, "user-check"),
    action(state.countyOffices, "pin"),
    upcoming
      ? h("a", { class: "btn ghost small with-icon", href: calendarHref(dates.election_day), download: "" },
        icon("calendar"), "Add all to calendar")
      : null,
  ];
  const more = state.site ? [" More at ", extLink(state.site.url, state.site.label), "."] : [];
  return [
    h("h2", { id: "key-dates-title" }, "When to vote"),
    dates ? h("dl", { class: "key-date-list" }, dateRows(dates, state)) : null,
    h("div", { class: "button-row key-actions" }, actions),
    mailVoting(dates, state),
    h("p", { class: "fine" },
      dates ? ["Dates from the ", extLink(dates.source_url, "Texas Secretary of State"), ". "] : null,
      "Your county elections office sets where and when you vote.", more),
  ];
}

// "Early voting: Mon, Oct 19 – Fri, Oct 30" for the printed sheet (``short``: "Early voting
// Oct 19 – Oct 30", for the wallet card), or null.
export function earlyVotingText(ballot, { short = false } = {}) {
  const dates = ballot.key_dates;
  if (!dates?.early_voting_start || !dates.early_voting_end) return null;
  const format = short ? SHORT_DAY : DAY;
  return `Early voting${short ? "" : ":"} ${formatDate(dates.early_voting_start, format)} – ${formatDate(dates.early_voting_end, format)}`;
}
