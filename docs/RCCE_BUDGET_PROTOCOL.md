# RCCE matched-history benchmark

This exploratory benchmark compares replay of saved feedback with a deterministic organizer that selects the latest verified preference for the requested profile and context. Both conditions start from the same 51-record synthetic history. A separate Python process writes each profile's history, and evaluation verifies its hash before use.

Eight synthetic profiles cover all combinations of current preferences across three contexts. Each history includes two preference changes per context, unverified reversals, and unrelated profile and context records. Each profile receives three new cost/time trade-offs per context. Each task has opposing winners for the two metrics. Task order and paired condition order use fixed seeds.

Both arms use the same Gemini model, temperature, task text, JSON schema and maximum prompt budget of 1,600 provider-reported input tokens. A shared byte limit checks prompts before sending. The model receives full replay or the relevant record selected from that replay, with no critic or retry for malformed answers. Numeric inputs and expected letters are generated independently of model outputs. The exact schema requires one choice from A or B. Any schema violation fails the measurement gate. Each trial retains its original response, provider ID, model version, token count and hashes.

## Decision rules fixed before the live run

The primary endpoint is correct structured choice on 72 paired tasks. Directional sign tests use the eight profile-level paired accuracy differences, counting ties as failures to clear the tested threshold. The sign tests and thresholds are pilot decision rules over these synthetic profiles.

- **Accuracy advantage** requires at least a 10 percentage point mean gain and a one-sided sign test at 0.05.
- **Token efficiency** requires a one-sided sign test at 0.05 against a profile-level median accuracy-loss margin of 5 percentage points and at least 25% fewer provider-reported prompt tokens.
- **Use replay** if the accuracy noninferiority gate passes and the absolute accuracy and token differences are both at most 5%, or if replay has a symmetric 10-point accuracy advantage that clears the sign test.
- All other results are inconclusive.

The token measure covers prompt input. It excludes local indexing cost and does not estimate billed cost, latency, or a real-user effect. The organizer uses explicit verified feedback and cannot establish latent capabilities or personalization from natural conversation.
