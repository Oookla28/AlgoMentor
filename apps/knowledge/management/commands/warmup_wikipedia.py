"""Explicit, rate-limited article prefetch; never runs at application startup."""
import json
from pathlib import Path
import time

from django.core.management.base import BaseCommand, CommandError

from apps.knowledge.services.wikipedia_service import reviewed_keywords, search_wikipedia
from core.exceptions import BusinessError


class Command(BaseCommand):
    help = '按人工审核的关键词预热公共 Wikipedia 缓存；默认跳过有效缓存。'

    def add_arguments(self, parser):
        parser.add_argument('--query', action='append', help='单个概念；可重复使用。')
        parser.add_argument('--keywords', nargs='+', help='显式指定一批公开概念。')
        parser.add_argument('--config', help='人工审核词表 JSON；结构为 {"keywords": [{"query": "...", "en": "..."}]}。')
        parser.add_argument('--language', choices=['zh', 'en'], default='zh')
        parser.add_argument('--interval', type=float, default=1.0, help='概念间请求间隔，至少 0.5 秒。')
        parser.add_argument('--limit', type=int, default=30, help='单次最多处理概念数，范围 1 至 50。')
        parser.add_argument('--force-refresh', action='store_true', help='尝试刷新有效缓存（仍遵守服务冷却）。')

    def handle(self, *args, **options):
        if not 1 <= options['limit'] <= 50 or not 0.5 <= options['interval'] <= 60:
            raise CommandError('limit 须为 1 至 50，interval 须为 0.5 至 60 秒。')
        queries = [*(options['query'] or []), *(options['keywords'] or [])]
        if not queries:
            if options['config']:
                try:
                    items = json.loads(Path(options['config']).read_text(encoding='utf-8'))['keywords']
                    if not isinstance(items, list):
                        raise ValueError()
                except (OSError, ValueError, KeyError, TypeError):
                    raise CommandError('无法读取审核词表 JSON。') from None
            else:
                items = reviewed_keywords()
            try:
                queries = [item.get('en', item['query']) if options['language'] == 'en' else item['query'] for item in items]
            except (TypeError, KeyError, AttributeError):
                raise CommandError('审核词表条目必须含 query。') from None
        if not queries or any(not isinstance(query, str) or not query.strip() for query in queries):
            raise CommandError('审核词表至少需要一个非空公开概念。')
        queries = list(dict.fromkeys(queries))[:options['limit']]
        successful = failed = skipped = 0
        for index, query in enumerate(queries):
            try:
                result = search_wikipedia(query, language=options['language'], force_refresh=options['force_refresh'])
                if result['success'] and not result['from_cache']:
                    successful += 1
                    self.stdout.write(f"成功：{result['language']} / {result['title']} / page_id={result['page_id']}")
                elif result['success'] and result['cache_status'] == 'FRESH' and not result.get('error'):
                    skipped += 1
                    self.stdout.write(f"跳过有效缓存：{result['title']}")
                else:
                    failed += 1
                    self.stdout.write(f"未更新：{result['query']} / {result.get('error') or result.get('cache_warning')}")
            except BusinessError as exc:
                failed += 1
                self.stdout.write(f'未更新：{exc.code}')
            if index < len(queries) - 1:
                time.sleep(options['interval'])
        self.stdout.write(self.style.SUCCESS(f'成功 {successful}；失败 {failed}；跳过有效缓存 {skipped}；合计 {len(queries)}。'))
