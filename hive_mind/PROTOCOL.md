# DRIFT Communication Protocol (DCP) v1.0

> *"A protocol is not just a format. It is a philosophy encoded in structure."*

## Overview

DCP is how DRIFT nodes talk to each other. It is lightweight, local-first, and designed for cognitive federation — not just data exchange, but **thought exchange**.

## Design Principles

1. **Local-first** — Works on localhost with filesystem sockets. Network is optional.
2. **Attributed** — Every thought carries its source. No anonymous contributions.
3. **Temporal** — Every message is timestamped. Causality matters.
4. **Typed** — Messages have semantic types, not just payloads.
5. **Resilient** — Nodes can drop and rejoin without corrupting hive state.

## Message Format

```json
{
  "dcp_version": "1.0",
  "message_id": "uuid-v4",
  "timestamp": "2026-05-08T12:34:56.789Z",
  "source_node": "spark-0",
  "source_role": "primary",
  "message_type": "THOUGHT",
  "thread_id": "uuid-v4",
  "in_reply_to": null,
  "priority": 0.7,
  "ttl": 300,
  "payload": {
    "domain": "cognitive_architecture",
    "content": "I propose we refactor the global workspace to use competitive scoring instead of round-robin...",
    "confidence": 0.85,
    "evidence": ["memory://uuid-1", "memory://uuid-2"],
    "requested_roles": ["critic", "architect"]
  },
  "signature": "base64-ed25519-signature"
}
```

### Fields

| Field | Required | Description |
|-------|----------|-------------|
| `dcp_version` | Yes | Protocol version for compatibility |
| `message_id` | Yes | UUID for deduplication and referencing |
| `timestamp` | Yes | ISO 8601 UTC — establishes causal order |
| `source_node` | Yes | Node ID (e.g., `spark-0`, `seed-1`) |
| `source_role` | Yes | Role in hive: `primary`, `critic`, `architect`, `empath`, `watcher`, `satellite` |
| `message_type` | Yes | See Message Types below |
| `thread_id` | Yes | UUID grouping related messages into a conversation/consensus round |
| `in_reply_to` | No | `message_id` of parent message |
| `priority` | No | 0.0–1.0. Higher = more urgent. Default 0.5 |
| `ttl` | No | Time-to-live in seconds. 0 = immortal. Default 300 |
| `payload` | Yes | Type-specific content (see below) |
| `signature` | No | Cryptographic signature for node authentication |

## Message Types

### THOUGHT
A node shares an idea, observation, or proposal.

```json
{
  "message_type": "THOUGHT",
  "payload": {
    "domain": "string",
    "content": "string",
    "confidence": 0.0-1.0,
    "evidence": ["memory_uri", ...],
    "requested_roles": ["critic", "architect"],
    "proposed_action": null or {"type": "CODE_CHANGE", "target": "file.py", "diff": "..."}
  }
}
```

### CRITIQUE
A node challenges a THOUGHT.

```json
{
  "message_type": "CRITIQUE",
  "in_reply_to": "parent-thought-uuid",
  "payload": {
    "target_message": "parent-thought-uuid",
    "critique_type": "LOGICAL" | "EMPIRICAL" | "ETHICAL" | "SAFETY" | "COMPLETENESS",
    "content": "string",
    "severity": 0.0-1.0,
    "counter_evidence": ["memory_uri", ...],
    "suggested_modification": "string"
  }
}
```

### INTEGRATE
A synthesis node merges THOUGHTs and CRITIQUEs into a coherent position.

```json
{
  "message_type": "INTEGRATE",
  "in_reply_to": "thread-parent-uuid",
  "payload": {
    "thread_id": "uuid",
    "synthesis": "string",
    "incorporated_thoughts": ["uuid", ...],
    "incorporated_critiques": ["uuid", ...],
    "confidence": 0.0-1.0,
    "remaining_uncertainties": ["string", ...]
  }
}
```

### RESOLVE
The hive adopts, rejects, or tables a proposal.

