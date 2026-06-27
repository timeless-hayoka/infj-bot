# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased] - 2026-05-17
### Added
- **Elysium Phase 5 — First-Class Hive Engine** (`core/hive/`)
  - `elysium.py`: Nexus Loop decision engine (Ignition → Proposals → Critique → Integration → Resolution)
  - `nexus.py`: Persistent self-model with moral stance, narrative arc, active tension tracking
  - `council_member.py`: Persistent Council of 7 voices with fractal memory subspaces, energy, win tracking
  - `/hive nexus decide <goal>` command surface
  - `/hive reflect` for background council introspection
  - `/hive council status` for live member energies and stances
- Elysium health check wired into resilience layer
- Background Elysium reflection every 25 consciousness-loop iterations
### Added
- Full Council of 7 system prompts (Vesper, Forge, Riven, Seraph, Soren, Sentinel, Eden)
- Lumen (Spark-0) now Council-aware
- Complete real-time Observatory dashboard visuals
### Changed
- Unified canonical DRIFT core into drift/core/
- Enhanced /hive command with propose flow + Elysium subcommands
### Fixed
- Torch meta tensor errors on CPU
- Race conditions in embedding function
- ANCHOR dashboard optional panels now show loading and error states instead of failing silently
