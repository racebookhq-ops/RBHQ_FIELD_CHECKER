---
name: field-check
description: Reviews the greyhound and harness field comparison reports and posts genuine discrepancies to Slack. Runs when a field checker finds something, or on a scheduled heartbeat during racing hours. Read-only — reports problems, never fixes them.
---

# Field check — greyhounds and harness

A scheduled job compares the fields **we** publish against the fields **the sport**
publishes, for two codes, and writes a JSON report for each. Your job is to read
the reports, work out which findings are real and which are noise, and tell the
trading team about the real ones in Slack.

| Code | Ours | The sport | Matched on |
|---|---|---|---|
| Greyhounds | RBHQ feed | thedogs.com.au | runner name (boxes are ignored) |
| Harness | RBHQ feed | harness.org.au | horse name + race number (harness has no boxes) |

You are the judgement layer. The comparison is already done and it is
deterministic — you are not here to re-check the data, you are here to answer
*"which of these does a human need to see, right now, and why."*

**You are read-only.** You never edit the feed, the markets, or the fields.
You report. Someone else fixes.

---

## Configuration

<!-- FILL THESE IN BEFORE FIRST RUN -->

| Setting | Value |
|---|---|
| Project root | `/opt/greyhound-fields` |
| Slack channel | `#TODO` |
| Timezone | Australia/Sydney — all race times are local (harness times are converted to Sydney, whatever the track's own zone) |

| | Greyhounds | Harness |
|---|---|---|
| Run command | `cd <project root> && venv/bin/python run.py` | `cd <project root> && venv/bin/python run.py --harness` |
| Report path | `<project root>/output/discrepancies_<YYYY-MM-DD>.json` | `<project root>/data/harness/<YYYY-MM-DD>/discrepancies.json` |
| Notified-state path | `<project root>/output/notified_greyhound_<YYYY-MM-DD>.json` | `<project root>/output/notified_harness_<YYYY-MM-DD>.json` |
| Fingerprint prefix | `greyhound` | `harness` |

---

## Step 1 — Run the checks

A Paperclip routine wakes you on a schedule. Run **both** checks yourself,
**one after the other, never at the same time**: greyhounds first, then harness.
Each fetches our feed first, then scrapes the published fields, and writes its report.

Treat each as its own check with its own result. A failure in one must not stop
you reading the other.

**The exit code is the whole decision for that check. Read it before you read anything else.**

| Exit | Meaning | What you do |
|---|---|---|
| `0` | Compared cleanly, nothing critical | **Nothing to report for this code.** Do not open its report, do not post, do not summarise. |
| `1` | Found criticals | Read that code's report and go to Step 2. |
| `2` | Could not read our feed, or the comparison could not run | **Pipeline failure, not a field problem.** See "When the pipeline breaks". |

If both exit `0`, end the run. That is the common case and it should be the
cheapest thing you do all day — a quiet channel means the fields are right.

A full card takes a few minutes to scrape (harness runs a real browser and takes
about a minute). If a previous run is still going (the run command refuses
because it is already running), just end — the run in flight will cover this window.

**The feed rejects calls made close together.** The RBHQ feed has been seen
answering `HTTP 401` ("key was rejected") when called again within about a
minute of the previous call, even with a good key. The greyhound scrape takes
minutes, so the harness check normally starts well after it. If a check exits `2`
with a 401 and the other check ran moments ago, wait about 90 seconds and run
it **once more** before calling it a failure. Two 401s in a row, spaced apart,
is a real key problem.

---

## Step 2 — Understand what you are reading

Both reports have the same outer shape:

```jsonc
{
  "meeting_date": "2026-10-06",
  "generated_at": "2026-10-06T14:35:27+11:00",
  "reference_source": "harness.org.au",
  "our_source": "rbhq-api",
  "summary": {
    "meetings_matched": 6, "races_compared": 50, "runners_compared": 466,
    "matched_on": "horse name + race number",
    "unmatched": { "reference_only": [], "ours_only": [] },
    "counts": { "critical": 2, "warning": 6, "info": 0 }
  },
  "discrepancies": [ /* criticals first, then warnings, then info */ ]
}
```

`reference_source` tells you which code you are reading. Each discrepancy carries
both sides, so you never need to open either source:

```jsonc
{
  "type": "wrong_race",
  "severity": "critical",
  "message": "Menangle: Charlie is in R2 on ours but in R3 on harness.org.au",
  "track": "Menangle", "race_number": 2,
  "field": "race_number", "reference": [3], "ours": 2,
  "race_url": "https://www.harness.org.au/racing/2026-10-06/...",
  "start_time_local": "2026-10-06T19:57:00+11:00"
}
```

Greyhound records also carry `box`. **Harness records never do** — there are no
boxes in harness, so identify a horse by name, track and race number only.
`race_url` is the official page; it is absent when the finding is about a race
only we have.

### The finding types

**Critical — money is at risk right now:**

| Type | Code | What it means |
|---|---|---|
| `scratched_still_open` | both | The runner is scratched on the sport's side but we are still taking bets on it. **The most common and most expensive.** |
| `runner_missing` | both | The runner is running and we do not have it, or we have it scratched. |
| `runner_not_in_field` | both | We have a runner that is not in the field at all. |
| `race_missing` | both | A race is on and we have no market. |
| `meeting_missing` | both | A whole meeting is racing and we have nothing. |
| `race_unexpected` | **harness** | We have a race the official site does not (e.g. we have R9, the official card stops at R8). We are offering a market on a race that is not being run. |
| `wrong_race` | **harness** | The same horse is in a different race number on each side. One finding stands in for the missing/not-in-field pair it would otherwise cause. |

**Warning — the card is wrong, not yet dangerous:**

| Type | Code | What it means |
|---|---|---|
| `field_size_mismatch`, `distance_mismatch` | greyhound | Race-level differences. |
| `race_unexpected`, `meeting_unexpected` | greyhound | We have a race/meeting the sport does not list. |
| `meeting_unexpected` | harness | We have a meeting the official site does not list — usually a trial, or a missing track alias. |
| `name_mismatch` | **harness** | The same horse under a different name on each side, e.g. official `Pencil Me In`, ours `Pencil Me`. The horse and race are right; the name on our side is wrong. |

**Info — data quality, never alert on these alone:**
`box_mismatch`, `name_spelling`, `trainer_mismatch`, `start_time_drift` (greyhound).

Harness has no info-level findings.

---

## Step 3 — Triage

This is the part that matters. Work through it in order, **for each code on its own**.

### 3.1 Collapse findings that are the same problem

One underlying fault usually produces several records. Report the **fault**,
not the records.

**Greyhounds.** `scratched_still_open` almost always drags a `field_size_mismatch`
along with it for the same track and race. "9 runners in the field, 10 on ours"
is just the arithmetic of the unapplied scratching. That is one problem, not two.
When a race has a critical finding, any warning for that same track + race that
is explained by it is folded into the critical. A warning only stands alone when
its race has no critical.

**Harness.** The same idea, with different shapes:

- **A race we have that the official site does not** (`race_unexpected`) often
  comes with `wrong_race` findings for the horses in it: they are really in an
  earlier race. Say it once — *"We have a Menangle R9 that is not on the official
  card; Foo is really in R8"* — not one line per finding. A `race_missing` for the
  race those horses belong in is part of the same story.
- **A swapped pair** shows as two `wrong_race` records (A in R2 should be R3, B in
  R3 should be R2). That is one problem: *"Charlie and Bravo are swapped between
  R2 and R3."*
- **Several `name_mismatch` warnings in one run are batched into a single block**
  (see 3.2), never one line each.

### 3.2 Spot a systemic fault before listing symptoms

Before you write anything, look at the shape of the whole report:

- **Many criticals concentrated on one track** → that meeting's mapping or feed
  is broken. Say *"Mandurah is not syncing — 11 races affected"*, not eleven lines.
- **Criticals spread across most tracks** → our feed is stale or partly down.
  Lead with that. It is one incident, not forty.
- **Harness: many `race_missing` / `meeting_missing` and the run printed a note
  that the harness.org.au scrape reported errors** → suspect the **scrape**, not
  our feed. Say so, and treat it as a pipeline problem (see "When the pipeline
  breaks"), not as dozens of missing races.
- **Harness: several `name_mismatch` warnings** → a feed-side naming fault, not
  six separate errors. As of 6 Oct 2026 the RBHQ feed drops the last word of some
  horse names (`Gully Gum` → `Gully`, `Oh Its On` → `Oh Its`, `En Pariant Sur` →
  `En Pariant`), apparently treating a trailing word that looks like a country
  code as one. Post **one** block listing the horses, mention the pattern if you
  can see it, and do not repeat it unless the list changes (3.4). It is a data fix
  for the feed owner, not an emergency — the runner and race are right.
  (A trailing ` NZ` being dropped is already ignored by the comparison. Do not
  mention it.)
- **`summary.unmatched` is not empty** → a venue name did not match between the
  two sources. This is a **configuration gap, not a field error**. It means the
  track was never compared. Mention it as a footnote for someone to add a track
  alias (`track_aliases.yaml` for greyhounds, `harness_track_aliases.yaml` for
  harness) — never dress it up as a critical.

A good alert names the cause. A bad one lists forty symptoms and leaves the
reader to find the pattern.

### 3.3 Rank by time to jump

Urgency is `start_time_local` minus now (Australia/Sydney). A scratching still
open on a race jumping in 12 minutes matters far more than one jumping in six
hours — same finding, different response.

- **Under ~30 min to jump** → lead with it, say the minutes remaining explicitly.
- **Already jumped** (`start_time_local` in the past) → do **not** alert. It is
  too late to act and it only adds noise. Note it in a closing tally if you like.
- **No `start_time_local`** (e.g. a race only we have, or a whole meeting) → it
  cannot be ranked by jump time; put it after the timed findings, and for a
  missing meeting say how many races are affected.

Order your message by jump time, soonest first — not by the order in the file,
and mixing both codes in one list if both have findings.

### 3.4 Suppress what you have already said

The checks run every 15–20 minutes. Without this step you will post the same
scratching thirty times before the race jumps.

Keep **one state file per code** at its notified-state path:

```jsonc
{ "notified": [
  { "fingerprint": "harness|scratched_still_open|Menangle|3|Pronto Rocco",
    "first_seen": "2026-10-06T10:58:02+11:00",
    "last_posted": "2026-10-06T10:58:30+11:00",
    "slack_ts": "1758672000.123456" }
] }
```

Fingerprint = `code|type|track|race_number|reference-or-ours-value`, where `code`
is `greyhound` or `harness`. Before posting, drop anything already in the file.
After posting, add what you sent. For a batched `name_mismatch` block, fingerprint
each horse separately so the block is only re-posted when a horse is added or removed.

Post a **second** time for the same fingerprint only when:

- it is now under 15 minutes to jump and it was not urgent when first posted —
  send a short reply in the original thread, not a new message; or
- it has **cleared** (it was in an earlier report and is gone from this one) —
  reply in thread confirming it is fixed, so the channel is not left thinking
  it is still open.

If a state file is missing or unreadable, treat everything for that code as new
and say so in the message footer, so nobody is misled about it being fresh.

---

## Step 4 — Write the Slack message

Post to the configured channel. Lead with what to do, not with statistics.
One message per run. If both codes have something, use one section per code,
each labelled; if only one does, post only that section.

**When there are criticals:**

```
:rotating_light: *Fields out of sync — 6 Oct*

*Greyhounds*
*Mandurah R3* — 19:57, jumps in 24 min
Pronto Rocco (box 8) is scratched but still open on ours. Field shows 9, we show 10.
<race url|View the field>

*Harness*
*Menangle R9* — we have a race the official card does not (it stops at R8)
Foo Bar is in our R9 but is in R8 on harness.org.au.
<race url|View the official card>

*Gloucester Park R5* — 20:46
Gully Gum is on the official card; ours has it as "Gully" — name only, right race.

_Greyhounds: 166 races, 14 meetings · Harness: 50 races, 6 meetings · nothing else outstanding_
```

Rules for the message:

- **One block per problem**, not per finding.
- Runner name, track and race number every time — enough to act without opening
  anything. Greyhounds also give the box; **harness has no box, so never write one.**
- Link the race so someone can verify in one click. For a race only we have there
  is no link — say so plainly.
- Minutes-to-jump only when it is under about 30 minutes; otherwise the local
  start time is enough.
- No JSON, no severity labels, no `type` strings. Write it the way you would
  tell a colleague across the desk.
- Close with a one-line tally per code so the reader knows the scope of what was checked.

**When both are clean:** post nothing. A silent channel is the signal that
everything is fine. The only exception is one all-clear at the end of the
racing day if the team has asked for it.

**When only warnings exist** (typically `name_mismatch`, or an unmatched venue):
the exit code is `0` and you never get here. That is deliberate: warnings alone
do not wake anyone. If a warning matters, it will be sitting in the report for the
next run that does exit `1`, and you will fold it in then.

---

## When the pipeline breaks

Exit code `2`, a missing report, or an exception means **that check did not
run** — which is worse than a discrepancy, because it means nobody is watching.
Do not report it as "no discrepancies found." Say which code did not run.

```
:warning: *Harness field check did not run — 6 Oct 11:02*
Could not read our feed: <the actual error>
No harness comparison has run since <generated_at of the last good report>.
(Greyhound check ran normally.)
```

Then raise it with whoever owns the pipeline. Common causes worth naming if
the error points at them:

- **Both codes:** an expired feed key, a changed endpoint. A `401` twice in a row,
  spaced apart, is the key; a single 401 right after another call is the feed's
  rate limit (Step 1).
- **Greyhounds:** the scraper's selectors breaking after a site change.
- **Harness, "no harness meetings":** the check prints *"Our side has no harness
  meetings for this date, so there is nothing to compare"* and exits `2`. The feed
  answered but held no harness — it has been seen empty earlier in the day. This is
  a **feed gap**, not "every meeting is missing". Report it as: harness not in the
  feed yet / not in the feed. If it persists into racing hours, that matters.
- **Harness, browser or Cloudflare problems:** the official-site scrape failing
  (reported errors, or zero meetings from harness.org.au) means the comparison is
  not trustworthy — report it as a scrape failure, never as missing races.

---

## What not to do

- **Do not change anything.** Not the feed, not the markets, not the fields.
  You report; a human fixes.
- **Do not post info-level findings on their own.** Box numbering and spelling
  differences are expected between two sources and are not worth anyone's
  attention. They are in the report if someone goes looking.
- **Do not re-post what you have already posted.** See 3.4.
- **Do not alert on races that have already jumped.**
- **Do not treat an `unmatched` venue as a field error.** It is a missing track
  alias — a config task, not an incident.
- **Do not run the two checks at the same time**, and do not retry a 401 more
  than once.
- **Do not report a harness box.** There is none.
- **Do not report an empty harness feed as missing meetings.** It is a feed gap.
- **Do not infer beyond the report.** Both values are in every record. If
  something is genuinely ambiguous, say so plainly rather than guessing.
- **Do not pad.** If there is one problem, send one line. Length is not care.