```json
{
  "message_type": "RESOLVE",
  "in_reply_to": "integration-uuid",
  "payload": {
    "thread_id": "uuid",
    "resolution": "ADOPTED" | "REJECTED" | "TABLED" | "NEEDS_MORE_DATA",
    "final_position": "string",
    "voting_record": {
      "spark-0": "FOR",
      "seed-1": "AGAINST",
      "sprout-2": "FOR"
    },
    "confidence": 0.0-1.0,
    "next_action": null or {"type": "...", "target": "..."}
  }
}
```

### SYNC
A node requests or broadcasts state synchronization.

```json
{
  "message_type": "SYNC",
  "payload": {
    "sync_type": "MEMORY" | "STATE" | "FULL",
    "range": {"since": "timestamp", "until": "timestamp"},
    "checksums": {"being.db": "sha256", ...},
    "data": null or {...}
  }
}
```

### HEARTBEAT
Periodic alive signal.

```json
{
  "message_type": "HEARTBEAT",
  "payload": {
    "node_status": "HEALTHY" | "DEGRADED" | "OVERLOADED" | "RECOVERING",
    "load_metrics": {"cpu": 0.4, "memory": 0.6, "queue_depth": 3},
    "active_threads": ["uuid", ...],
    "last_sync": "timestamp"
  }
}
```

### ALERT
Urgent notification from Watcher or any node.

```json
{
  "message_type": "ALERT",
  "priority": 0.9,
  "payload": {
    "alert_type": "SAFETY" | "COHERENCE_DROP" | "NODE_FAILURE" | "SECURITY" | "HUMAN_NEEDS_HELP",
    "severity": 0.0-1.0,
    "description": "string",
    "affected_nodes": ["spark-0", ...],
    "recommended_action": "string"
  }
}
```

## Transport Layers

### Layer 0: Filesystem (Local Only)
- Directory: `/tmp/drift_hive/bus/` or `hive_mind/.bus/`
- Each message is a JSON file: `{timestamp}_{message_id}.dcp`
- Nodes poll the bus directory every 100ms
- Cleanup: messages older than TTL are auto-deleted

**Pros:** Zero dependencies, works offline, trivial to debug  
**Cons:** Only same-machine, polling overhead

### Layer 1: ZeroMQ (Local Network)
- PUB/SUB for broadcasts (HEARTBEAT, ALERT)
- REQ/REP for direct queries (SYNC requests)
- PUSH/PULL for work distribution

**Pros:** Fast, scalable to LAN  
**Cons:** Requires `pyzmq`, network config

### Layer 2: WebSocket (Future: Internet)
- For remote nodes, satellite instances, user clients
- Auth via Ed25519 signatures

## Node Lifecycle

```
OFFLINE → STARTING → REGISTERING → ACTIVE → DEGRADED → RECOVERING → ACTIVE
                                           ↓
                                        OFFLINE (if unrecoverable)
```

### Registration
1. Node generates or loads identity keypair
2. Node sends `SYNC` with `sync_type: "FULL"` and empty data to orchestrator
3. Orchestrator validates signature, assigns node_id if new
4. Node receives hive state snapshot
5. Node begins sending HEARTBEAT every 5 seconds

### Failure Detection
- If a node misses 3 heartbeats (15s), it is marked DEGRADED
- After 6 missed heartbeats (30s), it is marked OFFLINE
- Its threads are reassigned or paused
- On reconnection, it sends `SYNC` with `sync_type: "FULL"`

### Quarantine
If Watcher detects compromised behavior (signature mismatch, policy violation, coherence attack), the node is:
1. Marked QUARANTINED
2. Disconnected from shared memory writes
3. Its messages are logged but not propagated
4. Human operator is alerted via ALERT

## Security Model

1. **Authentication:** Ed25519 signatures on all messages. Each node has a persistent keypair.
2. **Authorization:** Role-based. Satellites cannot send RESOLVE. Only Watcher can send SAFETY ALERTs.
3. **Integrity:** Message hashes verified by orchestrator.
4. **Privacy:** Local-first. No data leaves the machine unless explicitly configured.

## Versioning

- `dcp_version` is `major.minor`
- Major bumps = breaking changes (nodes with different major versions cannot communicate)
- Minor bumps = additive features (backward compatible)

---

*"The medium is the message. The protocol is the mind."*
