# Paperclip agent

`SKILL.md` is the instruction set for the Paperclip agent that reviews the
greyhound and harness field comparison reports and posts to Slack.

## Installing it

Load it into Paperclip as a skill for the agent that owns this job. The agent
needs, at minimum:

- **read** access to `<project root>/output/` (greyhound report) and
  `<project root>/data/harness/` (harness report)
- **write** access to `output/` (the two notified-state files it maintains)
- a **Slack** tool — MCP gateway or webhook
- **shell** access to run the checks: `venv/bin/python run.py` (greyhounds) and
  `venv/bin/python run.py --harness` (harness). The skill runs them one after the
  other, never together.

## Before first run

Fill in the Configuration table at the top of `SKILL.md`:
project root, Slack channel, and confirm the run command matches how the
project is deployed.

## How it is triggered

A Paperclip routine, configured manually. The agent wakes on schedule, runs both
checks itself, and stops immediately when both exit `0` — so a clean card costs
two commands and no report reading. A run is a few minutes: the greyhound scrape
takes minutes and the harness check (a real browser) about a minute.

Suggested cadence (Australia/Sydney):

- **One full run early**, before the first meeting, to catch missing races and
  meetings while there is time to fix them.
- **Every 15–20 minutes through racing hours.** Scratchings land all day right
  up to jump, and `scratched_still_open` is the finding that actually costs
  money.
- **Nothing overnight.** No racing, no point.

If the token cost of polling a clean card becomes annoying, the alternative is
a systemd timer that runs the check and only creates a Paperclip task on exit
`1` or `2` — the agent then wakes solely when there is something to judge. Not
needed to start.

## The one thing to get right

Findings are not problems. One unapplied scratching shows up as a
`scratched_still_open` critical *and* a `field_size_mismatch` warning for the
same race. Section 3.1 of `SKILL.md` is what keeps the channel readable.

## Harness specifics

- Harness has no boxes; runners are matched on horse name + race number, and
  `wrong_race` / `race_unexpected` are harness-only criticals.
- The harness check exits `2` when the RBHQ feed holds no harness meetings. The
  skill reports that as a feed gap, not as every meeting missing.
- `name_mismatch` (feed drops the last word of some horse names) is a warning, so
  on its own it exits `0` and the agent stays quiet. It is folded into the next
  message that has a critical. If you want it posted on its own, change the exit
  rule in `field_compare/harness_cli.py`.
- The RBHQ feed has been seen answering `401` to calls made within about a minute
  of each other; the skill spaces the two checks and retries a lone 401 once.
