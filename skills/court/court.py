#!/usr/bin/env python3
"""Bookkeeping for the court skill: put an idea on trial in front of a jury of sub-agents.

The skill's orchestrator drives the trial with these commands. Every sub-agent reads a
brief this script writes and writes one output file; this script checks the files, counts the votes
and renders the verdict. All state lives in .court/<run>/ in the current directory.

Pi port maintained by Cristiano Gariboldo (Pixel3Design), social@pixel3design.it. Derived from the
original court skill by Alex Chen: https://github.com/alexyc9381/court-skill

    python3 court.py plan [--jury N | --quick]
    python3 court.py figures
    python3 court.py init --case-file PATH [--jury N | --quick] [--seed S] [--force]
    python3 court.py dismiss --reason thin|scattered --note TEXT   (or: --clear)
    python3 court.py next
    python3 court.py prompts <phase>
    python3 court.py check <phase>
    python3 court.py tally
    python3 court.py render

Phases, in order: opening, rebuttal, jury, judge. The arithmetic (`figures`) runs before the trial, so
its list of missing inputs can drive the questions the clerk asks before opening one.
"""
import argparse
import json
import os
import random
import re
import shutil
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
# Everything the court reads or writes lives under .court/ in the working directory. A trial is one
# timestamped run folder; LATEST is the pointer every command after init follows.
ROOT = ".court"
LATEST = os.path.join(ROOT, "LATEST")
# figures is deliberately absent: the math expert runs before init, see cmd_figures.
PHASES = ["opening", "rebuttal", "jury", "judge"]
PRETRIAL_MATHS = os.path.join(ROOT, "figures", "maths.md")
DEFAULT_JURY = 12
QUICK_JURY = 6
CREDIT = ("_Made with [court](https://github.com/pixel3design-hub/Pi.dev-court-skill) by Cristiano Gariboldo (Pixel3Design), based on [the original court skill](https://github.com/alexyc9381/court-skill)._")
CHARGE = "The case fails as stated: it should not go ahead the way it is described."

# A dismissal leaves a marker as well as a document, so a later init cannot quietly reopen the case.
DISMISSED = os.path.join(ROOT, "DISMISSED")
DISMISSED_DOC = os.path.join(ROOT, "DISMISSED.md")
DISMISS_TITLES = {"thin": "not enough evidence to try", "scattered": "the case needs reorganising"}
NUMBER_RE = re.compile(r"\d")


def has_evidence(case):
    """The floor, not the judgement: a case with no number, cost, date or result anywhere has nothing
    for a jury to weigh, so it cannot open a trial unless the caller forces it."""
    return bool(NUMBER_RE.search(case))


# ---------- state ----------

def load_jurors():
    with open(os.path.join(HERE, "jurors.json")) as f:
        return json.load(f)


def run_dir():
    if not os.path.exists(LATEST):
        sys.exit("court: no trial yet. Run: court.py init --case-file .court/case.md")
    with open(LATEST) as f:
        return f.read().strip()


def load_state(rd=None):
    rd = rd or run_dir()
    with open(os.path.join(rd, "state.json")) as f:
        return json.load(f)


def save_state(state):
    with open(os.path.join(state["dir"], "state.json"), "w") as f:
        json.dump(state, f, indent=2)


def jury_size(args):
    """--quick wins over --jury; otherwise the default jury, bounded by the size of jurors.json."""
    if getattr(args, "quick", False):
        return QUICK_JURY
    n = getattr(args, "jury", None) or DEFAULT_JURY
    if n < 3 or n > 12:
        sys.exit("court: the jury must be 3 to 12 jurors")
    return n


# ---------- jobs ----------

def jobs(state, phase):
    """Every job in a phase: id, brief path, output path.

    Output names derive from the id, so no two agents ever write the same file. `figures` is handled
    here too, called with the pseudo-state {"dir": ROOT}, because the math expert runs before init
    and therefore has no run folder yet.
    """
    d = state["dir"]
    if phase == "figures":
        ids = ["maths"]
    elif phase in ("opening", "rebuttal"):
        ids = ["prosecution", "defense"]
    elif phase == "jury":
        ids = ["juror-%02d" % (i + 1) for i in range(len(state["jury"]))]
    elif phase == "judge":
        ids = ["judge"]
    else:
        sys.exit("court: unknown phase %r (phases: %s)" % (phase, ", ".join(PHASES)))
    out = []
    for jid in ids:
        out.append({
            "id": jid,
            "brief": os.path.abspath(os.path.join(d, "briefs", "%s-%s.md" % (phase, jid))),
            "output": os.path.abspath(os.path.join(d, phase, "%s.md" % jid)),
        })
    return out


