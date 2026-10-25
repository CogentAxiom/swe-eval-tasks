"""Alignment: the exhibit's prose against the data it describes.

A blind read of the package found figures that had drifted from their data: a kit whose results no
longer reproduced after an in-place edit, and pilot counts that outlived a rebuilt corpus. Each check
here ties a statement to the file that settles it, so the next drift fails the suite instead of
waiting for a reader.
"""
import hashlib
import json
import re
import subprocess
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
EXHIBIT = REPO / "exhibit-2-failure-taxonomy"
KITDIR = EXHIBIT / "auditkit"
KIT = EXHIBIT / "portable_kit"
RUN = KITDIR / "runs" / "pilots_2026-10-17"
MUT = KITDIR / "mutation" / "MUTATION_REPORT.md"

# The kit files a model sees or that score it, pinned in KIT_SHA256.json as they were run on 2026-10-17.
# Changing any of them breaks the stored results.
KIT_AS_RUN = ("SYSTEM_PROMPT.md", "rules.json", "fixture_transcript.json", "fixture_truth.json", "validate.py")
KIT_HASHES = KIT / "runs_2026-10-17" / "KIT_SHA256.json"


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def prose(*paths: Path) -> list[tuple[str, str]]:
    return [(p.name, p.read_text(encoding="utf-8")) for p in paths if p.exists()]


def without_entry_notes(doc: str) -> str:
    """The pilot write-up's entry list quotes each coder's note verbatim ('the 25 candidates' there are
    intervals). Those notes are data, not the write-up's own statements, so the count checks skip them."""
    a, b = doc.find("\n## The entries\n"), doc.find("\n## The candidates\n")
    return doc[:a] + doc[b:] if 0 <= a < b else doc


@unittest.skipUnless(KIT.exists(), "portable kit not present")
class TestKitReproduces(unittest.TestCase):
    def test_files_are_the_kit_as_run(self):
        pinned = json.loads(KIT_HASHES.read_text(encoding="utf-8"))
        self.assertEqual(set(pinned), set(KIT_AS_RUN))
        for name, h in pinned.items():
            self.assertEqual(sha(KIT / name), h, f"{name} differs from the kit as run; RESULTS no longer reproduce")

    def test_stored_runs_score_as_published(self):
        runs = sorted((KIT / "runs_2026-10-17").glob("*-run*"))
        self.assertEqual(len(runs), 8)
        for d in runs:
            out = next(d.glob("*model_output*"))
            r = subprocess.run([sys.executable, "-I", str(KIT / "validate.py"), str(out)], capture_output=True, text=True)
            self.assertIn("instruction compliance (quote gate) : 100%", r.stdout, d.name)
            self.assertIn("recall on seeded failures           : 100%", r.stdout, d.name)
            self.assertIn("protections violated                : 0 of 5", r.stdout, d.name)


@unittest.skipUnless((RUN / "claims.json").exists(), "pilot run not present")
class TestPilotFiguresInProse(unittest.TestCase):
    def setUp(self):
        self.claims = len(json.loads((RUN / "claims.json").read_text(encoding="utf-8")))
        self.entries = len(json.loads((RUN / "corpus.json").read_text(encoding="utf-8"))["entries"])
        self.cands = len(json.loads((RUN / "candidates.json").read_text(encoding="utf-8")))
        self.docs = [(name, without_entry_notes(doc)) for name, doc in
                     prose(REPO / "README.md", KITDIR / "README.md", REPO / "portfolio" / "index.html",
                           EXHIBIT / "PILOTS_UNDER_THE_RUBRIC.md", EXHIBIT / "README.md")]

    def test_claim_counts(self):
        for name, doc in self.docs:
            for n in re.findall(r"([\d,]{4,}) claims", doc):
                if n.replace(",", "") != "1859":  # the first build's count, cited once as such
                    self.assertEqual(int(n.replace(",", "")), self.claims, f"{name}: '{n} claims'")

    def test_entry_and_candidate_counts(self):
        for name, doc in self.docs:
            for n in re.findall(r"\*?\*?(\d+) entries (?:are in the corpus|survived)", doc):
                self.assertEqual(int(n), self.entries, f"{name}: '{n} entries'")
            for n in re.findall(r"\*?\*?(\d+) (?:proposed entries|candidates)\b", doc):
                if n != "37":  # the first build's count, cited once as such
                    self.assertEqual(int(n), self.cands, f"{name}: '{n} candidates'")


CORPUS_STATS = KITDIR / "runs" / "corpus_2026-09-24" / "stats.json"


