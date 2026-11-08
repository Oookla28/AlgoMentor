import pytest

from apps.platform.capabilities import capability_map, probe_capabilities
from apps.platform.domains import get_domain_pack, list_domain_packs, list_task_packs, sync_manifests
from apps.platform.tools import list_tool_specs


def test_domain_packs_are_pluggable_and_distinct():
    packs = {pack.pack_id: pack for pack in list_domain_packs()}
    assert set(packs) == {'data_structures', 'general_documents'}
    assert packs['data_structures'].chunk_policy['child_token_max'] > 0
    assert packs['data_structures'].authority_policy['official_course_level'] == 1
    assert packs['general_documents'].authority_policy['official_course_level'] == 3
    assert get_domain_pack('missing') is None
    assert any(task.domain_pack_id == 'general_documents' for task in list_task_packs())


def test_tool_specs_declare_permissions_timeouts_and_costs():
    specs = {spec['tool_id']: spec for spec in list_tool_specs()}
    assert 'keyword_search' in specs and 'read_parent' in specs
    assert all(spec['permission'] == 'read' for spec in specs.values())
    assert all(spec['timeout_seconds'] > 0 and spec['budget_cost'] >= 1 for spec in specs.values())


@pytest.mark.django_db
def test_capability_probe_uses_explicit_state_vocabulary():
    entries = probe_capabilities()
    names = {entry['name'] for entry in entries}
    assert {'django', 'database', 'legacy_index', 'advanced_index', 'embedding', 'reranker', 'llm', 'piston', 'ocr', 'asr', 'keyframes', 'wikipedia'} <= names
    allowed = {'available', 'fallback', 'disabled', 'environment-limited', 'unverified', 'not-configured'}
    assert all(entry['state'] in allowed for entry in entries)
    mapping = capability_map()
    assert mapping['django']['state'] == 'available'
    assert mapping['llm']['details']['network_probe'] is False


@pytest.mark.django_db
def test_sync_manifests_persists_both_domains():
    count = sync_manifests()
    assert count >= 4
    from apps.platform.models import DomainPack, TaskPack
    assert DomainPack.objects.filter(pack_id='data_structures').exists()
    assert DomainPack.objects.filter(pack_id='general_documents').exists()
    assert TaskPack.objects.filter(domain_pack_id='general_documents').exists()