def done(job):
    p = job["output"]
    return os.path.exists(p) and os.path.getsize(p) > 0


def missing(state, phase):
    return [j for j in jobs(state, phase) if not done(j)]


# ---------- briefs ----------

def _abs(state, *parts):
    return os.path.abspath(os.path.join(state["dir"], *parts))


def brief_text(state, phase, job):
    """The entire brief a sub-agent gets: it cannot see the conversation, so every path is absolute and
    the answer goes to exactly one file.

    Only the math expert computes. Every other phase gets the derived-numbers clause pointing at the
    arithmetic document, which is what keeps ten agents from inventing ten versions of the same sum.
    """
    case = _abs(state, "case.md")
    head = ("You are one part of a trial run by the court skill. You cannot see the user's conversation: "
            "everything you know is in the files named below. Use only what is in the record. Never invent "
            "facts, numbers, quotes or sources. Where the record is silent, say what is missing and why it "
            "matters. Write your answer to exactly this file and nothing else:\n\n    %s\n\n"
            "The charge: %s\n\nThe case file: %s\n\n" % (job["output"], CHARGE, case))
    if phase == "figures":
        model = _abs(state, "figures", "model.py")
        return head + (
            "You are the court's MATH EXPERT, the only part of this trial allowed to compute. Your job: work "
            "out which calculations the charge needs, then do them in code.\n\n"
            "1. Read the case file and list the numbers a jury would have to derive to judge it. Decide from "
            "this case; there is no checklist. Unit margin, monthly profit, runway, break-even volume, growth "
            "rate, payback, whatever it is.\n"
            "2. Write ONE stdlib-only Python script to %s. Every input comes from the case file, with the "
            "source line beside it in a comment. No network, no invented inputs, no rounding that flatters the "
            "case. It prints one `label: value` line per figure, and exits non-zero naming the input when a "
            "required input is not in the record.\n"
            "3. Run it (python3, or `uv run python` if that is blocked) and paste its real output. If it exits "
            "non-zero, fix the script; never fill the gap.\n"
            "4. Write this file, and only this file:\n\n    %s\n\n"
            "Shape:\n\n"
            "    # The arithmetic\n\n"
            "    | figure | expression | value | why it matters |\n"
            "    |---|---|---|---|\n"
            "    | margin per candle | 18 - 6 | 12 | what one sale is worth before fees |\n\n"
            "    Script: %s\n"
            "    Re-run: python3 %s\n\n"
            "    ## Not in the record\n"
            "    - <input the case does not give, and the figure it blocks>\n\n"
            "Every value in the table is the script's output, never your own arithmetic. If the case needs "
            "no calculation at all, say so in one line and stop: that is a valid answer.\n"
            % (model, job["output"], model, model))
    head += ("Derived numbers: the court's arithmetic is in %s and the script that produced it is %s. Quote "
             "figures from there. If a number you need is not there, say the record does not support it. Do "
             "not compute anything yourself; you may run the script to check it.\n\n"
             % (_abs(state, "figures", "maths.md"), _abs(state, "figures", "model.py")))
    if phase == "opening":
        if job["id"] == "prosecution":
            return head + (
                "You are the PROSECUTOR. Build the strongest honest case that the charge holds.\n\n"
                "- 3 to 5 numbered charges. Each names one concrete way the case fails, the evidence for it from "
                "the case file (quote it), and what it would cost if you are right.\n"
                "- Attack the case as the user actually wrote it, never a weaker version of it.\n"
                "- No insults, no hedging, no praise. 350 words at most.\n")
        return head + (
            "You are the DEFENSE. Build the strongest honest case that the charge does NOT hold: the case "
            "should go ahead as described.\n\n"
            "- 3 to 5 numbered points. Each names one concrete strength, the evidence for it from the case "
            "file (quote it), and why it outweighs the obvious objection.\n"
            "- Defend the case as the user actually wrote it. If a part cannot be defended, concede it in one "
            "line instead of spinning it.\n- 350 words at most.\n")
    if phase == "rebuttal":
        side, other = ("prosecution", "defense") if job["id"] == "prosecution" else ("defense", "prosecution")
        return head + (
            "You are the %s. Read the other side's opening statement:\n\n    %s\n\n"
            "Answer each of its numbered points in order: say whether it survives, and why, in one or two "
            "sentences each. Then name the one point the jury should decide on. 250 words at most.\n"
            % (side.upper(), _abs(state, "opening", other + ".md")))
    if phase == "jury":
        idx = int(job["id"].split("-")[1]) - 1
        juror = state["jury"][idx]
        record = "\n".join("    " + _abs(state, p, s + ".md")
                           for p in ("opening", "rebuttal") for s in ("prosecution", "defense"))
        return head + (
            "You are JUROR %d of %d: %s. %s\n\n"
            "Read the case file and all four statements:\n\n%s\n\n"
            "Decide on your own: you will never see the other jurors. You owe the case nothing. Voting for it "
            "to be kind, or against it to look tough, is contempt of court. Judge it through your own eyes "
            "as described above.\n\n"
            "Write exactly these four lines and nothing else:\n\n"
            "VOTE: GUILTY or NOT GUILTY\n"
            "REASON: one sentence, in your own voice\n"
            "DECIDING FACT: the one fact from the record that decided it\n"
            "WOULD FLIP IF: the one change to the case that would make you vote the other way\n"
            % (idx + 1, len(state["jury"]), juror["name"], juror["lens"], record))
    if phase == "judge":
        return head + (
            "You are the JUDGE. The jury has voted and you cannot overturn the vote. Read the case file, the "
            "four statements in %s and %s, every juror's vote in %s, and the count in %s.\n\n"
            "Write these sections, plainly, for someone who has never seen a courtroom:\n\n"
            "## Charges that stuck\nThe 3 objections the jurors cited most, each in one sentence, with how "
            "many jurors leaned on it.\n\n"
            "## What the defense got right\nThe 2 strongest points in the case's favour.\n\n"
            "## Conditions for acquittal\nThe 3 specific changes that would flip the most votes, built from "
            "the jurors' WOULD FLIP IF lines. Each one is something the user can do this week.\n\n"
            "## The sentence\nOne short paragraph in a judge's voice: what the user should do next.\n\n"
            "250 words at most. Do not repeat the vote count: it is printed above your judgment.\n"
            % (_abs(state, "opening"), _abs(state, "rebuttal"), _abs(state, "jury"),
               _abs(state, "tally.json")))
    raise ValueError(phase)


