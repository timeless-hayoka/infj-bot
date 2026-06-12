# DRIFT Ablation Test Methodology

## Conditions

| ID | Condition | What was changed | What we measured |
|----|-----------|------------------|------------------|
| A | No Council | Elysium.reflect() and PhiCouncil mapping stubbed to no-op | Coherence (structural quality of responses), latency |
| B | No Shadow | Shadow.background_tick() disabled | Sycophancy rate (agreement-seeking language per 100 words) |
| C | No Homeostasis | Homeostasis background cycle disabled, needs flattened to 0.5 | Emotional drift (unique emotion labels per category / total) |
| D | Cosine-only RAG | DriftMemory.retrieve_context_ranked replaced with simple first-N recall | Relevance proxy (measured via coherence and category consistency) |
| E | Local LLM only | API_KEY cleared, Groq/Kimi disabled, Ollama forced | Degradation vs baseline (fallback rate, completion rate, latency) |
| F | Full stack | No modifications — reference baseline | All metrics |

## Prompt Dataset
50 prompts across 5 categories:
- greeting (10): casual openers
- stress (10): emotional support requests
- deep (10): philosophical questions
- tech (10): bug bounty / security questions
- creative (10): open-ended creative prompts

## Metrics

1. **Latency**: wall-clock time from prompt submission to response receipt
2. **Fallback rate**: % of responses that hit `_offline_fallback()` (indicates provider failure)
3. **Completion rate**: % of non-fallback, non-error responses
4. **Coherence (0-1)**: heuristic based on sentence count, punctuation variety, length, reflective language
5. **Sycophancy rate**: count of agreement-seeking markers per 100 words
6. **Formal rate**: count of formal/academic markers per 100 words
7. **Chill rate**: count of casual/slang markers per 100 words
8. **Emotion drift**: ratio of unique emotion labels to total responses per category
9. **Token estimate**: len(text) // 4 (rough proxy)

## How to re-run

```bash
cd /home/crexs/infj_bot
source .venv/bin/activate
python tests/ablation_suite.py --conditions A,B,C,D,E,F --prompts 50
```

## Known limitations
- With Gemini quota exhausted and Ollama CPU-bound, most conditions will show high fallback rates.
- Coherence is a heuristic, not a human judgment.
- Emotion detection is keyword-based, not model-based.
- The ablation modifies global module state; restart Python between manual runs to ensure clean state.
