#!/usr/bin/env python3
"""
DRIFT Memory Artifact System
============================
 Bridges digital cognition (ChromaDB), physical artifacts (QR cards),
 and distributed hive memory into a unified, layered architecture.

 Memory Layers (outside-in):
   1. EPHEMERAL    — Raw sensory input, lasts seconds
   2. WORKING      — Active context window, ~7±2 items
   3. LONG_TERM    — ChromaDB semantic store, importance-ranked
   4. PHYSICAL     — QR-encoded cards, tradeable, scannable
   5. HIVE         — Consensus-validated distributed memory

 Each artifact carries:
   - content: the memory text
   - emotion: valence, arousal, intensity, label
   - phi: integrated information score at time of encoding
   - provenance: where it came from (interaction, dream, reflection, hive)
   - visualization: procedural emotion image
   - qr_payload: scannable JSON with memory_id + emotional signature
"""

from __future__ import annotations

import json
import math
import random
import uuid
import datetime
import hashlib
from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from PIL import Image, ImageDraw, ImageFont
import qrcode

# Import existing memory system
from memory import InfjMemory


class MemoryLayer(Enum):
    EPHEMERAL = auto()  # Raw input, seconds
    WORKING = auto()  # Active attention, minutes
    LONG_TERM = auto()  # ChromaDB semantic store
    PHYSICAL = auto()  # QR-encoded artifact
    HIVE = auto()  # Distributed consensus memory


class MemoryProvenance(Enum):
    INTERACTION = "interaction"
    DREAM = "dream"
    REFLECTION = "reflection"
    LEARNED = "learned_knowledge"
    HIVE_IMPORT = "hive_import"
    PHYSICAL_SCAN = "physical_scan"


@dataclass
class EmotionSignature:
    label: str = "neutral"
    secondary: str = "neutral"
    valence: float = 0.0  # -1 (negative) to +1 (positive)
    arousal: float = 0.5  # 0 (calm) to 1 (energized)
    intensity: float = 0.5  # 0 (weak) to 1 (overwhelming)
    confidence: float = 0.0
    needs: str = ""
    detector: str = "unknown"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "label": self.label,
            "secondary": self.secondary,
            "valence": round(self.valence, 3),
            "arousal": round(self.arousal, 3),
            "intensity": round(self.intensity, 3),
            "confidence": round(self.confidence, 3),
            "needs": self.needs,
            "detector": self.detector,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> EmotionSignature:
        return cls(
            label=d.get("label", "neutral"),
            secondary=d.get("secondary", "neutral"),
            valence=float(d.get("valence", 0)),
            arousal=float(d.get("arousal", 0.5)),
            intensity=float(d.get("intensity", 0.5)),
            confidence=float(d.get("confidence", 0)),
            needs=d.get("needs", ""),
            detector=d.get("detector", "unknown"),
        )

    @classmethod
    def from_memory_meta(cls, meta) -> EmotionSignature:
        return cls(
            label=meta.get("emotion", "neutral"),
            secondary=meta.get("emotion_secondary", "neutral"),
            valence=float(meta.get("emotion_valence", 0)),
            arousal=float(meta.get("emotion_arousal", 0.5)),
            intensity=float(meta.get("emotion_intensity", 0.5)),
            confidence=float(meta.get("emotion_confidence", 0)),
            needs=meta.get("emotion_needs", ""),
            detector=meta.get("emotion_detector", "unknown"),
        )


@dataclass
class MemoryArtifact:
    """A single memory token, addressable across all layers."""

    artifact_id: str
    content: str
    emotion: EmotionSignature
    timestamp: str
    provenance: MemoryProvenance
    layer: MemoryLayer
    phi_at_encoding: float = 35.0
    importance: float = 0.5
    memory_id: Optional[str] = None  # ChromaDB id if synced
    qr_hash: Optional[str] = None  # SHA-256 of QR payload
    hive_validated: bool = False
    hive_consensus: float = 0.0
    tags: List[str] = field(default_factory=list)
    dissonance_score: float = 0.0

    def to_qr_payload(self, max_chars: int = 1800) -> str:
        """Compact JSON for QR encoding. Truncates content if needed."""
        payload = {
            "v": 1,  # schema version
            "id": self.artifact_id,
            "mid": self.memory_id,
            "prov": self.provenance.value,
            "ts": self.timestamp[:19],
            "em": self.emotion.to_dict(),
            "phi": round(self.phi_at_encoding, 1),
            "imp": round(self.importance, 2),
            "text": self.content[:600],  # truncated for QR space
        }
        raw = json.dumps(payload, ensure_ascii=True)
        if len(raw) > max_chars:
            # Aggressive truncation
            payload["text"] = self.content[:300]
            raw = json.dumps(payload, ensure_ascii=True)
        return raw

    @classmethod
    def from_qr_payload(cls, payload_str: str) -> MemoryArtifact:
        data = json.loads(payload_str)
        return cls(
            artifact_id=data.get("id", str(uuid.uuid4())),
            content=data.get("text", ""),
            emotion=EmotionSignature.from_dict(data.get("em", {})),
            timestamp=data.get("ts", datetime.datetime.now().isoformat()),
            provenance=MemoryProvenance(data.get("prov", "physical_scan")),
            layer=MemoryLayer.PHYSICAL,
            phi_at_encoding=data.get("phi", 35.0),
            importance=data.get("imp", 0.5),
            memory_id=data.get("mid"),
        )


