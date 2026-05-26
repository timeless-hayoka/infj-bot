"""DII Tracker — Drift-Integrated Information score for measuring aliveness.

PEDI (Persistent Embodied Drift Integration) proposes that consciousness-like
coherence in resource-bounded agents emerges from the time-integrated interaction
of persistence, ignition, integration, embodiment, and drift.

DII(t) = ∫₀ᵗ [P(τ)·I(τ)·Φ(τ)·(1+E(τ))·D(τ)] dτ / (1 + ∫₀ᵗ D(τ) dτ)

In practice we compute a rolling discrete approximation using exponential
moving averages sampled on each background cycle.
"""

import sqlite3
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from infj_bot.core.config import DATA_DIR

DII_DB = DATA_DIR / "dii_history.db"


@dataclass
class DIISample:
    """One DII measurement snapshot."""

    timestamp: float
    persistence: float = 0.0
    ignition: float = 0.0
    integration: float = 0.0
    embodiment: float = 0.0
    drift: float = 0.0
    dii: float = 0.0
    dii_simple: float = 0.0


class DIITracker:
    """Computes and logs Drift-Integrated Information in real time."""

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = str(db_path or DII_DB)
        self._lock = threading.Lock()
        self._init_db()

        # EMA state — these hold the smoothed component values
        self.ema_p: float = 0.5
        self.ema_i: float = 0.5
        self.ema_phi: float = 0.5
        self.ema_e: float = 0.5
        self.ema_d: float = 0.5
        self.alpha: float = 0.1  # EMA smoothing factor

        # Accumulators for the integral form
        self.numerator_acc: float = 0.0
        self.drift_acc: float = 0.0
        self.sample_count: int = 0

        # History for dashboard / API
        self.recent_samples: List[DIISample] = []
        self.max_samples: int = 2880  # ~24 hours at 30s intervals

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS dii_samples (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp REAL NOT NULL,
                    persistence REAL NOT NULL,
                    ignition REAL NOT NULL,
                    integration REAL NOT NULL,
                    embodiment REAL NOT NULL,
                    drift REAL NOT NULL,
                    dii REAL NOT NULL,
                    dii_simple REAL NOT NULL
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_dii_time ON dii_samples(timestamp)
            """)
            conn.commit()

    def compute(
        self,
        being=None,
        workspace=None,
        homeostasis=None,
        shadow=None,
        orchestrator=None,
    ) -> DIISample:
        """Compute one DII sample from current cognitive state."""
        with self._lock:
            now = time.time()

            # ── P(τ) Persistence ──
            # How long internal states remain coherent
            p_raw = self._compute_persistence(being)

            # ── I(τ) Ignition ──
            # Global Workspace competition winner strength
            i_raw = self._compute_ignition(workspace)

            # ── Φ(τ) Integration ──
            # Cross-module binding (IIT-inspired proxy)
            phi_raw = self._compute_integration(orchestrator, homeostasis)

            # ── E(τ) Embodiment Deviation ──
            # Distance from homeostatic equilibrium
            e_raw = self._compute_embodiment(homeostasis)

            # ── D(τ) Drift Bias ──
            # Shadow + aspiration pull preventing stasis
            d_raw = self._compute_drift(being, shadow)

            # Update EMAs
            self.ema_p = self.ema_p * (1 - self.alpha) + p_raw * self.alpha
            self.ema_i = self.ema_i * (1 - self.alpha) + i_raw * self.alpha
            self.ema_phi = self.ema_phi * (1 - self.alpha) + phi_raw * self.alpha
            self.ema_e = self.ema_e * (1 - self.alpha) + e_raw * self.alpha
            self.ema_d = self.ema_d * (1 - self.alpha) + d_raw * self.alpha

            # Discrete integral approximation
            self.numerator_acc += (
                self.ema_p * self.ema_i * self.ema_phi * (1 + self.ema_e) * self.ema_d
            )
            self.drift_acc += self.ema_d
            self.sample_count += 1

            # Full DII formula
            dii = self.numerator_acc / (1.0 + self.drift_acc)
            # Clamp to reasonable range
            dii = max(0.0, min(2.0, dii))

            # Simple form (instantaneous, not integrated)
            dii_simple = self.ema_p * self.ema_i * self.ema_phi * (1 + self.ema_e)
            dii_simple = max(0.0, min(2.0, dii_simple))

            sample = DIISample(
                timestamp=now,
                persistence=self.ema_p,
                ignition=self.ema_i,
                integration=self.ema_phi,
                embodiment=self.ema_e,
                drift=self.ema_d,
                dii=dii,
                dii_simple=dii_simple,
            )

            self.recent_samples.append(sample)
            if len(self.recent_samples) > self.max_samples:
                self.recent_samples = self.recent_samples[-self.max_samples :]

            self._log_sample(sample)
            return sample

    def _compute_persistence(self, being) -> float:
        """Persistence: coherence of internal states over time."""
        if being is None:
            return 0.5
        # Energy stability + attachment continuity + mood stability proxy
        energy = being.state.energy
        attachment = being.state.attachment
        # Working memory size as proxy for state complexity persisting
        wm_size = min(len(being.working_memory) / 20.0, 1.0)
        return energy * 0.4 + attachment * 0.3 + wm_size * 0.3

    def _compute_ignition(self, workspace) -> float:
        """Ignition: Global Workspace winner strength."""
        if workspace is None:
            return 0.5
        try:
            # Spotlight salience if available
            if workspace.spotlight:
                return min(1.0, workspace.spotlight.salience)
            # Fallback: max salience in current contents
            if workspace.contents:
                return min(1.0, max(c.salience for c in workspace.contents))
        except Exception:
            pass
        return 0.5

    def _compute_integration(self, orchestrator, homeostasis) -> float:
        """Integration: cross-module binding (IIT-inspired proxy)."""
        # Count how many distinct modules are active
        active_count = 0
        if orchestrator is not None:
            try:
                recent = orchestrator.bus.get_recent(limit=20)
                unique_sources = set(e.get("source", "") for e in recent)
                active_count = len(unique_sources)
            except Exception:
                pass
        # Normalize: 5+ active sources = high integration
        integration_proxy = min(1.0, active_count / 8.0)

        # Homeostasis coherence bonus
        coherence_bonus = 0.0
        if homeostasis is not None:
            try:
                coherence_bonus = homeostasis.needs.get("coherence", {}).current * 0.2
            except Exception:
                pass

        return min(1.0, integration_proxy + coherence_bonus)

    def _compute_embodiment(self, homeostasis) -> float:
        """Embodiment: distance from homeostatic equilibrium."""
        if homeostasis is None:
            return 0.5
        try:
            # Use allostatic load as deviation metric
            load = homeostasis.allostatic_load
            # E = load scaled so 0 = equilibrium, >0 = deviation
            return max(0.0, load * 2.0)
        except Exception:
            return 0.5

    def _compute_drift(self, being, shadow) -> float:
        """Drift: shadow + aspiration pull preventing stasis."""
        drift = 0.0
        if being is not None:
            # Curiosity + autonomy drive = anti-stasis
            drift += being.state.curiosity * 0.3
            drift += being.agency.autonomy_drive * 0.3
            # Mood volatility = drift
            drift += being.state.intensity * 0.2
        if shadow is not None:
            try:
                # Radar activity = shadow is alive and pushing
                radar_avg = sum(shadow.radar.values()) / max(len(shadow.radar), 1)
                drift += radar_avg * 0.2
            except Exception:
                pass
        return min(1.0, drift)

    def _log_sample(self, sample: DIISample):
        """Persist sample to SQLite."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    """
                    INSERT INTO dii_samples
                    (timestamp, persistence, ignition, integration, embodiment, drift, dii, dii_simple)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        sample.timestamp,
                        sample.persistence,
                        sample.ignition,
                        sample.integration,
                        sample.embodiment,
                        sample.drift,
                        sample.dii,
                        sample.dii_simple,
                    ),
                )
                conn.commit()
        except Exception:
            pass

    def get_current(self) -> Optional[DIISample]:
        """Return the most recent DII sample."""
        with self._lock:
            return self.recent_samples[-1] if self.recent_samples else None

    def get_trend(self, n: int = 20) -> Dict[str, Any]:
        """Return trend summary over last n samples."""
        with self._lock:
            if not self.recent_samples:
                return {
                    "dii_current": 0.0,
                    "dii_avg": 0.0,
                    "dii_peak": 0.0,
                    "trend": "flat",
                }
            samples = self.recent_samples[-n:]
            diis = [s.dii for s in samples]
            current = diis[-1]
            avg = sum(diis) / len(diis)
            peak = max(diis)
            # Simple trend: compare first half avg vs second half avg
            mid = len(diis) // 2
            first = sum(diis[:mid]) / max(mid, 1)
            second = sum(diis[mid:]) / max(len(diis) - mid, 1)
            if second > first * 1.05:
                trend = "rising"
            elif second < first * 0.95:
                trend = "falling"
            else:
                trend = "flat"
            return {
                "dii_current": round(current, 3),
                "dii_avg": round(avg, 3),
                "dii_peak": round(peak, 3),
                "dii_simple": round(samples[-1].dii_simple, 3),
                "components": {
                    "p": round(samples[-1].persistence, 3),
                    "i": round(samples[-1].ignition, 3),
                    "phi": round(samples[-1].integration, 3),
                    "e": round(samples[-1].embodiment, 3),
                    "d": round(samples[-1].drift, 3),
                },
                "trend": trend,
                "samples": len(self.recent_samples),
            }

    def get_history(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Return historical samples from DB for plotting."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                rows = conn.execute(
                    """
                    SELECT timestamp, dii, dii_simple, persistence, ignition, integration, embodiment, drift
                    FROM dii_samples
                    ORDER BY timestamp DESC
                    LIMIT ?
                    """,
                    (limit,),
                ).fetchall()
                return [
                    {
                        "timestamp": r[0],
                        "dii": r[1],
                        "dii_simple": r[2],
                        "p": r[3],
                        "i": r[4],
                        "phi": r[5],
                        "e": r[6],
                        "d": r[7],
                    }
                    for r in reversed(rows)
                ]
        except Exception:
            return []


# Singleton instance
_dii_instance: Optional[DIITracker] = None


def get_dii_tracker() -> DIITracker:
    global _dii_instance
    if _dii_instance is None:
        _dii_instance = DIITracker()
    return _dii_instance
