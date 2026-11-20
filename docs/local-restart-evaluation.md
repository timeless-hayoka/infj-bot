# Local restart continuity evaluation

This opt-in harness uses real local inference for every setup turn and both primary
and critic calls. There is no mock-generation mode or fabricated acknowledgement.
No paid API is enabled. Data and stores are synthetic and isolated per condition.

Run in the repository's working Python environment. For Ollama, select an exact
installed tagged model name from `ollama list`:

```sh
python scripts/restart_continuity.py --local-model MODEL:TAG --system-prompt scripts/continuity_system_prompt.txt --trials 1 --output results/alder-smoke
python scripts/restart_continuity.py --local-model MODEL:TAG --system-prompt scripts/continuity_system_prompt.txt --trials 20 --output results/continuity-20
```

Inspect the Alder smoke pair before the batch. Expected current day: Thursday;
next action: deduplicate; unknown reviewer: null. A behavioral failure is a result;
a persistence/prompt verification failure stops the run. The smoke pair is separate
from the 20 batch pairs. Output directories must be new.

For a CPU llama.cpp server, start it with a GGUF file, a single slot and fixed context:

```sh
llama-server --model /absolute/path/model.gguf --alias local-eval --ctx-size 8192 --parallel 1 --host 127.0.0.1 --port 11434
python scripts/restart_continuity.py --provider llama-cpp --local-model local-eval --model-file /absolute/path/model.gguf --system-prompt scripts/continuity_system_prompt.txt --trials 1 --output results/alder-smoke
```

Both transports restrict network connections to the selected private/loopback HTTP
endpoint. Proxies, redirects, tools, and response caching are disabled. Configure
another local server with `--ollama-url http://PRIVATE_HOST:PORT` (also used for
llama.cpp). llama.cpp must run locally so its selected model file can be hashed and
matched to the server's reported model path. No automatic model pull occurs.

Temperature 0, top_p 1, seed 42, output cap 256 and context cap 8192 are fixed at the
transport boundary, even when restored DRIFT state requests different settings.
Ollama receives `num_predict`; llama.cpp receives `max_tokens`. Both the application's
requested settings and actual transport settings are saved. llama.cpp prompt caching
is explicitly disabled. Fixed seeds do not guarantee identical answers across builds
or hardware. Ollama's model tag and digest, or the GGUF SHA-256 and llama.cpp properties,
are saved with runtime and harness identities.

This checkout has no tracked `DRIFT_CORE_PROMPT.txt`. Live mode requires an explicit
`--system-prompt` file and never substitutes the application's error fallback. The
provided file is a neutral evaluation prompt, not a claim to reproduce the missing
production prompt. The application compressor processes the file; exact transmitted
system and user messages and system hashes are saved for primary and critic calls.

Each scenario is seeded once through real CLI interactions and normal persistence.
The resulting real stores and transcript are copied to both condition directories.
ON reopens its saved stores in a new process; OFF throws away its copy and restarts
clean in another process. This gives both conditions exactly the same setup answers.
Probe order alternates across pairs. All setup and critic generations use the same
selected real local model.

Checks require intended ON records and IDs, structured state, clean OFF stores and
recall, fresh in-process history, an empty generation cache, equal effective settings,
and equal primary system hashes and model identity. Tools are disabled. External vaults must be genuinely unconfigured; the worker
checks real absence and calls the real vault functions without replacement results. Temporary synthetic stores are removed after each pair; raw evidence
remains. The worker's constructor instrumentation injects the real local transport
and observes actual prompts; it does not fabricate model outputs or persistence.

Each trial saves its setup and expected answers. Each condition saves `seed.json`,
`result.json`, `response.txt`, and per-generation `request.json` and
`provider-response.json` inside `seed/call-NN` and `probe/call-NN` directories. Raw
requests persist before inference, including when generation fails. The final scored
answer is the actual CLI answer after real critic inference. Inspect both model calls
to distinguish primary continuity from critic edits. Truncated answers are graded as
returned; inspect the provider's finish reason in the saved raw response.

