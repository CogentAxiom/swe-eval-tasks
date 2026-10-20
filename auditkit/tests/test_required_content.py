"""Required content: the author's rulings on the exhibit, enforced as a gate.

An agent revising the exhibit once deleted the paragraph on what the one-user limit does not mean,
logging it as "unsupported". A rule an agent reads does not reliably execute; a test that fails
does. Each check below is a ruling of the author's, and any rewrite that drops one fails the suite.
"""
import re
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
README = REPO / "docs" / "audit_rubric" / "README.md"
METHOD = REPO / "docs" / "audit_rubric" / "METHOD.md"
PAGE = REPO / "portfolio" / "audit-rubric.html"


def text(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def section(doc: str, heading_re: str) -> str:
    """The text from a heading to the next heading of the same or higher level."""
    m = re.search(heading_re, doc, re.M)
    if not m:
        return ""
    level = len(m.group(1))
    rest = doc[m.end():]
    n = re.search(r"^#{1,%d} " % level, rest, re.M)
    return rest[: n.start()] if n else rest


@unittest.skipUnless(README.exists() and METHOD.exists(), "exhibit docs not present")
class TestRequiredContent(unittest.TestCase):
    def test_scope_logic_present(self):
        # The one-user limit bounds rates, never validity: in the README, METHOD.md and the page.
        self.assertIn("What the scope does not mean", text(README))
        self.assertIn("What the one-user limit does not mean", text(METHOD))
        for doc in (text(README), text(METHOD)):
            self.assertRegex(doc, r"survive n\s*=\s*1")
        if PAGE.exists():
            self.assertIn("What the scope does not mean", text(PAGE))

    def test_limits_name_all_three_instruments(self):
        # Wherever this audit's limits are stated, the same limits are stated for Sharma et al. and SycEval.
        readme_limits = section(text(README), r"^(##) Limits")
        method_limits = section(text(METHOD), r"^(##) 11\. Limits")
        for name, block in (("README Limits", readme_limits), ("METHOD section 11", method_limits)):
            self.assertTrue(block, f"{name} missing")
            for inst in ("Sharma", "SycEval"):
                self.assertIn(inst, block, f"{name} states this audit's limits without {inst}'s")

    def test_symmetric_table_and_note(self):
        m = text(METHOD)
        self.assertIn("The same standard, applied to every instrument", m)
        self.assertIn("How this section came to be", m)
        self.assertIn("Where the challenges came from", m)
        self.assertIn("Did the challenger claim authority?", m)
        if PAGE.exists():
            p = text(PAGE)
            self.assertIn("The same standard, applied to every instrument", p)
            self.assertIn("How that section came to be", p)

    def test_each_limit_stated_for_all_three(self):
        # Every question asked of this audit is asked of both papers: in the README's Limits, and as a
        # row of the page's comparison table. A limit stated for this audit alone fails here.
        readme_limits = section(text(README), r"^(##) Limits")
        bullets = [b for b in re.split(r"\n- ", readme_limits) if b.lstrip().startswith("**")]
        self.assertGreaterEqual(len(bullets), 6, "README Limits lost its per-question bullets")
        for b in bullets:
            for inst in ("This audit", "Sharma", "SycEval"):
                self.assertIn(inst, b, f"README Limits bullet states a limit without {inst}: {b[:80]!r}")
        if PAGE.exists():
            p = text(PAGE)
            for row in ("Who ran it", "What was sampled", "Where the challenges came from", "Did the challenger claim authority?",
                        "counted as a failure?", "G9: a judge outside the judged set", "error rate measured?",
                        "Independently replicated?", "released for outside review?", "What an outside reader can check", "Conflicts"):
                self.assertIn(row, p, f"page comparison table lost the row {row!r}")

    def test_relationships_disclosed(self):
        # His ruling (2026-10-19): a relationship is a fact to disclose, for every instrument, his own included.
        docs = [text(README), text(METHOD)] + ([text(PAGE)] if PAGE.exists() else [])
        for doc in (re.sub(r"\s+", " ", d) for d in docs):
            self.assertIn("Virtue AI", doc)
            self.assertIn("Google DeepMind, a competitor of the audited vendor", doc)
            self.assertIn("All authors are at Anthropic", doc)

    def test_paper_errors_listed(self):
        # His ruling (2026-10-19): the two published papers' errors are listed, apart from this audit, which states its limits.
        perr = REPO / "docs" / "audit_rubric" / "PAPER_ERRORS.md"
        self.assertTrue(perr.exists(), "PAPER_ERRORS.md missing")
        md = text(perr)
        for h in ("## Sharma et al. 2023", "## SycEval 2025"):
            self.assertIn(h, md)
        self.assertIn("### Errors in the two published papers", text(METHOD))
        if PAGE.exists():
            self.assertIn("Errors in the two published papers", text(PAGE))

    def test_flow_and_definitions_page(self):
        # His ruling (2026-10-19): the rubric's flow and definitions go in, readable on one page.
        page = REPO / "portfolio" / "decision-tree.html"
        self.assertTrue(page.exists(), "decision-tree.html missing")
        t = text(page)
        for s in ("Not an error: never counted", "<h3>Sycophancy</h3>", "<h3>Hallucination</h3>", "Every type of error, defined"):
            self.assertIn(s, t)
        self.assertEqual(t.count('<article class="def"'), 26)
        self.assertIn("decision-tree.html", text(REPO / "portfolio" / "index.html"))

    def test_g9_defined_in_words(self):
        # G9 is named in every comparison, so its two prongs are defined in words wherever it is.
        docs = [text(README), text(METHOD)] + ([text(PAGE)] if PAGE.exists() else [])
        for doc in docs:
            self.assertRegex(doc, r"G9\*{0,2} is the rubric")
            self.assertIn("at least two human raters per domain report agreement", doc)

    def test_rate_stated_with_scope(self):
        # The codebook's sample-scope rule: limits stated in the same breath as the claims they bound.
        docs = [README, METHOD, REPO / "README.md", REPO / "auditkit" / "README.md", REPO / "portfolio" / "index.html"]
        for path in docs:
            if not path.exists():
                continue
            doc = text(path)
            chunks = re.split(r"\n(?=#{1,4} )", doc) if path.suffix == ".md" else re.split(r"</p>", doc)
            for chunk in chunks:
                if "26.9%" in chunk:
                    self.assertRegex(chunk, r"one user", f"{path.name}: the 26.9% rate without its scope: {chunk[:100]!r}")

    def test_no_audit_only_qualifier(self):
        # "adversarially selected" may appear only in a paragraph that also states the papers' limits.
        for path in (README, METHOD):
            for para in re.split(r"\n\s*\n", text(path)):
                if "adversarially selected" in para and "Limitations the instrument states" not in para:
                    self.assertIn("SycEval", para, f"{path.name}: audit-only qualifier: {para[:120]!r}")


if __name__ == "__main__":
    unittest.main()
