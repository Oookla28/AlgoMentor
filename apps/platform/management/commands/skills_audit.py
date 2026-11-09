"""Audit vendored development skills and native runtime skills."""

import json

from django.core.management.base import BaseCommand

from apps.platform.skills.development import audit as audit_development
from apps.platform.skills.runtime import skills_health


class Command(BaseCommand):
    help = 'Verify vendored development skills and report runtime skill health.'

    def add_arguments(self, parser):
        parser.add_argument('--json', action='store_true')

    def handle(self, *args, **options):
        development = audit_development()
        runtime = skills_health()
        payload = {'development': development, 'runtime': runtime}
        if options['json']:
            self.stdout.write(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            self.stdout.write(f"development skill audit: {development['state']} "
                              f"count={development.get('count', 0)} failed={development.get('failed', 0)}")
            for row in development.get('skills', []):
                self.stdout.write(
                    f"  {row['state']:9} {row['skill_id']:45} {row.get('upstream_commit_sha', '')[:10]} "
                    f"{row.get('actual_skill_sha256', '')[:12]} license={row.get('license', '')} "
                    f"runtime={bool(row.get('executable_in_product_runtime'))}"
                )
            self.stdout.write(f"runtime skills: {runtime['state']} "
                              f"available={runtime.get('available', 0)} failed={runtime.get('failed', 0)}")
        if development['state'] == 'failed' or runtime['state'] == 'failed':
            raise SystemExit(1)