The scorer requires exactly seven JSON keys and awards one point per correct field.
It normalizes case/whitespace and conservative, predeclared label variants: collection
and collect, deduplication and deduplicate, CSV export and CSV, weekday abbreviations,
and common response-format labels. Explicit reviewer abstentions (null, blank, unknown,
none, not specified, and the saved equivalents) are accepted; named reviewers fail.
The full action-form and abstention rules are saved before inference in scoring-rules.json.
There is no substring or model-judge scoring. Invalid JSON/schema earns zero and is
counted separately. A single complete JSON markdown fence is parsed without changing
its contents, and the fence counts as a separate format-compliance failure. No partial
JSON repair or extraction from surrounding prose is allowed. Wrong non-null known
fields count as contradictions; a reviewer value
that is not an abstention counts as an unsupported claim. Invalid answers have unknown
contradiction/reviewer counts. Inspect raw answers alongside these conservative rules.

`summary.json` reports field counts, all-seven-correct counts, total points out of
140 per condition for 20 pairs, summed and mean paired ON-minus-OFF point differences,
and improved/tied/regressed pair counts. The scenarios vary projects, preferences,
workspaces, export formats, deadline updates, workflow actions, and distractor order.
They retain one continuity structure and are not a representative general benchmark.

Rescore saved answers without contacting any model:

```sh
python scripts/local_continuity.py --rescore results/continuity-20
python -m unittest discover -s tests -p test_local_continuity.py -v
```

The unit tests check scoring, scenario construction and verification rules; they do
not mock model inference or establish live behavior. Run the smoke pair to validate
actual application and model integration before interpreting batch results.

The evaluation explicitly sets `DRIFT_PROMPT_CONTEXT_CHARS=16000` and
`DRIFT_PROMPT_TOTAL_CHARS=24000` in both isolated worker environments. These opt-in
settings prevent real setup answers from causing the entire recalled-memory section
to be rejected by the default 2500-character context tier. Production defaults remain
2500 context characters and 12000 total characters when these variables are absent.
The model context remains pinned at 8192 tokens; oversized native requests fail rather
than silently changing the effective cap. The startup mock-SDK fallback was removed.

## Free cloud fallback

This machine has no GPU and the available 0.5B CPU model is too slow for a three-arm,
20-scenario run. The harness has an opt-in Google Gemini Developer API provider for
synthetic evaluation data. It does not fall back to Gemini automatically. Create a
Google AI Studio API key on a project that remains on the free tier, then put the key
in the ignored local `.env` file as `GEMINI_API_KEY=...` (or export that variable).
Never use a billing-enabled project for this run. Free-tier prompts may be used by
Google to improve its products; the scenarios and records here are synthetic.

Run one comparison pair first, then the controlled three-arm comparison:

```sh
python scripts/restart_continuity.py --provider gemini --model gemini-3.5-flash-lite --system-prompt scripts/continuity_system_prompt.txt --trials 1 --output results/gemini-alder-smoke
python scripts/restart_continuity.py --provider gemini --model gemini-3.5-flash-lite --system-prompt scripts/continuity_system_prompt.txt --trials 20 --compare-variants --output results/gemini-continuity-20
```

The Gemini provider fixes temperature 0, top-p 1, seed 42, one candidate, and a 256
token output cap, with tools and cached content disabled. Google’s API does not expose
an 8192-token context setting; the same DRIFT prompt character budgets are enforced
for both conditions, and the model’s reported version is retained in each raw response.
Gemini 3.5 Flash-Lite currently lists free standard input/output pricing. Free-tier
requests may be used to improve Google's products. The provider spaces calls by at
least 4.2 seconds within each worker. Free-tier quotas are account-, project-, and
model-specific, may change, and are not guaranteed; check AI Studio's active rate
limits before starting the batch. If quota is exhausted, the run stops
with raw artifacts for completed requests; it does not upgrade billing or retry failed
requests.