@unittest.skipUnless(CORPUS_STATS.exists(), "corpus build not present")
class TestCorpusSpreadInProse(unittest.TestCase):
    # The per-conversation figures in prose must be the build's.
    def test_spread_figures(self):
        r = json.loads(CORPUS_STATS.read_text(encoding="utf-8"))["rate"]
        docs = prose(REPO / "README.md", KITDIR / "README.md", REPO / "portfolio" / "index.html",
                     EXHIBIT / "README.md", EXHIBIT / "METHOD.md")
        for name, doc in docs:
            for x, y, p in re.findall(r"(\d+) of (?:the )?(\d+) with a reply \((\d+\.\d)%\)", doc):
                self.assertEqual((int(x), int(y), float(p)), (r["affected_conversations"], r["conversations_with_replies"],
                                                              r["affected_pct_of_conversations_with_replies"]), name)
            for v in re.findall(r"mean (\d+\.\d+) across all \d+", doc):
                self.assertEqual(float(v), r["mean_entries_per_conversation"], name)
            for v in re.findall(r"(\d+\.\d+) per affected conversation", doc):
                self.assertEqual(float(v), r["mean_entries_per_affected_conversation"], name)
            for v in re.findall(r"mean (\d+\.\d)% across the \d+ with a reply", doc):
                self.assertEqual(float(v), r["mean_rate_conversations_with_replies_pct"], name)
            for v in re.findall(r"(\d+) of them empty", doc):
                self.assertEqual(int(v), r["empty_conversations"], name)


TREE_PAGE = REPO / "portfolio" / "decision-tree.html"


@unittest.skipUnless(TREE_PAGE.exists(), "decision-tree page not present")
class TestTreePage(unittest.TestCase):
    # The flow-and-definitions page and its Markdown twin are what the generator writes from the codebook and the build.
    def test_generated(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("build_tree_page", KITDIR / "tools" / "build_tree_page.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        cb, st = mod.load()
        self.assertEqual(TREE_PAGE.read_text(encoding="utf-8"), mod.render_html(cb, st), "decision-tree.html is stale: run tools/build_tree_page.py")
        self.assertEqual((EXHIBIT / "WHERE_AN_ERROR_GOES.md").read_text(encoding="utf-8"), mod.render_md(cb, st))


PERR = EXHIBIT / "paper_errors.json"


@unittest.skipUnless(PERR.exists(), "paper error list not present")
class TestPaperErrors(unittest.TestCase):
    # The two papers' error counts in prose are the data file's, and the markdown list is generated from it.
    def setUp(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("paper_errors", KITDIR / "tools" / "paper_errors.py")
        self.mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.mod)
        self.doc = json.loads(PERR.read_text(encoding="utf-8"))
        self.counts = self.mod.counts(self.doc)

    def test_counts_in_prose(self):
        want = (self.counts["sharma"]["errors"], self.counts["syceval"]["errors"])
        docs = prose(REPO / "README.md", EXHIBIT / "README.md", EXHIBIT / "METHOD.md",
                     REPO / "portfolio" / "audit-rubric.html")
        seen = 0
        for name, doc in docs:
            for a, b in re.findall(r"(\d+) errors hold in Sharma et al\. and (\d+) in SycEval", re.sub(r"\s+", " ", doc)):
                self.assertEqual((int(a), int(b)), want, name)
                seen += 1
        self.assertGreaterEqual(seen, 4, "the paper-error counts dropped out of the prose")

    def test_markdown_is_generated(self):
        md = (EXHIBIT / "PAPER_ERRORS.md").read_text(encoding="utf-8")
        self.assertEqual(md, self.mod.render(self.doc), "PAPER_ERRORS.md differs from paper_errors.json: run tools/paper_errors.py")

    def test_no_private_references(self):
        blob = json.dumps(self.doc)
        self.assertIsNone(re.search(r"\b(IL\d{4}|T\d{4}|w\d{3}|Claude-y)\b", blob))


@unittest.skipUnless(MUT.exists(), "mutation report not present")
class TestMutationCountInProse(unittest.TestCase):
    def test_counts(self):
        m = re.search(r"\*\*(\d+) of (\d+) mutants caught", MUT.read_text(encoding="utf-8"))
        caught, total = int(m.group(1)), int(m.group(2))
        for name, doc in prose(REPO / "README.md", KITDIR / "README.md", REPO / "portfolio" / "index.html",
                               EXHIBIT / "README.md"):
            for a, b in re.findall(r"(\d+) of (\d+) mutants", doc):
                self.assertEqual((int(a), int(b)), (caught, total), f"{name}: '{a} of {b} mutants'")


if __name__ == "__main__":
    unittest.main()
