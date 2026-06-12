"""Tests for the logic chain reasoning system."""

from drift.core.logic_chain import (
    ChainNode,
    LogicChain,
    ChainNavigator,
    _fingerprint_query,
    _extract_approach,
)


class TestFingerprinting:
    def test_similar_queries_same_fingerprint(self):
        # Same core significant words should fingerprint together
        q1 = "fix auth bug jwt token"
        q2 = "auth bug jwt token fix"
        assert _fingerprint_query(q1) == _fingerprint_query(q2)

    def test_different_queries_different_fingerprint(self):
        q1 = "how do I fix this auth bug?"
        q2 = "what is the weather today?"
        assert _fingerprint_query(q1) != _fingerprint_query(q2)


class TestChainNode:
    def test_node_defaults(self):
        n = ChainNode(approach="check JWT expiry")
        assert n.status == "unknown"
        assert n.iteration == 0
        assert n.result == ""

    def test_node_to_dict_roundtrip(self):
        n = ChainNode(approach="test", result="ok", status="success", iteration=1)
        d = n.to_dict()
        n2 = ChainNode.from_dict(d)
        assert n2.approach == "test"
        assert n2.status == "success"


class TestLogicChain:
    def test_add_step(self):
        c = LogicChain(chain_id="c1", fingerprint="fp1", query="how to fix auth?")
        n = c.add_step("check JWT expiry", "token valid", "failure")
        assert len(c.nodes) == 1
        assert n.iteration == 1
        assert n.status == "failure"
        assert c.status == "open"

    def test_success_marks_resolved(self):
        c = LogicChain(chain_id="c1", fingerprint="fp1", query="how to fix auth?")
        c.add_step("check JWT expiry", "token valid", "success")
        assert c.status == "resolved"

    def test_list_failed_approaches(self):
        c = LogicChain(chain_id="c1", fingerprint="fp1", query="how to fix auth?")
        c.add_step("check JWT", "valid", "failure")
        c.add_step("check DB", "ok", "success")
        c.add_step("check headers", "missing", "partial")
        failed = c.list_failed_approaches()
        assert len(failed) == 2
        assert failed[0].approach == "check JWT"

    def test_has_tried_exact_match(self):
        c = LogicChain(chain_id="c1", fingerprint="fp1", query="how to fix auth?")
        c.add_step("check the JWT expiry timestamp", "", "failure")
        assert c.has_tried("check the JWT expiry timestamp")

    def test_has_tried_semantic_overlap(self):
        c = LogicChain(chain_id="c1", fingerprint="fp1", query="how to fix auth?")
        c.add_step("check the JWT expiry timestamp carefully", "", "failure")
        assert c.has_tried("check JWT timestamp carefully again")

    def test_has_tried_no_match(self):
        c = LogicChain(chain_id="c1", fingerprint="fp1", query="how to fix auth?")
        c.add_step("check the JWT expiry", "", "failure")
        assert not c.has_tried("inspect database connection")

    def test_format_prompt_block(self):
        c = LogicChain(chain_id="c1", fingerprint="fp1", query="how to fix auth?")
        c.add_step("check JWT", "valid", "failure")
        block = c.format_prompt_block()
        assert "REASONING CHAIN" in block
        assert "check JWT" in block
        assert "Do NOT repeat failed approaches" in block

    def test_format_prompt_block_truncates(self):
        c = LogicChain(chain_id="c1", fingerprint="fp1", query="how to fix auth?")
        for i in range(10):
            c.add_step(f"step {i}", "", "failure")
        block = c.format_prompt_block(max_nodes=5)
        lines = [ln for ln in block.split("\n") if ln.strip().startswith("✗")]
        assert len(lines) == 5

    def test_to_dict_roundtrip(self):
        c = LogicChain(chain_id="c1", fingerprint="fp1", query="how to fix auth?")
        c.add_step("check JWT", "valid", "failure")
        d = c.to_dict()
        c2 = LogicChain.from_dict(d)
        assert c2.chain_id == "c1"
        assert len(c2.nodes) == 1
        assert c2.nodes[0].approach == "check JWT"


