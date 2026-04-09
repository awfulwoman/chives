from __future__ import annotations
from pathlib import Path
from chives.config import Config
from chives.store import Store


def build_context(config: Config, store: Store, current_message: str = "") -> str:
    parts: list[str] = []

    profile = Path(config.profile_path)
    for fname in ("PERSONALITY.md", "USER.md", "PROTOCOLS.md"):
        fpath = profile / fname
        if fpath.exists():
            parts.append(fpath.read_text().strip())

    memories = store.get_all_memories()
    if memories:
        recent = memories[-20:]
        hits = [m["fact"] for m in recent]
        if current_message:
            words = set(current_message.lower().split())
            hits = sorted(
                hits,
                key=lambda f: sum(w in f.lower() for w in words),
                reverse=True,
            )
        parts.append("## What I know about the user\n" + "\n".join(f"- {h}" for h in hits))

    return "\n\n---\n\n".join(parts)