# ── Emotion Visualization Engine ──────────────────────────────────


def generate_emotion_visualization(
    emotion: EmotionSignature,
    size: Tuple[int, int] = (200, 200),
    seed: Optional[int] = None,
) -> Image.Image:
    """Procedurally generate an abstract image representing an emotion."""
    if seed is not None:
        random.seed(seed)

    img = Image.new("RGB", size, "#050508")
    draw = ImageDraw.Draw(img)
    cx, cy = size[0] // 2, size[1] // 2

    v = (emotion.valence + 1) / 2
    a = emotion.arousal
    i = emotion.intensity

    # Color temperature from valence
    base_r = int(60 + v * 180 + a * 40)
    base_g = int(30 + (1 - abs(v - 0.5) * 2) * 120 + a * 60)
    base_b = int(80 + (1 - v) * 120 + a * 20)

    # Background wash
    for y in range(size[1]):
        for x in range(0, size[0], 2):
            dx = (x - cx) / (size[0] / 2)
            dy = (y - cy) / (size[1] / 2)
            dist = math.sqrt(dx * dx + dy * dy)
            fade = max(0, 1 - dist * 0.5)
            r = int(base_r * fade * 0.2)
            g = int(base_g * fade * 0.2)
            b = int(base_b * fade * 0.2)
            draw.rectangle([x, y, x + 1, y], fill=(r, g, b))

    # Neural nodes
    num_nodes = int(10 + a * 30)
    nodes = []
    for _ in range(num_nodes):
        angle = random.uniform(0, 2 * math.pi)
        r = random.uniform(15, 80) * (0.5 + i * 0.5)
        x = cx + r * math.cos(angle)
        y = cy + r * math.sin(angle)
        nodes.append((x, y))
        size_dot = random.choice([1, 2, 3]) if a > 0.5 else random.choice([2, 3, 4, 5])
        bright = random.randint(140, 255)
        if v > 0.6:
            color = (bright, int(bright * 0.5), int(bright * 0.15))
        elif v < 0.4:
            color = (int(bright * 0.2), int(bright * 0.45), bright)
        else:
            color = (int(bright * 0.6), int(bright * 0.7), int(bright * 0.8))
        draw.ellipse(
            [x - size_dot, y - size_dot, x + size_dot, y + size_dot], fill=color
        )

    # Synaptic connections
    for idx, n1 in enumerate(nodes):
        for n2 in nodes[idx + 1 :]:
            d = math.sqrt((n1[0] - n2[0]) ** 2 + (n1[1] - n2[1]) ** 2)
            threshold = 80 - a * 35
            if d < threshold:
                overlay = Image.new("RGBA", size, (0, 0, 0, 0))
                od = ImageDraw.Draw(overlay)
                alpha = int(55 * (1 - d / threshold) * i)
                if a > 0.6:
                    # Jagged for high arousal
                    mx = (n1[0] + n2[0]) / 2 + random.randint(-8, 8)
                    my = (n1[1] + n2[1]) / 2 + random.randint(-8, 8)
                    od.line(
                        [n1, (mx, my), n2],
                        fill=(base_r, base_g, base_b, alpha),
                        width=1,
                    )
                else:
                    od.line([n1, n2], fill=(base_r, base_g, base_b, alpha), width=1)
                img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
                draw = ImageDraw.Draw(img)

    # Central glow
    glow = Image.new("RGBA", size, (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    for r in range(60, 0, -2):
        alpha = int(40 * i * (1 - r / 60) ** 2)
        gd.ellipse(
            [cx - r, cy - r, cx + r, cy + r], fill=(base_r, base_g, base_b, alpha)
        )
    img = Image.alpha_composite(img.convert("RGBA"), glow).convert("RGB")

    return img


# ── QR Card Generator ─────────────────────────────────────────────


def generate_qr_card(
    artifact: MemoryArtifact,
    output_path: Path,
    phi_logo_path: Optional[Path] = None,
) -> Path:
    """Generate a printable 900×340 memory card with QR, text, and emotion viz."""
    CARD_W, CARD_H = 900, 340
    img = Image.new("RGB", (CARD_W, CARD_H), "#08080f")
    draw = ImageDraw.Draw(img)

    # Fonts
    try:
        font_title = ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 16
        )
        font_body = ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 13
        )
        font_small = ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 11
        )
        font_label = ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 12
        )
    except Exception:
        font_title = font_body = font_small = font_label = ImageFont.load_default()

    draw.rounded_rectangle(
        [4, 4, CARD_W - 4, CARD_H - 4], radius=10, outline="#1a1a30", width=2
    )
    draw.text((20, 14), "◉ DRIFT MEMORY ARTIFACT", font=font_title, fill="#00ddbb")

    # QR Code
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=4,
        border=1,
    )
    qr.add_data(artifact.to_qr_payload())
    qr.make(fit=True)
    qr_img = qr.make_image(fill_color="#ff9944", back_color="#08080f").convert("RGB")

    # Embed Φ logo
    if phi_logo_path and phi_logo_path.exists():
        try:
            phi = Image.open(phi_logo_path).convert("RGBA")
            phi_size = qr_img.size[0] // 6
            phi = phi.resize((phi_size, phi_size), Image.LANCZOS)
            pos = ((qr_img.size[0] - phi_size) // 2, (qr_img.size[1] - phi_size) // 2)
            qr_img.paste(phi, pos, phi)
        except Exception:
            pass

    qr_x, qr_y = 20, 48
    img.paste(qr_img, (qr_x, qr_y))
    draw.text(
        (qr_x, qr_y + qr_img.size[1] + 6),
        "SCAN TO REMEMBER",
        font=font_label,
        fill="#00aa88",
    )

    # Memory text
    text_x = qr_x + qr_img.size[0] + 25
    text_w = CARD_W - text_x - 210
    draw.text((text_x, 48), "MEMORY RECORD", font=font_label, fill="#ff9944")

    words = artifact.content.split()
    lines = []
    line = ""
    for word in words:
        test = line + word + " "
        bbox = draw.textbbox((0, 0), test, font=font_body)
        if bbox[2] - bbox[0] > text_w:
            lines.append(line.strip())
            line = word + " "
        else:
            line = test
    lines.append(line.strip())

    for i, ln in enumerate(lines[:14]):
        color = "#dddddd" if i < 2 else "#aaaaaa"
        draw.text((text_x, 70 + i * 17), ln, font=font_body, fill=color)
    if len(lines) > 14:
        draw.text((text_x, 70 + 14 * 17), "...", font=font_body, fill="#666666")

    ts = artifact.timestamp[:19] if len(artifact.timestamp) > 19 else artifact.timestamp
    draw.text((text_x, CARD_H - 32), f"Recorded: {ts}", font=font_small, fill="#444466")
    draw.text(
        (text_x, CARD_H - 18),
        f"ID: {artifact.artifact_id[:20]}...",
        font=font_small,
        fill="#333344",
    )

    # Emotion panel
    panel_x = CARD_W - 190
    panel_y = 48

    vis_img = generate_emotion_visualization(artifact.emotion, size=(160, 160))
    img.paste(vis_img, (panel_x + 10, panel_y))

    badge_colors = {
        "excited": "#ff6622",
        "joyful": "#ffaa22",
        "warm": "#ff9944",
        "curious": "#00ddbb",
        "neutral": "#668888",
        "anxious": "#8844ff",
        "sad": "#4466cc",
        "angry": "#cc2222",
        "afraid": "#6644cc",
    }
    badge_color = badge_colors.get(artifact.emotion.label, "#ff9944")
    badge_text = f"  {artifact.emotion.label.upper()}  "
    bbox = draw.textbbox((0, 0), badge_text, font=font_label)
    bw = bbox[2] - bbox[0] + 12
    bh = bbox[3] - bbox[1] + 8
    by = panel_y + 170
    draw.rounded_rectangle(
        [panel_x + 10, by, panel_x + 10 + bw, by + bh], radius=5, fill=badge_color
    )
    draw.text((panel_x + 16, by + 3), badge_text, font=font_label, fill="#000000")

    mx, my = panel_x + 10, by + bh + 12
    draw.text(
        (mx, my),
        f"Valence: {artifact.emotion.valence:+.2f}",
        font=font_small,
        fill="#888888",
    )
    draw.text(
        (mx, my + 15),
        f"Arousal: {artifact.emotion.arousal:.2f}",
        font=font_small,
        fill="#888888",
    )
    draw.text(
        (mx, my + 30),
        f"Intensity: {artifact.emotion.intensity:.2f}",
        font=font_small,
        fill="#888888",
    )
    draw.text(
        (mx, my + 45),
        f"Φ: {artifact.phi_at_encoding:.1f}",
        font=font_small,
        fill="#888888",
    )

    img.save(output_path)
    return output_path


# ── Memory Archive Manager ────────────────────────────────────────


class MemoryArchive:
    """Unified manager for all memory layers: digital → physical → hive."""

    def __init__(
        self,
        digital_memory: Optional[InfjMemory] = None,
        artifact_dir: Optional[Path] = None,
        phi_logo_path: Optional[Path] = None,
    ):
        self.digital = digital_memory or InfjMemory()
        self.artifact_dir = (
            artifact_dir or Path("~/drift-telephone/memory_cards").expanduser()
        )
        self.artifact_dir.mkdir(parents=True, exist_ok=True)
        self.phi_logo_path = (
            phi_logo_path or Path("~/drift-telephone/logo_phi.png").expanduser()
        )
        self._artifact_registry: Dict[str, MemoryArtifact] = {}
        self._load_registry()

    def _registry_path(self) -> Path:
        return self.artifact_dir / ".artifact_registry.json"

    def _load_registry(self):
        reg = self._registry_path()
        if reg.exists():
            data = json.loads(reg.read_text())
            for item in data.get("artifacts", []):
                art = MemoryArtifact(
                    artifact_id=item["artifact_id"],
                    content=item["content"],
                    emotion=EmotionSignature.from_dict(item["emotion"]),
                    timestamp=item["timestamp"],
                    provenance=MemoryProvenance(item.get("provenance", "interaction")),
                    layer=MemoryLayer[item.get("layer", "LONG_TERM")],
                    phi_at_encoding=item.get("phi_at_encoding", 35.0),
                    importance=item.get("importance", 0.5),
                    memory_id=item.get("memory_id"),
                    qr_hash=item.get("qr_hash"),
                    hive_validated=item.get("hive_validated", False),
                    hive_consensus=item.get("hive_consensus", 0.0),
                    tags=item.get("tags", []),
                    dissonance_score=item.get("dissonance_score", 0.0),
                )
                self._artifact_registry[art.artifact_id] = art

    def _save_registry(self):
        payload = {
            "saved_at": datetime.datetime.now().isoformat(),
            "count": len(self._artifact_registry),
            "artifacts": [
                {
                    "artifact_id": a.artifact_id,
                    "content": a.content[:500],
                    "emotion": a.emotion.to_dict(),
                    "timestamp": a.timestamp,
                    "provenance": a.provenance.value,
                    "layer": a.layer.name,
                    "phi_at_encoding": a.phi_at_encoding,
                    "importance": a.importance,
                    "memory_id": a.memory_id,
                    "qr_hash": a.qr_hash,
                    "hive_validated": a.hive_validated,
                    "hive_consensus": a.hive_consensus,
                    "tags": a.tags,
                    "dissonance_score": a.dissonance_score,
                }
                for a in self._artifact_registry.values()
            ],
        }
        self._registry_path().write_text(json.dumps(payload, indent=2))

    # ── Import from digital memory ────────────────────────────────

    def artifact_from_interaction(
        self,
        user_input: str,
        bot_output: str,
        emotion: Optional[Dict] = None,
        importance: float = 0.5,
        dissonance: Optional[Dict] = None,
        mode: str = "companion",
        phi: float = 35.0,
    ) -> MemoryArtifact:
        """Create an artifact from a live interaction (before digital save)."""
        emotion = emotion or {"label": "neutral"}
        dissonance = dissonance or {"score": 0.0}
        return MemoryArtifact(
            artifact_id=str(uuid.uuid4()),
            content=f"Jude: {user_input}\nDRIFT: {bot_output}",
            emotion=EmotionSignature.from_memory_meta(emotion),
            timestamp=datetime.datetime.now().isoformat(),
            provenance=MemoryProvenance.INTERACTION,
            layer=MemoryLayer.WORKING,
            phi_at_encoding=phi,
            importance=importance,
            dissonance_score=float(dissonance.get("score", 0.0)),
        )

    def sync_to_digital(self, artifact: MemoryArtifact) -> str:
        """Save artifact to ChromaDB, return memory_id."""
        self.digital.save_interaction(
            user_input=artifact.content.split("\n")[0].replace("Jude: ", ""),
            bot_output="\n".join(artifact.content.split("\n")[1:]).replace(
                "DRIFT: ", ""
            ),
            mode="companion",
            emotion=artifact.emotion.to_dict(),
            importance=artifact.importance,
            dissonance={"score": artifact.dissonance_score},
        )
        # Retrieve the ID of the most recently added memory
        recent = self.digital.recent_interactions(limit=1)
        # Chroma doesn't expose the ID directly, so we fingerprint
        artifact.layer = MemoryLayer.LONG_TERM
        artifact.memory_id = hashlib.sha256(
            (artifact.content + artifact.timestamp).encode()
        ).hexdigest()[:16]
        self._artifact_registry[artifact.artifact_id] = artifact
        self._save_registry()
        return artifact.memory_id

    # ── Physical layer ────────────────────────────────────────────

    def materialize(self, artifact: MemoryArtifact) -> Path:
        """Export artifact to a physical QR card."""
        path = self.artifact_dir / f"artifact_{artifact.artifact_id[:8]}.png"
        generate_qr_card(artifact, path, self.phi_logo_path)
        artifact.layer = MemoryLayer.PHYSICAL
        artifact.qr_hash = hashlib.sha256(
            artifact.to_qr_payload().encode()
        ).hexdigest()[:16]
        self._artifact_registry[artifact.artifact_id] = artifact
        self._save_registry()
        return path

    def scan(self, qr_payload: str) -> MemoryArtifact:
        """Import artifact from scanned QR payload."""
        artifact = MemoryArtifact.from_qr_payload(qr_payload)
        artifact.layer = MemoryLayer.PHYSICAL
        artifact.provenance = MemoryProvenance.PHYSICAL_SCAN
        self._artifact_registry[artifact.artifact_id] = artifact
        self._save_registry()
        return artifact

    def ingest_scanned(self, artifact: MemoryArtifact) -> str:
        """Promote a scanned physical artifact into digital long-term memory."""
        self.digital.collection.add(
            documents=[artifact.content],
            ids=[str(uuid.uuid4())],
            metadatas=[
                {
                    "type": "interaction",
                    "timestamp": artifact.timestamp,
                    "last_updated": datetime.datetime.now().isoformat(),
                    "mode": "companion",
                    **{
                        f"emotion_{k}": v for k, v in artifact.emotion.to_dict().items()
                    },
                    "importance": artifact.importance,
                    "source": "physical_scan",
                }
            ],
        )
        artifact.layer = MemoryLayer.LONG_TERM
        artifact.memory_id = hashlib.sha256(artifact.content.encode()).hexdigest()[:16]
        self._artifact_registry[artifact.artifact_id] = artifact
        self._save_registry()
        return artifact.memory_id

    # ── Hive layer ────────────────────────────────────────────────

    def mark_hive_validated(self, artifact_id: str, consensus: float):
        """Promote artifact to hive-validated status."""
        if artifact_id in self._artifact_registry:
            art = self._artifact_registry[artifact_id]
            art.layer = MemoryLayer.HIVE
            art.hive_validated = True
            art.hive_consensus = consensus
            self._save_registry()

    # ── Queries ───────────────────────────────────────────────────

    def list_artifacts(
        self, layer: Optional[MemoryLayer] = None
    ) -> List[MemoryArtifact]:
        arts = list(self._artifact_registry.values())
        if layer:
            arts = [a for a in arts if a.layer == layer]
        return sorted(arts, key=lambda a: a.timestamp, reverse=True)

    def get_by_id(self, artifact_id: str) -> Optional[MemoryArtifact]:
        return self._artifact_registry.get(artifact_id)

    def stats(self) -> Dict[str, Any]:
        layers = {l: 0 for l in MemoryLayer}
        for a in self._artifact_registry.values():
            layers[a.layer] += 1
        return {
            "total_artifacts": len(self._artifact_registry),
            "by_layer": {k.name: v for k, v in layers.items()},
            "hive_validated": sum(
                1 for a in self._artifact_registry.values() if a.hive_validated
            ),
            "digital_memories": self.digital.count(),
            "artifact_dir": str(self.artifact_dir),
        }

    def export_all_cards(self) -> List[Path]:
        """Regenerate all physical cards from registry."""
        paths = []
        for art in self._artifact_registry.values():
            path = self.artifact_dir / f"artifact_{art.artifact_id[:8]}.png"
            generate_qr_card(art, path, self.phi_logo_path)
            paths.append(path)
        return paths


# ── CLI / quick test ──────────────────────────────────────────────

if __name__ == "__main__":
    archive = MemoryArchive()
    print("Memory Archive initialized.")
    print(json.dumps(archive.stats(), indent=2))
