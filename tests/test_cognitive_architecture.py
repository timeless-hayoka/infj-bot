"""Tests for the cognitive architecture registry and plugin system."""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from cognitive_architecture import (
    CognitiveArchitecture,
    CognitivePlugin,
    CycleContext,
    LoopStep,
)


class FakeModule:
    """Stub cognitive module for testing."""

    def __init__(self):
        self.cycle_calls = 0
        self.prompt_calls = 0

    def cycle(self, context):
        self.cycle_calls += 1

    def format_prompt_snippet(self):
        self.prompt_calls += 1
        return "[fake prompt]"


@pytest.fixture
def fresh_arch():
    CognitiveArchitecture.reset_instance()
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        path = tmp.name
    arch = CognitiveArchitecture(db_path=path)
    # Clear any auto-registered plugins from other imports
    for name in list(arch.list_plugins()):
        arch.unregister(name)
    yield arch
    CognitiveArchitecture.reset_instance()
    os.unlink(path)


class TestPluginRegistration:
    def test_register_and_list(self, fresh_arch):
        plugin = CognitivePlugin(
            name="fake",
            description="A fake module",
            module_path="tests.test_cognitive_architecture",
            instance_factory=FakeModule,
            cycle_handler="cycle",
            prompt_formatter="format_prompt_snippet",
        )
        fresh_arch.register(plugin)
        assert "fake" in fresh_arch.list_plugins()

    def test_unregister(self, fresh_arch):
        plugin = CognitivePlugin(
            name="fake",
            description="A fake module",
            module_path="tests.test_cognitive_architecture",
            instance_factory=FakeModule,
        )
        fresh_arch.register(plugin)
        fresh_arch.unregister("fake")
        assert "fake" not in fresh_arch.list_plugins()

    def test_duplicate_register_ignored(self, fresh_arch):
        plugin = CognitivePlugin(
            name="fake",
            description="A fake module",
            module_path="tests.test_cognitive_architecture",
            instance_factory=FakeModule,
        )
        fresh_arch.register(plugin)
        fresh_arch.register(plugin)  # should be idempotent
        assert len(fresh_arch.list_plugins()) == 1

    def test_get_enabled_plugins(self, fresh_arch):
        fresh_arch.register(
            CognitivePlugin(
                name="on",
                description="enabled",
                module_path="x",
                instance_factory=FakeModule,
                enabled=True,
            )
        )
        fresh_arch.register(
            CognitivePlugin(
                name="off",
                description="disabled",
                module_path="x",
                instance_factory=FakeModule,
                enabled=False,
            )
        )
        enabled = fresh_arch.get_enabled_plugins()
        assert len(enabled) == 1
        assert enabled[0].name == "on"


class TestLoopSteps:
    def test_get_loop_steps(self, fresh_arch):
        fresh_arch.register(
            CognitivePlugin(
                name="a",
                description="",
                module_path="x",
                instance_factory=FakeModule,
                cycle_handler="cycle",
                cycle_priority=10,
            )
        )
        fresh_arch.register(
            CognitivePlugin(
                name="b",
                description="",
                module_path="x",
                instance_factory=FakeModule,
                cycle_handler="cycle",
                cycle_priority=5,
            )
        )
        steps = fresh_arch.get_loop_steps()
        names = [s.plugin.name for s in steps]
        assert names == ["b", "a"]  # sorted by priority

    def test_loop_step_execution(self, fresh_arch):
        fresh_arch.register(
            CognitivePlugin(
                name="a",
                description="",
                module_path="x",
                instance_factory=FakeModule,
                cycle_handler="cycle",
            )
        )
        steps = fresh_arch.get_loop_steps()
        ctx = CycleContext(
            being=None,
            memory=None,
            state=None,
            brain=None,
            iteration=1,
            minutes_since_interaction=0.0,
            last_interaction_time=None,
        )
        steps[0].run(ctx)
        assert steps[0].instance.cycle_calls == 1

    def test_loop_step_respects_frequency(self, fresh_arch):
        fresh_arch.register(
            CognitivePlugin(
                name="a",
                description="",
                module_path="x",
                instance_factory=FakeModule,
                cycle_handler="cycle",
                cycle_frequency=3,
            )
        )
        steps = fresh_arch.get_loop_steps()
        ctx = CycleContext(
            being=None,
            memory=None,
            state=None,
            brain=None,
            iteration=1,
            minutes_since_interaction=0.0,
            last_interaction_time=None,
        )
        assert steps[0].should_run(1) is False
        assert steps[0].should_run(3) is True
        assert steps[0].should_run(6) is True


class TestPromptPlugins:
    def test_get_prompt_plugins_sorted(self, fresh_arch):
        fresh_arch.register(
            CognitivePlugin(
                name="a",
                description="",
                module_path="x",
                instance_factory=FakeModule,
                prompt_formatter="format_prompt_snippet",
                prompt_priority=100,
            )
        )
        fresh_arch.register(
            CognitivePlugin(
                name="b",
                description="",
                module_path="x",
                instance_factory=FakeModule,
                prompt_formatter="format_prompt_snippet",
                prompt_priority=10,
            )
        )
        plugins = fresh_arch.get_prompt_plugins()
        assert [p.name for p in plugins] == ["b", "a"]

    def test_prompt_formatting(self, fresh_arch):
        fresh_arch.register(
            CognitivePlugin(
                name="a",
                description="",
                module_path="x",
                instance_factory=FakeModule,
                prompt_formatter="format_prompt_snippet",
            )
        )
        plugins = fresh_arch.get_prompt_plugins()
        inst = plugins[0].instance_factory()
        snippet = getattr(inst, plugins[0].prompt_formatter)()
        assert "[fake prompt]" in snippet


class TestCycleContext:
    def test_context_creation(self):
        ctx = CycleContext(
            being="being",
            memory="memory",
            state="state",
            brain="brain",
            iteration=42,
            minutes_since_interaction=5.5,
            last_interaction_time=None,
        )
        assert ctx.iteration == 42
        assert ctx.minutes_since_interaction == 5.5
