# Opt-in feedback organizer pilot

The pilot is available through the one-shot INFJ-Bot CLI on the RCCE research branch. Supply explicit verified feedback and select the profile and decision context on each request.

Example `feedback.json`:

```json
[
  {"review": 1, "profile": "demo", "context": "planning", "scope": "default", "preference": "cheap"},
  {"review": 2, "profile": "demo", "context": "planning", "scope": "urgent", "preference": "fast"},
  {"review": 3, "profile": "demo", "context": "planning", "scope": "urgent", "preference": "cheap"},
  {"review": 4, "profile": "demo", "context": "planning", "scope": "urgent", "retracts": 3}
]
```

```sh
drift ask --rcce-feedback feedback.json --rcce-profile demo --rcce-context planning --rcce-scope urgent "A takes 20 minutes and costs 40 credits. B takes 35 minutes and costs 25 credits. Which should I pick?"
```

The resolver applies verified corrections and chooses the active exception before the default. The example supplies a preference for less time. Omit the scope to use the default. Set `"verified": false` for records that should be ignored. Corrections reference earlier preferences in the same profile, context and scope.

The feedback file is read-only. Only a bounded time-or-cost preference is passed into the ordinary model prompt. The pilot skips the CLI's normal tool calls, post-turn evaluator and interaction save. The CLI can still use its configured model and existing read-side context. This pilot requires explicit feedback and a caller-selected context. The live benchmark evaluates a synthetic A/B decision task. General conversation quality and live CLI behavior are separate measurements.
