"""Pluggable domain/task manifests. Core agent code must not branch on domain id."""

from dataclasses import asdict, dataclass, field


@dataclass(frozen=True)
class DomainPack:
    pack_id: str
    version: str
    name: str
    description: str = ''
    capabilities: tuple[str, ...] = ()
    document_profile: dict = field(default_factory=dict)
    chunk_policy: dict = field(default_factory=dict)
    metadata_schema: dict = field(default_factory=dict)
    authority_policy: dict = field(default_factory=dict)
    freshness_policy: dict = field(default_factory=dict)
    prompt_policy: dict = field(default_factory=dict)
    tool_manifest: tuple[str, ...] = ()
    evaluation_cases: tuple[str, ...] = ()

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class TaskPack:
    task_id: str
    domain_pack_id: str
    version: str
    name: str
    description: str = ''
    required_capabilities: tuple[str, ...] = ()
    tool_ids: tuple[str, ...] = ()
    evaluation_case_ids: tuple[str, ...] = ()

    def to_dict(self) -> dict:
        return asdict(self)