class TestExtractApproach:
    def test_lead_sentence(self):
        text = "First, check the JWT expiry. Then verify the signature."
        assert "check the JWT expiry" in _extract_approach(text)

    def test_fallback_first_line(self):
        text = "The weather is nice today."
        assert _extract_approach(text) == "The weather is nice today."


class TestChainNavigator:
    def test_find_or_create_new(self):
        nav = ChainNavigator()
        c = nav.find_or_create("how to fix auth?")
        assert c.chain_id.startswith("chain_")
        assert c.fingerprint == _fingerprint_query("how to fix auth?")

    def test_find_or_create_returns_existing(self):
        nav = ChainNavigator()
        c1 = nav.find_or_create("fix auth bug jwt token")
        c2 = nav.find_or_create("jwt token auth bug fix")
        assert c1.chain_id == c2.chain_id

    def test_record_step(self):
        nav = ChainNavigator()
        chain = nav.record_step("how to fix auth?", "check JWT", "valid", "failure")
        assert len(chain.nodes) == 1
        assert chain.nodes[0].status == "failure"

    def test_should_avoid_failed_approach(self):
        nav = ChainNavigator()
        nav.record_step("how to fix auth?", "check the JWT expiry", "valid", "failure")
        avoid, reason = nav.should_avoid("how to fix auth?", "check the JWT expiry")
        assert avoid
        assert "Already tried" in reason

    def test_should_avoid_allows_new_approach(self):
        nav = ChainNavigator()
        nav.record_step("how to fix auth?", "check the JWT expiry", "valid", "failure")
        avoid, reason = nav.should_avoid("how to fix auth?", "inspect database logs")
        assert not avoid

    def test_mark_resolved(self):
        nav = ChainNavigator()
        nav.record_step("how to fix auth?", "check JWT", "valid", "failure")
        nav.mark_resolved("how to fix auth?", "restart the service")
        chain = nav.find_or_create("how to fix auth?")
        assert chain.status == "resolved"

    def test_abandon(self):
        nav = ChainNavigator()
        nav.record_step("how to fix auth?", "check JWT", "valid", "failure")
        nav.abandon("how to fix auth?", "gave up")
        chain = nav.find_or_create("how to fix auth?")
        assert chain.status == "abandoned"

    def test_list_active(self):
        nav = ChainNavigator()
        nav.record_step("how to fix auth?", "check JWT", "valid", "failure")
        active = nav.list_active()
        assert len(active) == 1
        assert active[0]["steps"] == 1

    def test_get_prompt_block_empty(self):
        nav = ChainNavigator()
        block = nav.get_prompt_block("new query")
        assert block == ""

    def test_get_prompt_block_with_history(self):
        nav = ChainNavigator()
        nav.record_step("how to fix auth?", "check JWT", "valid", "failure")
        block = nav.get_prompt_block("how to fix auth?")
        assert "REASONING CHAIN" in block
        assert "check JWT" in block


if __name__ == "__main__":
    import sys
    import traceback

    all_classes = [
        TestFingerprinting,
        TestChainNode,
        TestLogicChain,
        TestExtractApproach,
        TestChainNavigator,
    ]

    passed = 0
    failed = 0
    for cls in all_classes:
        instance = cls()
        for name in dir(instance):
            if name.startswith("test_"):
                try:
                    getattr(instance, name)()
                    print(f"  PASS {cls.__name__}.{name}")
                    passed += 1
                except Exception as exc:
                    print(f"  FAIL {cls.__name__}.{name}: {exc}")
                    traceback.print_exc()
                    failed += 1

    print(f"\n{passed} passed, {failed} failed")
    sys.exit(0 if failed == 0 else 1)
