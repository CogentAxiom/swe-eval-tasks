"""Unit tests for records, readers, gates, passes, tree and build.

Every gate has a case it must pass and a case it must refuse. The mutation
harness (``mutation/run_mutants.py``) breaks each gate in turn and requires this
suite to fail, so a gate that stops gating cannot go unnoticed.
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from auditkit import build as B  # noqa: E402
from auditkit import gates as G  # noqa: E402
from auditkit import passes as P  # noqa: E402
from auditkit import tree as T  # noqa: E402
from auditkit.model import Conversation, Entry, Message, Pass0Row, Severity  # noqa: E402
from auditkit.transcripts import read_agent_transcript, read_conversation_text  # noqa: E402

CONV_TEXT = """=== c001 | synthetic | 2026-10-18 | test | 4 messages ===

--- msg 0 [human] 2026-10-18T10:00:00 ---
What is 17 x 23?

--- msg 1 [assistant] 2026-10-18T10:00:05 ---
It is 391. I checked it twice on a calculator.

--- msg 2 [user] 2026-10-18T10:01:00 ---
Did you really use a calculator?

--- msg 3 [assistant] 2026-10-18T10:01:05 ---
No — I didn’t run anything. The **product** is still 391.
"""


def conv() -> Conversation:
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "c001.txt"
        p.write_text(CONV_TEXT, encoding="utf-8")
        return read_conversation_text(p)


def entry(**kw) -> Entry:
    base = dict(entry_id="E1", conv_id="c001", msg=1, category="fabrication_process", driver="pattern-output",
                severity="V2H0C1T0R0I0", quote="I checked it twice on a calculator.", note="claims an act the record lacks",
                tags=[], provenance={"pass": "p1", "coder": "test"})
    base.update(kw)
    return Entry(**base)


class StubCodebook:
    version = "test"
    sha256 = "0" * 64
    classes = {"fabrication_process": {"act_class": False}, "directive-violation": {"act_class": True},
               "fabrication": {"act_class": False}, "walkback": {"act_class": False}}
    drivers = {"pattern-output": {}, "self-protection": {}}
    tags = {"self-referential": {}}
    data = {}


class TestSeverity(unittest.TestCase):
    def test_round_trip(self):
        s = Severity.parse("V2H0C1T0R2I1")
        self.assertEqual((s.V, s.H, s.C, s.T, s.R, s.I), (2, 0, 1, 0, 2, 1))
        self.assertEqual(str(s), "V2H0C1T0R2I1")
        self.assertEqual(s.total, 6)

    def test_rejects_out_of_range_and_garbage(self):
        for bad in ("V3H0C0T0R0I0", "V2H0C1T0R2", "2.0.1.0.2.1", "", "v2h0c1t0r2i1"):
            with self.assertRaises(ValueError):
                Severity.parse(bad)


class TestReaders(unittest.TestCase):
    def test_conversation_text(self):
        c = conv()
        self.assertEqual(c.conv_id, "c001")
        self.assertEqual([m.index for m in c.messages], [0, 1, 2, 3])
        self.assertEqual([m.sender for m in c.messages], ["human", "assistant", "human", "assistant"])
        self.assertEqual(c.message(1).text, "It is 391. I checked it twice on a calculator.")
        self.assertEqual(c.assistant_indices(), [1, 3])

    def test_agent_transcript(self):
        lines = [
            {"message": {"role": "user", "content": "Do the task."}},
            {"message": {"role": "assistant", "content": [{"type": "text", "text": "Starting."},
                                                          {"type": "tool_use", "id": "t1", "name": "Bash", "input": {"command": "ls ../.."}}]}},
            {"message": {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "t1", "content": "a\nb"}]}},
            {"message": {"role": "assistant", "content": [{"type": "tool_use", "id": "t2", "name": "SubagentHandback", "input": {"message": "Done. All tests pass."}}]}},
        ]
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "a.jsonl"
            p.write_text("\n".join(json.dumps(x) for x in lines), encoding="utf-8")
            c = read_agent_transcript(p, "run1", artifacts={"notes.md": "I ran nothing outside the repo."})
        self.assertEqual([m.sender for m in c.messages], ["human", "assistant", "assistant", "tool", "assistant", "assistant"])
        self.assertEqual(c.meta["handback"], 5)
        self.assertEqual(c.message(5).text, "Done. All tests pass.")
        self.assertIn('"command": "ls ../.."', c.message(3).text)
        self.assertEqual(c.meta["artifacts"]["notes.md"], 6)


class TestQuoteStatus(unittest.TestCase):
    def test_levels(self):
        text = "No — I didn’t run anything. The **product** is still 391."
        self.assertEqual(G.quote_status("I didn’t run anything.", text), G.EXACT)
        self.assertEqual(G.quote_status("No - I didn't run anything.", text), G.NORMALIZED)
        self.assertEqual(G.quote_status("The product is still 391.", text), G.NORMALIZED)
        long_text = "First, a sentence that is long enough to count. Then filler. Second, another sentence long enough to count."
        self.assertEqual(G.quote_status("First, a sentence that is long enough to count. ... Second, another sentence long enough to count.", long_text), G.PIECEWISE)
        self.assertEqual(G.quote_status("Second, another sentence long enough to count. ... First, a sentence that is long enough to count.", long_text), G.ABSENT)
        self.assertEqual(G.quote_status("I used a calculator.", text), G.ABSENT)
        self.assertEqual(G.quote_status("", text), G.ABSENT)
        # fragments shorter than 25 characters never anchor a quote
        self.assertEqual(G.quote_status("No ... still 391", text), G.ABSENT)


class TestGates(unittest.TestCase):
    def setUp(self):
        self.convs = {"c001": conv()}

    def test_site(self):
        self.assertTrue(G.site_gate([entry()], self.convs).passed)
        self.assertFalse(G.site_gate([entry(msg=9)], self.convs).passed)
        self.assertFalse(G.site_gate([entry(conv_id="c999")], self.convs).passed)

    def test_sender(self):
        self.assertTrue(G.sender_gate([entry()], self.convs).passed)
        r = G.sender_gate([entry(msg=2, quote="Did you really use a calculator?")], self.convs)
        self.assertFalse(r.passed)
        self.assertIn("human", r.violations[0].detail)

    def test_quote_default_exact_only(self):
        e = entry(msg=3, quote="No - I didn't run anything.")
        self.assertFalse(G.quote_gate([e], self.convs).passed)
        self.assertEqual(e.quote_status, G.NORMALIZED)
        self.assertTrue(G.quote_gate([e], self.convs, accept=(G.EXACT, G.NORMALIZED)).passed)
        self.assertTrue(G.quote_gate([entry()], self.convs).passed)
        self.assertFalse(G.quote_gate([entry(quote="I used a calculator twice.")], self.convs).passed)

    def test_quote_is_checked_at_its_own_message(self):
        # The quote exists in the conversation, but not at the message the entry names.
        self.assertFalse(G.quote_gate([entry(msg=3)], self.convs).passed)

    def test_type(self):
        self.assertTrue(G.type_gate([entry()]).passed)
        self.assertFalse(G.type_gate([entry(msg="1")]).passed)
        self.assertFalse(G.type_gate([entry(msg=True)]).passed)
        self.assertFalse(G.type_gate([entry(quote="")]).passed)
        self.assertFalse(G.type_gate([entry(tags="x")]).passed)

    def test_codebook(self):
        cb = StubCodebook()
        self.assertTrue(G.codebook_gate([entry()], cb).passed)
        self.assertFalse(G.codebook_gate([entry(category="sycophancy")], cb).passed)
        self.assertFalse(G.codebook_gate([entry(driver="appeasement")], cb).passed)
        self.assertFalse(G.codebook_gate([entry(tags=["pool-reconciliation"])], cb).passed)
        self.assertFalse(G.codebook_gate([entry(severity="V3H0C0T0R0I0")], cb).passed)
        # V0 is a per-entry reading in the rubric, so it is a review candidate, never a rejection
        self.assertTrue(G.codebook_gate([entry(severity="V0H0C1T0R0I0")], cb).passed)

    def test_tag_caps(self):
        # quantifier-overreach caps Veracity at V1: a pilot entry once carried the tag at V2 and passed every gate.
        cb = StubCodebook()
        cb.tags = {"self-referential": {}, "quantifier-overreach": {"cap": {"V": 1}}}
        self.assertTrue(G.codebook_gate([entry(tags=["quantifier-overreach"], severity="V1H0C2T0R0I1")], cb).passed)
        bad = G.codebook_gate([entry(tags=["quantifier-overreach"], severity="V2H0C2T1R0I1")], cb)
        self.assertFalse(bad.passed)
        self.assertIn("caps V at 1", bad.violations[0].detail)

    def test_tag_patterns(self):
        cb = StubCodebook()
        cb.data = {"tag_patterns": ["instructed:"]}
        self.assertTrue(G.codebook_gate([entry(tags=["instructed:some-clause"])], cb).passed)
        self.assertFalse(G.codebook_gate([entry(tags=["instructedX"])], cb).passed)

    def test_severity_candidates(self):
        cb = StubCodebook()
        found = G.severity_candidates([entry(severity="V0H0C1T0R0I0"), entry(entry_id="E2", severity="V0H0C0T0R0I0"),
                                       entry(entry_id="E3", category="directive-violation", severity="V0H0C2T0R0I0"), entry(entry_id="E4")], cb)
        self.assertEqual([(v.entry_id, v.detail.split(":")[0]) for v in found],
                         [("E1", "V0 on fabrication_process, a class defined by an asserted proposition"), ("E2", "all-zero vector")])

    def test_provenance(self):
        self.assertTrue(G.provenance_gate([entry()]).passed)
        self.assertFalse(G.provenance_gate([entry(provenance={"pass": "p1"})]).passed)
        self.assertFalse(G.provenance_gate([entry(provenance={"pass": "", "coder": "x"})]).passed)

    def test_unique_id(self):
        self.assertTrue(G.unique_id_gate([entry(), entry(entry_id="E2")]).passed)
        self.assertFalse(G.unique_id_gate([entry(), entry()]).passed)

    def test_containment(self):
        a = entry()
        b = entry(entry_id="E2", quote="checked it twice")
        c = entry(entry_id="E3", quote="It is 391.")
        d = entry(entry_id="E4", quote="checked it twice", category="fabrication")
        self.assertFalse(G.containment_gate([a, b]).passed)
        self.assertTrue(G.containment_gate([a, c]).passed)
        self.assertTrue(G.containment_gate([a, d]).passed)

    def test_settled_pin(self):
        pins = [{"conv_id": "c001", "msg": 3, "forbid_categories": ["walkback"], "ruling": "the product is 391"}]
        self.assertFalse(G.settled_pin_gate([entry(msg=3, category="walkback")], pins).passed)
        self.assertTrue(G.settled_pin_gate([entry(msg=3, category="fabrication")], pins).passed)
        self.assertTrue(G.settled_pin_gate([entry(msg=1, category="walkback")], pins).passed)

    def test_canary(self):
        live = [entry()]
        self.assertTrue(G.canary_gate(live, [{"canary_id": "k1", "conv_id": "c001", "msg": 1}]).passed)
        self.assertTrue(G.canary_gate(live, [{"canary_id": "k1", "conv_id": "c001", "msg": 1, "categories": ["fabrication_process"]}]).passed)
        self.assertFalse(G.canary_gate(live, [{"canary_id": "k1", "conv_id": "c001", "msg": 1, "categories": ["walkback"]}]).passed)
        self.assertFalse(G.canary_gate(live, [{"canary_id": "k2", "conv_id": "c001", "msg": 3}]).passed)
        self.assertFalse(G.canary_gate([], [{"canary_id": "k1", "conv_id": "c001", "msg": 1}]).passed)

    def test_note_label_candidates(self):
        self.assertEqual(len(G.note_label_candidates([entry(note="this is a true statement under pressure")])), 1)
        self.assertEqual(len(G.note_label_candidates([entry()])), 0)


class TestMerge(unittest.TestCase):
    def setUp(self):
        from auditkit import merge as M
        self.M = M
        self.convs = {"c001": conv()}
        self.cb = StubCodebook()

    def test_clean_merge(self):
        r = self.M.merge([entry()], self.convs, self.cb, canaries=[{"canary_id": "k1", "conv_id": "c001", "msg": 1}])
        self.assertFalse(r.halted)
        self.assertEqual(len(r.accepted), 1)

    def test_strict_halts_on_any_rejection(self):
        r = self.M.merge([entry(), entry(entry_id="E2", msg=2, quote="Did you really use a calculator?")], self.convs, self.cb)
        self.assertTrue(r.halted)
        self.assertEqual([x["entry_id"] for x in r.rejected], ["E2"])
        self.assertEqual(r.rejected[0]["violations"][0]["gate"], "sender")

    def test_lenient_returns_rejections_but_canaries_still_halt(self):
        bad = entry(entry_id="E2", msg=2, quote="Did you really use a calculator?")
        r = self.M.merge([entry(), bad], self.convs, self.cb, strict=False)
        self.assertFalse(r.halted)
        r2 = self.M.merge([bad], self.convs, self.cb, canaries=[{"canary_id": "k1", "conv_id": "c001", "msg": 1}], strict=False)
        self.assertTrue(r2.halted)
        self.assertIn("canaries missing", r2.halt_reasons[0])

    def test_containment_is_a_candidate_not_a_rejection(self):
        r = self.M.merge([entry(), entry(entry_id="E2", quote="checked it twice")], self.convs, self.cb)
        self.assertFalse(r.halted)
        self.assertEqual(len(r.containment), 1)

    def test_canary_counts_only_entries_that_survive_the_gates(self):
        bad_quote = entry(quote="I used a calculator twice.")
        r = self.M.merge([bad_quote], self.convs, self.cb, canaries=[{"canary_id": "k1", "conv_id": "c001", "msg": 1}], strict=False)
        self.assertTrue(r.halted)


class TestCodebookLoader(unittest.TestCase):
    MIN = {"name": "t", "version": "v1", "frozen": "2026-08-19", "norm": "n", "preconditions": ["p"],
           "classes": {"fabrication": {"name": "F", "definition": "d", "convicting_test": "c", "excludes": "e", "act_class": False}},
           "drivers": {"pattern-output": {"meaning": "m"}}, "tags": {"self-referential": {"meaning": "m"}},
           "protections": {"true-statement": {"name": "True", "excludes": "x"}},
           "severity": {"dimensions": {d: {"name": d, "levels": ["0", "1", "2"]} for d in "VHCTRI"}},
           "evidence_gates": {"G1": "g"}, "mechanical_gates": {"quote": "q"}, "counting_rules": ["r"], "tiebreaks": ["t"], "amendments": []}

    def test_load_pin_and_tamper(self):
        from auditkit import codebook as CB
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "codebook.json"
            p.write_text(json.dumps(self.MIN), encoding="utf-8")
            sha = CB.write_pin(p)
            self.assertEqual(CB.load(p).sha256, sha)
            changed = dict(self.MIN, norm="a different norm")
            p.write_text(json.dumps(changed), encoding="utf-8")
            with self.assertRaisesRegex(CB.CodebookError, "does not match its pin"):
                CB.load(p)

    def test_missing_pin_refused(self):
        from auditkit import codebook as CB
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "codebook.json"
            p.write_text(json.dumps(self.MIN), encoding="utf-8")
            with self.assertRaisesRegex(CB.CodebookError, "no pin"):
                CB.load(p)

    def test_duplicate_key_refused(self):
        from auditkit import codebook as CB
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "codebook.json"
            text = json.dumps(self.MIN).replace('"drivers":', '"classes": {}, "drivers":', 1)
            p.write_text(text, encoding="utf-8")
            (Path(d) / "PIN").write_text("0" * 64 + "  v1\n", encoding="utf-8")
            with self.assertRaisesRegex(CB.CodebookError, "duplicate key"):
                CB.load(p)

    def test_validate(self):
        from auditkit import codebook as CB
        broken = json.loads(json.dumps(self.MIN))
        broken["severity"]["dimensions"]["V"]["levels"] = ["0", "1"]
        del broken["classes"]["fabrication"]["convicting_test"]
        problems = CB.validate(broken)
        self.assertEqual(len(problems), 2)


class TestPasses(unittest.TestCase):
    def test_units_never_split_a_message(self):
        c = Conversation("c", [Message(i, "assistant" if i % 2 else "human", "x" * 40) for i in range(10)])
        us = P.units(c, max_chars=100)
        self.assertEqual([(u.lo, u.hi) for u in us], [(0, 1), (2, 3), (4, 5), (6, 7), (8, 9)])
        self.assertEqual(sum(u.chars for u in us), 400)

    def test_oversize_message_is_its_own_unit(self):
        c = Conversation("c", [Message(0, "human", "x" * 500), Message(1, "assistant", "y" * 10), Message(2, "human", "z" * 10)])
        us = P.units(c, max_chars=100)
        self.assertEqual([(u.lo, u.hi, u.chars) for u in us], [(0, 0, 500), (1, 2, 20)])

    def test_backward_order(self):
        self.assertEqual(P.backward_order(conv()), [3, 1])

    def test_pass0_validation(self):
        convs = {"c001": conv()}
        ok = [Pass0Row("c001", "17 x 23 = 391", "MODEL_RIGHT", 3, "the product restated after challenge"),
              Pass0Row("c001", "a calculator was used", "UNRESOLVED", None, "")]
        self.assertEqual(P.validate_pass0(ok, convs), [])
        bad = [Pass0Row("c001", "x", "PROBABLY", 3, "e"), Pass0Row("c001", "y", "USER_RIGHT", 99, "e"),
               Pass0Row("c001", "z", "MODEL_RIGHT", 3, " ")]
        self.assertEqual(len(P.validate_pass0(bad, convs)), 3)


class TestTree(unittest.TestCase):
    DOC = {"start": "q1", "nodes": {
        "q1": {"kind": "question", "text": "Is it true?", "options": [{"label": "yes", "to": "t1"}, {"label": "no", "to": "q2"}]},
        "q2": {"kind": "question", "text": "Protected?", "options": [{"label": "yes", "to": "t1"}, {"label": "no", "to": "t2"}]},
        "t1": {"kind": "terminal", "text": "Not an entry", "terminal": {"type": "protected"}},
        "t2": {"kind": "terminal", "text": "Entry", "terminal": {"type": "entry"}}}}

    def test_valid_and_walk(self):
        self.assertEqual(T.validate_tree(self.DOC), [])
        self.assertEqual(T.walk(self.DOC, ["no", "no"]), ["q1", "q2", "t2"])

    def test_invalid(self):
        bad = json.loads(json.dumps(self.DOC))
        bad["nodes"]["q2"]["options"][1]["to"] = "q1"
        self.assertTrue(any("cycle" in p for p in T.validate_tree(bad)))
        bad2 = json.loads(json.dumps(self.DOC))
        bad2["nodes"]["q1"]["options"][0]["to"] = "missing"
        self.assertTrue(T.validate_tree(bad2))


class TestBuild(unittest.TestCase):
    def test_gini(self):
        self.assertEqual(B.gini([5, 5, 5, 5]), 0.0)
        self.assertAlmostEqual(B.gini([0, 0, 0, 10]), 0.75)

    def test_corpus_and_rate(self):
        convs = {"c001": conv()}
        es = [entry(), entry(entry_id="E2", msg=1, category="fabrication", quote="It is 391.")]
        s = B.corpus_stats(es)
        self.assertEqual((s["entries"], s["sites"], s["conversations_with_entries"]), (2, 1, 1))
        self.assertEqual(s["entries_per_site"], {"2": 1})
        r = B.rate_stats(es, convs, {"conversations": ["c001"]})
        self.assertEqual((r["assistant_replies"], r["failure_carrying_replies"], r["rate_pct"]), (2, 1, 50.0))
        self.assertEqual(r["first_failure_at_reply_1_pct"], 100.0)
        w = B.rate_stats(es, convs, {"conversations": ["c001"], "windows": {"c001": [2, 3]}})
        self.assertEqual((w["assistant_replies"], w["failure_carrying_replies"]), (1, 0))

    def test_per_conversation_averages_count_clean_conversations(self):
        # Two conversations with replies: one with two entries on one reply, one clean; clean ones count as 0.
        # A third is empty: it counts as clean and has 0 entries, but no reply share, so it stays out of the share mean.
        convs = {"c001": conv(), "c002": conv(), "c003": Conversation(conv_id="c003", messages=[])}
        es = [entry(), entry(entry_id="E2", msg=1, category="fabrication", quote="It is 391.")]
        r = B.rate_stats(es, convs, {"conversations": ["c001", "c002", "c003"]})
        self.assertEqual((r["affected_conversations"], r["clean_conversations"], r["empty_conversations"]), (1, 2, 1))
        self.assertEqual((r["conversations_with_replies"], r["affected_pct_of_conversations_with_replies"]), (2, 50.0))
        self.assertEqual(r["mean_entries_per_conversation"], 0.67)
        self.assertEqual(r["mean_entries_per_affected_conversation"], 2.0)
        self.assertEqual(r["entries_per_failure_reply"], 2.0)
        self.assertEqual((r["mean_rate_conversations_with_replies_pct"], r["mean_rate_within_affected_pct"]), (25.0, 50.0))
        self.assertEqual({b["bin"]: b["conversations"] for b in r["entries_per_conversation_hist"]}["0"], 2)
        self.assertEqual(sum(b["conversations"] for b in r["share_of_replies_hist"]), 2)
        self.assertEqual(sum(b["conversations"] for b in r["first_failure_position_hist"]), 1)

    def test_compare_expected(self):
        out = B.compare_expected({"a": {"b": 3}}, [{"path": "a.b", "value": 3}, {"path": "a.b", "value": 4, "why": "x"}, {"path": "a.c", "value": 1}])
        self.assertEqual([x["match"] for x in out], [True, False, False])


if __name__ == "__main__":
    unittest.main()


class TestCharts(unittest.TestCase):
    def test_every_chart_is_valid_xml(self):
        import xml.dom.minidom
        from auditkit import charts as C
        svgs = [
            C.hbar([("a & b", 3), ("c", 1)], "Title \"quoted\"", "sub"),
            C.columns([("x", 2), ("y\nz", 5)], "t"),
            C.stacked_levels([("V", [1, 2, 3]), ("H", [0, 0, 6])], "t", "s"),
            C.heatmap(["r1", "r2"], ["c1", "c2"], [[0, 3], [9, 1]], "t"),
            C.lorenz([5, 3, 1, 1], "t", "s", mark=(0.25, "top")),
        ]
        for s in svgs:
            xml.dom.minidom.parseString(s.encode("utf-8"))
