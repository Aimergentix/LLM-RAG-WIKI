import os
import re
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Optional

import yaml

# Persona IDs become file basenames under ``personas/``. Reject anything
# that could escape the directory, embed control bytes, or alias a
# reserved control file (``active``, ``meta_directives``).
_PERSONA_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
_RESERVED_IDS = frozenset({"active", "meta_directives"})


def _validate_persona_id(persona_id: str) -> None:
    if not isinstance(persona_id, str) or not _PERSONA_ID_RE.match(persona_id):
        raise ValueError(
            f"[ERR_PERSONA_SCHEMA] invalid persona_id: {persona_id!r} (expected"
            " ^[a-z0-9][a-z0-9_-]{0,63}$)"
        )
    if persona_id in _RESERVED_IDS:
        raise ValueError(f"[ERR_PERSONA_SCHEMA] persona_id {persona_id!r} is reserved")

@dataclass
class Persona:
    id: str
    kind: str  # character | domain
    name: str
    rules: List[str] = field(default_factory=list)
    style_weights: Dict[str, float] = field(default_factory=dict)
    modes: Dict[str, object] = field(default_factory=dict)
    audit_log: List[str] = field(default_factory=list)
    version: str = "1.0.0"

@dataclass
class MetaDirective:
    id: str
    rule: str
    priority: int


@dataclass
class ActiveConfig:
    character: Optional[str] = None
    domains: List[str] = field(default_factory=list)

class PersonaStore:
    def __init__(self, root: Path):
        self.root = root
        self.active_path = root / "active.yaml"
        self.root.mkdir(parents=True, exist_ok=True)

    def load_persona(self, persona_id: str) -> Persona:
        _validate_persona_id(persona_id)
        path = self.root / f"{persona_id}.yaml"
        # Defence in depth: even with a validated id, refuse symlinks so an
        # operator-installed link inside personas/ cannot redirect reads.
        if path.is_symlink():
            raise ValueError(f"[ERR_PERSONA_SCHEMA] persona path is a symlink: {path}")
        try:
            path.resolve().relative_to(self.root.resolve())
        except ValueError:
            raise ValueError("[ERR_PERSONA_SCHEMA] invalid persona_id")
        if not path.exists():
            raise FileNotFoundError(f"[ERR_PERSONA_NOT_FOUND] Persona '{persona_id}' not found")
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)
            return Persona(**data)
        except (yaml.YAMLError, TypeError, ValueError) as e:
            raise ValueError(f"[ERR_PERSONA_SCHEMA] persona '{persona_id}' failed schema: {e}") from e

    def list_personas(self, kind: Optional[str] = None) -> List[Persona]:
        results = []
        for f in self.root.glob("*.yaml"):
            if f.name == "active.yaml" or f.name == "meta_directives.yaml":
                continue
            try:
                with open(f, 'r', encoding='utf-8') as fh:
                    data = yaml.safe_load(fh)
                p = Persona(**data)
            except (yaml.YAMLError, TypeError, ValueError, OSError):
                continue
            if kind is None or p.kind == kind:
                results.append(p)
        return results

    def get_active_config(self) -> ActiveConfig:
        if not self.active_path.exists():
            return ActiveConfig()
        with open(self.active_path, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f) or {}
            return ActiveConfig(
                character=data.get("character"),
                domains=data.get("domains", [])
            )

    def set_active_character(self, persona_id: str):
        config = self.get_active_config()
        # Verify existence
        self.load_persona(persona_id) 
        config.character = persona_id
        self._save_active(config)

    def toggle_domain(self, persona_id: str):
        config = self.get_active_config()
        self.load_persona(persona_id)
        if persona_id in config.domains:
            config.domains.remove(persona_id)
        else:
            config.domains.append(persona_id)
        self._save_active(config)

    def load_meta_directives(self) -> List[MetaDirective]:
        path = self.root / "meta_directives.yaml"
        if not path.exists():
            return []
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f) or {}
            entries = data.get("meta_directives", [])
            return [MetaDirective(**e) for e in entries]
        except (yaml.YAMLError, TypeError, ValueError, AttributeError) as e:
            raise ValueError(f"[ERR_PERSONA_SCHEMA] meta_directives.yaml failed schema: {e}") from e

    def _save_active(self, config: ActiveConfig):
        tmp = self.active_path.with_suffix(".tmp")
        with open(tmp, 'w', encoding='utf-8') as f:
            yaml.safe_dump(asdict(config), f)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, self.active_path)