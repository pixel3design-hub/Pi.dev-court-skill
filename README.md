# The court skill

When your model agrees with everything you say, put your idea on trial in front of a jury of 12
sub-agents. One [Pi](https://pi.dev) skill. Free, MIT, no signup, no API key, nothing to connect.

Made by **Alex Chen** ([@nocodealex](https://instagram.com/nocodealex)), an AI creator who builds free agent skills. Step-by-step guide at [chen.media](https://chen.media/guides/put-your-idea-on-trial-in-front-of-a-jury-of-12-claudes-how-to-install-the-free-skill).

Ask the model "is this a good idea?" and it usually says yes. `/skill:court` takes the same idea and
runs a trial instead:

1. A **prosecutor** sub-agent builds the strongest honest case that your idea fails as described.
2. A **defense** sub-agent builds the strongest honest case that it works.
3. Each side answers the other's points.
4. **12 jurors** read the record and vote GUILTY or NOT GUILTY on their own. Each one sees the case
   through different eyes: an accountant, a first-time customer, a competitor, a retired judge, a
   teenager, an engineer, a small-business owner, a statistician, a parent, an investor, a designer
   and a lawyer. No juror sees another's vote, so nobody can just go along with the room.
5. A **judge** sub-agent reads the verdict, the charges that stuck, what the defense got right, and the
   conditions for acquittal: the specific changes that would flip the most votes.

What comes back is `VERDICT.md`: the vote (for example GUILTY, 9 to 3), every juror's one-line reason,
and what to change before you try again.

**It never touches your files.** Everything is written inside `.court/` in the folder you run it in.

## Install

Paste this into Pi:

```
https://github.com/alexyc9381/court-skill
Install this skill for Pi, then confirm /skill:court works.
```

Or as a Pi package:

```bash
pi install git:github.com/alexyc9381/court-skill
```

Or copy the skill folder into any Pi skill directory:

```bash
git clone https://github.com/alexyc9381/court-skill
cp -r court-skill/skills/court ~/.agents/skills/
```

Run `/reload` (or restart Pi) and it shows up as `/skill:court`.

The jury is made of Pi sub-agents, so the `@tintinweb/pi-subagents` extension has to be installed
(`pi install npm:@tintinweb/pi-subagents`). Without it there is no `Agent` tool and no trial.

## Use

```
/skill:court Quit my job to sell candles on Etsy full time. I have $8,000 saved and 40 sales so far.
```

| flag | meaning |
| --- | --- |
| `--jury N` | 3 to 12 jurors. Default 12. |
| `--quick` | 6 jurors. |
| `--seed S` | Fixes which jurors sit on a smaller jury. |

A full trial is 17 sub-agent calls (2 openings, 2 rebuttals, 12 jurors, 1 judge); `--quick` is 11.
They run in parallel, one round per phase, so a full trial is 4 blocking rounds: the wall clock is
about the slowest agent in each round, not the sum of 17.
Every sub-agent counts toward your model usage, so start with `--quick` if you are near your limit.

See `examples/candles/VERDICT.md` for a real (3-juror) trial: "Quit my job as a nurse to sell
handmade candles on Etsy full time" came back GUILTY, 3 to 0, with the conditions that would flip it.

## How it works

`skills/court/court.py` does the bookkeeping: it opens the trial, writes one brief per sub-agent, checks
that every output exists, counts the votes and renders the verdict. The orchestrating agent only
orchestrates: it never argues a side, never votes and never edits the verdict. The jurors are in `skills/court/jurors.json`.

```bash
uv run python -m unittest discover -s tests
```

## Making a video or post about this?

Go ahead. Credit it like this, in your caption or description:

```text
court skill by Alex Chen (@nocodealex): github.com/alexyc9381/court-skill
```

Tag [@nocodealex](https://instagram.com/nocodealex) so I can see it. Every verdict the skill writes already ends with the same credit, so leave it in the shot.

Writing about it or citing it in a paper? Use **Cite this repository** in the sidebar on GitHub.

## Uninstall

```bash
pi remove git:github.com/alexyc9381/court-skill
```

Not made by Anthropic or Pi. The jury is made of language models, so treat the verdict as a structured
second opinion, not legal, financial or professional advice.