# ---------- votes ----------

VOTE_RE = re.compile(r"^\s*\**VOTE\**\s*:\s*\**\s*(NOT\s+GUILTY|GUILTY)", re.I | re.M)
FIELD_RE = r"^\s*\**%s\**\s*:\s*(.+)$"


def parse_vote(text):
    """One juror's file -> a vote and its three fields.

    Tolerates markdown bold and checks NOT GUILTY before GUILTY; a file with no VOTE line comes back
    as None so the caller can record NO VOTE instead of guessing.
    """
    m = VOTE_RE.search(text or "")
    if not m:
        return None
    vote = "NOT GUILTY" if "NOT" in m.group(1).upper() else "GUILTY"
    out = {"vote": vote}
    for key, name in (("reason", "REASON"), ("fact", "DECIDING FACT"), ("flip", "WOULD FLIP IF")):
        f = re.search(FIELD_RE % name, text, re.I | re.M)
        out[key] = f.group(1).strip().strip("*").strip() if f else ""
    return out


def tally(state):
    rows = []
    for j, juror in zip(jobs(state, "jury"), state["jury"]):
        text = open(j["output"]).read() if done(j) else ""
        v = parse_vote(text)
        rows.append({"juror": juror["name"], "vote": v["vote"] if v else "NO VOTE",
                     "reason": v["reason"] if v else "", "fact": v["fact"] if v else "",
                     "flip": v["flip"] if v else ""})
    guilty = sum(1 for r in rows if r["vote"] == "GUILTY")
    not_guilty = sum(1 for r in rows if r["vote"] == "NOT GUILTY")
    # A tie is a hung jury: neither side wins by default.
    if guilty > not_guilty:
        verdict = "GUILTY"
    elif not_guilty > guilty:
        verdict = "NOT GUILTY"
    else:
        verdict = "HUNG JURY"
    result = {"verdict": verdict, "guilty": guilty, "not_guilty": not_guilty,
              "no_vote": len(rows) - guilty - not_guilty, "jurors": rows}
    with open(os.path.join(state["dir"], "tally.json"), "w") as f:
        json.dump(result, f, indent=2)
    return result


def verdict_line(t):
    if t["verdict"] == "HUNG JURY":
        return "HUNG JURY, %d to %d" % (t["guilty"], t["not_guilty"])
    big, small = (t["guilty"], t["not_guilty"]) if t["verdict"] == "GUILTY" else (t["not_guilty"], t["guilty"])
    return "%s, %d to %d" % (t["verdict"], big, small)


