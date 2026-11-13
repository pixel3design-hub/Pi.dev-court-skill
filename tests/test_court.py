"""Tests for the court skill's bookkeeping.

Every test runs the real court.py from a temporary directory, so the gates it asserts are the ones a
model driving the skill actually hits: a dismissed case, missing or stale arithmetic, an evidence-free
case, and the briefs that decide who is allowed to compute.
"""
import contextlib
import io
import json
import os
import shutil
import sys
import tempfile
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.join(HERE, "..", "skills", "court")
sys.path.insert(0, SKILL)
import court  # noqa: E402


class CourtTest(unittest.TestCase):
    """Each test gets an empty .court/ with one evidence-bearing case, so the gates are tested in the
    state the clerk really starts from."""

    def setUp(self):
        self.old = os.getcwd()
        self.tmp = tempfile.mkdtemp()
        os.chdir(self.tmp)
        os.makedirs(".court")
        with open(".court/case.md", "w") as f:
            f.write("Quit my job to sell candles on Etsy full time\n\nI have $8,000 saved.\n")

    def tearDown(self):
        os.chdir(self.old)
        shutil.rmtree(self.tmp)

    def write_maths(self):
        # Pretrial artefact: written after case.md, so it passes init's freshness check.
        os.makedirs(".court/figures", exist_ok=True)
        with open(".court/figures/maths.md", "w") as f:
            f.write("# The arithmetic\n\n| figure | expression | value | why it matters |\n")

    def open_trial(self, *extra):
        self.write_maths()
        court.main(["init", "--case-file", ".court/case.md", "--seed", "7"] + list(extra))
        return court.load_state()

    def write_all(self, state, phase, text):
        for j in court.jobs(state, phase):
            with open(j["output"], "w") as f:
                f.write(text)

    def test_jurors_are_distinct(self):
        jurors = court.load_jurors()
        self.assertEqual(len(jurors), 12)
        self.assertEqual(len({j["name"] for j in jurors}), 12)

    def test_quick_jury_is_six_distinct(self):
        state = self.open_trial("--quick")
        self.assertEqual(len(state["jury"]), 6)
        self.assertEqual(len({j["name"] for j in state["jury"]}), 6)

    def test_briefs_name_their_output_and_the_record(self):
        state = self.open_trial("--jury", "3")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            court.main(["prompts", "jury"])
        j = court.jobs(state, "jury")[0]
        text = open(j["brief"]).read()
        self.assertIn(j["output"], text)
        self.assertIn("VOTE: GUILTY or NOT GUILTY", text)
        self.assertIn(os.path.abspath(os.path.join(state["dir"], "rebuttal", "defense.md")), text)
        # every job is listed so the whole phase can be launched in one parallel message
        for job in court.jobs(state, "jury"):
            self.assertIn(job["brief"], buf.getvalue())
        self.assertIn("ONE message", buf.getvalue())

    def test_figures_runs_before_the_trial(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            court.main(["figures"])
        out = buf.getvalue()
        self.assertIn(os.path.join(".court", "briefs", "figures-maths.md"), out)
        self.assertIn(os.path.join(".court", "figures", "maths.md"), out)
        self.assertFalse(os.path.exists(court.LATEST))
        self.assertIn("Not in the record", open(os.path.join(".court", "briefs", "figures-maths.md")).read())

    def test_init_requires_fresh_arithmetic(self):
        with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
            court.main(["init", "--case-file", ".court/case.md"])
        self.assertFalse(os.path.exists(court.LATEST))
        self.write_maths()
        later = time.time() + 60
        os.utime(".court/case.md", (later, later))
        with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
            court.main(["init", "--case-file", ".court/case.md"])
        self.assertFalse(os.path.exists(court.LATEST))

    def test_trial_starts_at_opening_and_copies_the_arithmetic(self):
        state = self.open_trial("--jury", "3")

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            court.main(["next"])
        self.assertIn("next phase: opening", buf.getvalue())
        self.assertTrue(os.path.exists(os.path.join(state["dir"], "figures", "maths.md")))

    def test_figures_brief_owns_the_arithmetic_and_the_others_are_barred(self):
        state = self.open_trial("--jury", "3")
        with contextlib.redirect_stdout(io.StringIO()):
            court.main(["figures"])
            for phase in ("opening", "judge"):
                court.main(["prompts", phase])
        figures = open(os.path.join(".court", "briefs", "figures-maths.md")).read()
        opening = open(court.jobs(state, "opening")[0]["brief"]).read()
        judge = open(court.jobs(state, "judge")[0]["brief"]).read()
        self.assertIn(os.path.abspath(os.path.join(".court", "figures", "model.py")), figures)
        self.assertIn("Not in the record", figures)
        self.assertIn("exits non-zero", figures)
        self.assertNotIn("Derived numbers", figures)
        maths = os.path.abspath(os.path.join(state["dir"], "figures", "maths.md"))
        for text in (opening, judge):
            self.assertIn(maths, text)
            self.assertIn("Do not compute anything yourself", text)

    def test_render_links_the_arithmetic(self):
        state = self.open_trial("--jury", "3")
        self.write_all(state, "opening", "x")
        self.write_all(state, "rebuttal", "x")
        for j in court.jobs(state, "jury"):
            with open(j["output"], "w") as f:
                f.write("VOTE: GUILTY\nREASON: x\n")
        self.write_all(state, "judge", "## The sentence\nNo.")
        text = court.render(state)
        self.assertIn("The arithmetic:", text)
        self.assertIn(os.path.join(state["dir"], "figures", "maths.md"), text)

    def test_parse_vote_variants(self):
        v = court.parse_vote("VOTE: NOT GUILTY\nREASON: it pays.\nDECIDING FACT: $8,000\nWOULD FLIP IF: no savings")
        self.assertEqual(v["vote"], "NOT GUILTY")
        self.assertEqual(v["flip"], "no savings")
        self.assertEqual(court.parse_vote("**VOTE:** guilty\nREASON: x")["vote"], "GUILTY")
        self.assertIsNone(court.parse_vote("NO VOTE"))

    def test_full_trial_tally_and_render(self):
        state = self.open_trial("--jury", "5")
        self.write_all(state, "opening", "1. point")
        self.write_all(state, "rebuttal", "1. answer")
        votes = ["GUILTY", "GUILTY", "NOT GUILTY", "GUILTY", "NO VOTE"]
        for j, v in zip(court.jobs(state, "jury"), votes):
            with open(j["output"], "w") as f:
                f.write("NO VOTE" if v == "NO VOTE" else "VOTE: %s\nREASON: because | pipes\n" % v)
        t = court.tally(state)
        self.assertEqual((t["verdict"], t["guilty"], t["not_guilty"], t["no_vote"]), ("GUILTY", 3, 1, 1))
        self.assertEqual(court.verdict_line(t), "GUILTY, 3 to 1")
        self.write_all(state, "judge", "## The sentence\nKeep the job for now.")
        text = court.render(state)
        self.assertIn("# The verdict: GUILTY, 3 to 1", text)
        self.assertIn("Quit my job to sell candles", text)
        self.assertIn("because / pipes", text)
        self.assertIn("## The sentence", text)
        self.assertTrue(text.rstrip().endswith(court.CREDIT))

    def test_hung_jury(self):
        state = self.open_trial("--jury", "4")
        for j, v in zip(court.jobs(state, "jury"), ["GUILTY", "NOT GUILTY", "GUILTY", "NOT GUILTY"]):
            with open(j["output"], "w") as f:
                f.write("VOTE: %s\n" % v)
        self.assertEqual(court.verdict_line(court.tally(state)), "HUNG JURY, 2 to 2")

    def test_next_walks_the_phases(self):
        state = self.open_trial("--jury", "3")
        self.assertTrue(court.missing(state, "opening"))
        self.write_all(state, "opening", "x")
        self.assertFalse(court.missing(state, "opening"))
        self.assertTrue(court.missing(state, "rebuttal"))

    def write_case(self, text):
        with open(".court/case.md", "w") as f:
            f.write(text)

    def test_a_case_without_evidence_cannot_open_a_trial(self):
        self.write_case("Quit my job to sell candles\n")
        with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
            court.main(["init", "--case-file", ".court/case.md"])
        self.assertFalse(os.path.exists(court.LATEST))
        # forcing it is explicit, and still opens
        state = self.open_trial("--force")
        self.assertEqual(len(state["jury"]), 12)

    def test_dismiss_blocks_init_until_cleared(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            court.main(["dismiss", "--reason", "thin", "--note", "No costs anywhere."])
        self.assertIn("# Dismissed: not enough evidence to try", buf.getvalue())
        self.assertTrue(os.path.exists(court.DISMISSED))
        self.assertIn("No costs anywhere.", open(court.DISMISSED_DOC).read())
        with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
            court.main(["init", "--case-file", ".court/case.md"])
        self.assertFalse(os.path.exists(court.LATEST))
        with contextlib.redirect_stdout(io.StringIO()):
            court.main(["dismiss", "--clear"])
        state = self.open_trial()
        self.assertEqual(len(state["jury"]), 12)

    def test_dismiss_needs_a_reason_or_clear(self):
        with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
            court.main(["dismiss"])
        self.assertFalse(os.path.exists(court.DISMISSED))


if __name__ == "__main__":
    unittest.main()
