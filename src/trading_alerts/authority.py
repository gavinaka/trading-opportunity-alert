from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AuthorityBundle:
    text: str
    hashes: dict[str, str]


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def load_authority(root: Path, files: tuple[str, ...]) -> AuthorityBundle:
    sections: list[str] = []
    hashes: dict[str, str] = {}
    missing: list[str] = []
    for relative in files:
        path = root / relative
        if not path.is_file():
            missing.append(relative)
            continue
        text = path.read_text(encoding="utf-8")
        hashes[relative] = sha256_text(text)
        sections.append(f"\n\n===== {relative} =====\n{text}")
    if missing:
        raise FileNotFoundError(
            "Trading-System authority files missing: " + ", ".join(missing)
        )
    return AuthorityBundle(text="".join(sections).strip(), hashes=hashes)