def render(state):
    t = tally(state)
    case = open(os.path.join(state["dir"], "case.md")).read().strip()
    first = case.splitlines()[0].lstrip("# ").strip() if case else "(empty case)"
    judge = jobs(state, "judge")[0]
    judgment = open(judge["output"]).read().strip() if done(judge) else "_The judge has not ruled yet._"
    lines = ["# The verdict: %s" % verdict_line(t), "",
             "**The case:** %s" % first, "", "**The charge:** %s" % CHARGE, "",
             "## How the jury voted", "", "| Juror | Vote | Why |", "|---|---|---|"]
    for r in t["jurors"]:
        lines.append("| %s | %s | %s |" % (r["juror"], r["vote"], r["reason"].replace("|", "/")))
    lines += ["", judgment, ""]
    # The arithmetic line sits above the credit so a reader can re-run every number in the verdict.
    if os.path.exists(_abs(state, "figures", "maths.md")):
        lines += ["_The arithmetic: %s, recomputable with `python3 %s`._"
                  % (_abs(state, "figures", "maths.md"), _abs(state, "figures", "model.py")), ""]
    lines += ["_The full trial is in %s: the opening statements, the rebuttals and every juror's vote._"
              % os.path.abspath(state["dir"]), "", CREDIT]
    text = "\n".join(lines) + "\n"
    with open(os.path.join(state["dir"], "VERDICT.md"), "w") as f:
        f.write(text)
    return text


# ---------- commands ----------

def cmd_plan(args):
    n = jury_size(args)
    calls = 1 + 2 + 2 + n + 1
    print("jury of %d: 1 math pass, 2 opening statements, 2 rebuttals, %d jurors, 1 judge = %d "
          "sub-agent calls" % (n, n, calls))


def cmd_figures(args):
    """Pre-trial: write the math expert's brief. No trial state, so its missing-inputs list exists
    before the clerk decides whether to ask, dismiss or try."""
    os.makedirs(os.path.join(ROOT, "briefs"), exist_ok=True)
    os.makedirs(os.path.join(ROOT, "figures"), exist_ok=True)
    job = jobs({"dir": ROOT}, "figures")[0]
    with open(job["brief"], "w") as f:
        f.write(brief_text({"dir": ROOT}, "figures", job))
    print("brief: %s" % job["brief"])
    print("output: %s" % job["output"])
    print("Launch one foreground Agent call: \"Read %s and follow it exactly. It is your whole brief.\""
          % job["brief"])
    print("Then read its `Not in the record` list: those are the inputs to ask about before init.")


def cmd_dismiss(args):
    """Record a refusal to try, or clear it. Needs no trial state: a dismissed case never had one."""
    if args.clear:
        for p in (DISMISSED, DISMISSED_DOC):
            if os.path.exists(p):
                os.remove(p)
        print("court: dismissal cleared; a trial can be opened again")
        return
    if not args.reason:
        sys.exit("court: dismiss needs --reason thin|scattered, or --clear")
    os.makedirs(ROOT, exist_ok=True)
    with open(DISMISSED, "w") as f:
        f.write("%s %s\n" % (args.reason, time.strftime("%Y-%m-%dT%H:%M:%S")))
    text = ("# Dismissed: %s\n\n%s\n\n_No trial was opened, so no sub-agents were spent. "
            "Bring the missing evidence, then run this skill again._\n"
            % (DISMISS_TITLES[args.reason], (args.note or "").strip() or "(no detail recorded)"))
    with open(DISMISSED_DOC, "w") as f:
        f.write(text)
    sys.stdout.write(text)


