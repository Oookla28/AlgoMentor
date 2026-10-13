"""Explicit administrative model download; normal queries use local files only."""
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = '联网准备当前配置的本地 BGE 模型；不会更换模型或重建课程索引。'

    def add_arguments(self, parser):
        parser.add_argument('--check-only', action='store_true', help='只检查已有模型缓存，不访问外网。')

    def handle(self, *args, **options):
        if settings.EMBEDDING_PROVIDER != 'bge':
            self.stdout.write('当前显式选择词法基线，无需下载 BGE。')
            return
        from huggingface_hub import snapshot_download
        try:
            snapshot_download(
                repo_id=settings.EMBEDDING_MODEL, revision=settings.EMBEDDING_REVISION,
                local_files_only=options['check_only'],
                allow_patterns=['*.json', '*.txt', '*.safetensors', '*.bin', '*.model'],
            )
            from sentence_transformers import SentenceTransformer
            model = SentenceTransformer(
                settings.EMBEDDING_MODEL, revision=settings.EMBEDDING_REVISION,
                local_files_only=True,
            )
            dimension = len(model.encode('数据结构', normalize_embeddings=True).tolist())
        except Exception:
            raise CommandError('模型准备未通过：请检查固定模型版本、缓存完整性及下载网络；未修改课程索引。') from None
        self.stdout.write(self.style.SUCCESS(f'本地模型加载通过：{settings.EMBEDDING_MODEL}；revision={settings.EMBEDDING_REVISION}；维度={dimension}。'))
