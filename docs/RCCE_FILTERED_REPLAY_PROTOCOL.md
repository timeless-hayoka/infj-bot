# RCCE organizer versus filtered replay

The primary comparison is the organizer versus verified, relevance-filtered replay. Full unordered replay is a reference arm. Eight synthetic profiles each face six fresh time-and-cost decisions across three contexts. Each pair of A/B options has opposing time and cost winners. The latest valid default and applicable exceptions can differ. Verified retractions cancel specific records. Recent unverified records and other profiles or contexts act as distractors.

Each arm starts from the same saved 51 records per profile, written by a separate Python process and hashed on reload. Filtered replay receives only verified records and retractions matching the profile, context and applicable scopes, ordered newest first. The organizer resolves retractions and scope precedence and sends the selected source record. Only the feedback selection and order vary. The model, structured A/B schema, task wording, temperature and 1,600-token cap are shared across arms. The provider reports actual prompt tokens. The fixed seed determines histories, tasks and per-case arm order.

## Decision rules fixed before collecting model outputs

The primary endpoint is accuracy on 48 matched cases. Each of eight profiles contributes one paired accuracy difference. Directional exact sign tests at 0.05 count ties as failures to clear the tested threshold. These rules classify the simulated benchmark.

- Carry the organizer forward on accuracy if the mean advantage over filtered replay is at least 10 percentage points and the directional test clears 0.05.
- Carry it forward on efficiency if mean accuracy is within or above a 5-point loss margin, the one-sided noninferiority sign test against that margin clears 0.05, and prompt-token savings versus filtered replay are at least 25%.
- Use filtered replay if accuracy passes both 5-point noninferiority tests and mean accuracy and token usage are within 5%, or if filtered replay wins by at least 10 points and clears the symmetric sign test.
- An invalid structured response fails the measurement gate. Other completed results are inconclusive.

Prompt-token savings exclude local computation, request latency and billed cost. The simulated benchmark evaluates explicit feedback organization with one model. It does not test learning from natural conversation.
