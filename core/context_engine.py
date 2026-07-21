from typing import TypeVar, Generic, Callable, Any
from pydantic import BaseModel, Field

A = TypeVar("A")
B = TypeVar("B")


class CognitiveState(BaseModel):
    """The continuous variables tracked by PEDI."""

    coherence: float = Field(default=0.8, ge=0.0, le=1.0)
    resonance: float = Field(default=0.5, ge=0.0, le=1.0)
    tension: float = Field(default=0.3, ge=0.0, le=1.0)
    shadow_depth: float = Field(default=0.2, ge=0.0, le=1.0)


class CognitivePayload(BaseModel):
    """Structured payload for the comonadic cognitive pipeline.

    Each step in the pipeline writes to its own field instead of
    overwriting a raw string. This prevents the ‘junk drawer’ effect
    when the pipeline grows to support tool calls, embeddings, and
    multi-step reasoning.
    """

    user_input: str = ""
    internal_log: str = ""
    response: str = ""
    metadata: dict = Field(default_factory=dict)

    def model_copy(self, update: dict | None = None, **kwargs) -> "CognitivePayload":
        """Immutable copy with optional field overrides."""
        copied = super().model_copy(update=update, **kwargs)
        # Deep-copy metadata so mutations don't leak across contexts
        if update is None or "metadata" not in update:
            copied.metadata = {k: v for k, v in self.metadata.items()}
        return copied


class Context(BaseModel, Generic[A]):
    """The immutable container holding both the state and the current computation value."""

    state: CognitiveState
    history: list[CognitiveState] = Field(default_factory=list)
    value: A


class ContextWorker(Generic[A]):
    """The Comonadic wrapper that executes operations in context."""

    def __init__(self, context: Context[A]):
        self._ctx = context

    def current(self) -> A:
        """Extracts the current focused value."""
        return self._ctx.value

    @property
    def state(self) -> CognitiveState:
        """The current cognitive state (PEDI variables)."""
        return self._ctx.state

    @property
    def history(self) -> list[CognitiveState]:
        """The full chain of previous states (read-only via copy)."""
        return list(self._ctx.history)

    def extend(
        self, operation: Callable[["ContextWorker[A]"], B]
    ) -> "ContextWorker[B]":
        """
        Takes a context-dependent operation, applies it, and returns a NEW
        ContextWorker with the updated history and newly computed value.
        """
        result = operation(self)

        # Unpack result if the operation modified the state
        if (
            isinstance(result, tuple)
            and len(result) == 2
            and isinstance(result[1], CognitiveState)
        ):
            new_value, new_state = result
        else:
            new_value = result
            new_state = self._ctx.state.model_copy()

        # Build the new context immutably
        new_ctx = Context[B](
            state=new_state,
            history=self._ctx.history + [self._ctx.state],
            value=new_value,
        )
        return ContextWorker[B](new_ctx)

    def fork(
        self, operations: list[Callable[["ContextWorker[A]"], Any]]
    ) -> list["ContextWorker[Any]"]:
        """
        Branching cognition. Runs parallel operations from the same
        initial context and returns a list of new workers.

        Useful for:
        - logical path vs intuitive path
        - low tension vs high tension response
        - different prompt strategies
        """
        return [self.extend(op) for op in operations]

    def merge(
        self,
        branches: list["ContextWorker[Any]"],
        selector: Callable[[list["ContextWorker[Any]"]], "ContextWorker[Any]"],
    ) -> "ContextWorker[Any]":
        """
        Merge multiple branched workers back into a single lineage.

        The selector receives the list of branch workers and picks one
        (or synthesises a new payload) to continue the pipeline.
        """
        return selector(branches)
