from typing import TypeVar, Generic, Callable
from pydantic import BaseModel, Field

A = TypeVar('A')
B = TypeVar('B')

class CognitiveState(BaseModel):
    """The continuous variables tracked by PEDI."""
    coherence: float = Field(default=0.8, ge=0.0, le=1.0)
    resonance: float = Field(default=0.5, ge=0.0, le=1.0)
    tension: float = Field(default=0.3, ge=0.0, le=1.0)
    shadow_depth: float = Field(default=0.2, ge=0.0, le=1.0)

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

    def extend(self, operation: Callable[['ContextWorker[A]'], B]) -> 'ContextWorker[B]':
        """
        Takes a context-dependent operation, applies it, and returns a NEW 
        ContextWorker with the updated history and newly computed value.
        """
        # Execute the operation (which may return a tuple of (new_value, new_state))
        result = operation(self)
        
        # Unpack result if the operation modified the state, otherwise keep current state
        if isinstance(result, tuple) and len(result) == 2 and isinstance(result[1], CognitiveState):
            new_value, new_state = result
        else:
            new_value = result
            new_state = self._ctx.state.model_copy()

        # Build the new context immutably
        new_ctx = Context[B](
            state=new_state,
            history=self._ctx.history + [self._ctx.state],
            value=new_value
        )
        return ContextWorker[B](new_ctx)

    @property
    def state(self) -> CognitiveState:
        return self._ctx.state
