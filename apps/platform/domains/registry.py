"""Domain/task pack registry. Lookup is by id; no caller branches on a domain name."""

from . import data_structures, general_documents, generic, research_literature, software_engineering, task_packs


def _builders():
    return {
        'data_structures': data_structures.build_domain_pack,
        'general_documents': general_documents.build_domain_pack,
        'generic': generic.build_domain_pack,
        'research_literature': research_literature.build_domain_pack,
        'software_engineering': software_engineering.build_domain_pack,
    }


def list_domain_packs():
    return [builder() for builder in _builders().values()]


def get_domain_pack(pack_id: str):
    builder = _builders().get(pack_id)
    if builder is None:
        return None
    return builder()


def list_task_packs(pack_id: str | None = None):
    packs = []
    for module in (data_structures, general_documents, generic, research_literature, software_engineering):
        for task in module.build_task_packs():
            if pack_id is None or task.domain_pack_id == pack_id:
                packs.append(task)
    for task in task_packs.build_task_packs():
        if pack_id is None or task.domain_pack_id in (pack_id, '*'):
            packs.append(task)
    return packs


def get_task_pack(task_id: str, pack_id: str):
    for task in list_task_packs(pack_id):
        if task.task_id == task_id:
            return task
    return None


def sync_manifests():
    """Persist manifests for admin inspection without changing runtime lookup."""
    from apps.platform.models import DomainPack as DomainPackRow, TaskPack as TaskPackRow
    rows = 0
    for pack in list_domain_packs():
        DomainPackRow.objects.update_or_create(
            pack_id=pack.pack_id, version=pack.version,
            defaults={'name': pack.name, 'description': pack.description, 'manifest': pack.to_dict(), 'is_active': True},
        )
        rows += 1
    for task in list_task_packs():
        TaskPackRow.objects.update_or_create(
            task_id=task.task_id, version=task.version,
            defaults={
                'domain_pack_id': task.domain_pack_id, 'name': task.name,
                'description': task.description, 'manifest': task.to_dict(), 'is_active': True,
            },
        )
        rows += 1
    return rows