def cmd_init(args):
    """Open a trial: gates first, then the run folder.

    The order matters. The dismissal marker, the case file, the arithmetic and its age, and the
    evidence floor are all checked before anything is written, so a failed init leaves no half-trial
    behind for `next` to pick up.
    """
    n = jury_size(args)
    if os.path.exists(DISMISSED):
        with open(DISMISSED) as f:
            why = f.read().strip()
        sys.exit("court: this case was dismissed (%s). Bring the evidence, then: "
                 "court.py dismiss --clear" % why)
    if not os.path.exists(args.case_file):
        sys.exit("court: case file not found: %s" % args.case_file)
    if not os.path.exists(PRETRIAL_MATHS) or os.path.getsize(PRETRIAL_MATHS) == 0:
        sys.exit("court: no arithmetic yet. Run court.py figures, launch the math expert, then init again")
    if os.path.getmtime(PRETRIAL_MATHS) < os.path.getmtime(args.case_file):
        sys.exit("court: the arithmetic is older than the case file. Re-run: court.py figures")
    case = open(args.case_file).read().strip()
    if not case:
        sys.exit("court: the case file is empty")
    if not args.force and not has_evidence(case):
        sys.exit("court: the case file holds no evidence (no number, cost, date or result) to weigh. "
                 "Dismiss it or ask for the facts; to try it anyway: court.py init ... --force")
    if args.force and not has_evidence(case):
        print("court: forced: the case has no numbers; the jury will weigh that absence")
    seed = args.seed if args.seed is not None else random.randrange(1, 10 ** 6)
    jurors = load_jurors()
    rng = random.Random(seed)
    jury = jurors[:] if n == len(jurors) else rng.sample(jurors, n)
    rd = os.path.join(ROOT, time.strftime("%Y%m%d-%H%M%S"))
    for sub in ("briefs", "opening", "rebuttal", "jury", "judge"):
        os.makedirs(os.path.join(rd, sub), exist_ok=True)
    # Copied, not linked: the run has to stay readable after .court/figures is overwritten for a retrial.
    shutil.copytree(os.path.join(ROOT, "figures"), os.path.join(rd, "figures"))
    with open(os.path.join(rd, "case.md"), "w") as f:
        f.write(case + "\n")
    state = {"dir": rd, "seed": seed, "jury": jury, "created": time.strftime("%Y-%m-%dT%H:%M:%S")}
    save_state(state)
    with open(LATEST, "w") as f:
        f.write(rd)
    print("court: trial opened in %s (jury of %d, seed %d)" % (rd, n, seed))
    print("next: python3 court.py prompts opening")


def cmd_prompts(args):
    """Write a brief per job and list the ones still missing an output."""
    state = load_state()
    todo = missing(state, args.phase)
    # Rewritten every call, so a retried job gets a brief that matches the current record.
    for j in jobs(state, args.phase):
        with open(j["brief"], "w") as f:
            f.write(brief_text(state, args.phase, j))
    if not todo:
        print("court: %s is complete. Run: court.py next" % args.phase)
        return
    for j in todo:
        print("  %s  brief=%s" % (j["id"], j["brief"]))
    print("Launch every job above in ONE message as foreground Agent calls "
          "(run_in_background=false), so they run in parallel. Prompt: "
          "\"Read <brief> and follow it exactly. It is your whole brief.\"")


def cmd_check(args):
    state = load_state()
    todo = missing(state, args.phase)
    if not todo:
        print("court: %s complete" % args.phase)
    for j in todo:
        print("missing: %s -> %s" % (j["id"], j["output"]))


def cmd_next(args):
    """Walk PHASES in order and name the first one with a missing output; that is the driver loop."""
    state = load_state()
    for phase in PHASES:
        if missing(state, phase):
            if phase == "judge":
                t = tally(state)
                print("court: the jury voted %s." % verdict_line(t))
            print("next phase: %s. Run: python3 court.py prompts %s" % (phase, phase))
            return
    print("court: the trial is over. Run: python3 court.py render")


def cmd_tally(args):
    state = load_state()
    t = tally(state)
    print(verdict_line(t))


def cmd_render(args):
    state = load_state()
    sys.stdout.write(render(state))


def main(argv=None):
    p = argparse.ArgumentParser(prog="court.py")
    sub = p.add_subparsers(dest="cmd")
    pl = sub.add_parser("plan")
    pl.add_argument("--jury", type=int)
    pl.add_argument("--quick", action="store_true")
    pi = sub.add_parser("init")
    pi.add_argument("--case-file", required=True)
    pi.add_argument("--jury", type=int)
    pi.add_argument("--quick", action="store_true")
    pi.add_argument("--seed", type=int)
    pi.add_argument("--force", action="store_true")
    pd = sub.add_parser("dismiss")
    pd.add_argument("--reason", choices=sorted(DISMISS_TITLES))
    pd.add_argument("--note", default="")
    pd.add_argument("--clear", action="store_true")
    for name in ("prompts", "check"):
        sp = sub.add_parser(name)
        sp.add_argument("phase", choices=PHASES)
    sub.add_parser("figures")
    for name in ("next", "tally", "render"):
        sub.add_parser(name)
    args = p.parse_args(argv)
    if not args.cmd:
        p.print_help()
        return 1
    # argparse has already validated flags and phase names; each command checks its own state.
    {"plan": cmd_plan, "init": cmd_init, "figures": cmd_figures, "dismiss": cmd_dismiss,
     "prompts": cmd_prompts, "check": cmd_check, "next": cmd_next, "tally": cmd_tally,
     "render": cmd_render}[args.cmd](args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
