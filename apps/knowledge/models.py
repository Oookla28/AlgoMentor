from django.conf import settings
from django.db import models

class Course(models.Model):
    slug = models.SlugField(unique=True)
    name = models.CharField(max_length=100)

class Chapter(models.Model):
    course = models.ForeignKey(Course,on_delete=models.CASCADE,related_name='chapters')
    number = models.PositiveSmallIntegerField(unique=True)
    name = models.CharField(max_length=100)

class KnowledgePoint(models.Model):
    slug = models.SlugField(unique=True)
    name = models.CharField(max_length=100)
    chapter = models.PositiveSmallIntegerField(db_index=True)
    description = models.TextField(blank=True)
    difficulty = models.PositiveSmallIntegerField(default=1)
    prerequisites = models.ManyToManyField('self',symmetrical=False,blank=True,related_name='successors')
    is_extension = models.BooleanField(default=False)
    order = models.PositiveSmallIntegerField(default=0)
    source_page = models.PositiveSmallIntegerField(null=True,blank=True)
    class Meta:
        ordering = ['chapter','order','slug']
    def __str__(self): return self.name

class KnowledgeRelation(models.Model):
    source = models.ForeignKey(KnowledgePoint,on_delete=models.CASCADE,related_name='outgoing_relations')
    target = models.ForeignKey(KnowledgePoint,on_delete=models.CASCADE,related_name='incoming_relations')
    relation_type = models.CharField(max_length=20,choices=[('contains','包含'),('prerequisite','先修'),('related','关联')])
    class Meta:
        constraints = [models.UniqueConstraint(fields=['source','target','relation_type'],name='unique_knowledge_relation')]

class KnowledgeDocument(models.Model):
    SOURCE_TYPES = [('pdf', 'PDF'), ('docx', 'Word'), ('markdown', 'Markdown'), ('text', '纯文本'), ('image', '图片'), ('video', '视频'), ('audio', '音频')]
    INGESTION_STATES = [('legacy', '旧版索引'), ('parsed', '已解析'), ('ready', '已索引'), ('partial', '部分可用'), ('failed', '入库失败')]
    name = models.CharField(max_length=255)
    document_hash = models.CharField(max_length=64,unique=True)
    path = models.CharField(max_length=500)
    version = models.CharField(max_length=32,default='1')
    page_count = models.PositiveIntegerField()
    embedding_model = models.CharField(max_length=255)
    embedding_revision = models.CharField(max_length=255)
    embedding_dimension = models.PositiveIntegerField()
    index_version = models.CharField(max_length=64)
    collection_name = models.CharField(max_length=100)
    # EvidenceRAG Studio metadata. All fields keep defaults so pre-existing rows remain readable.
    source_type = models.CharField(max_length=20,default='pdf',choices=SOURCE_TYPES)
    authority_level = models.PositiveSmallIntegerField(default=3,help_text='1 为最高权威，5 为最低；仅用于证据仲裁，不改变原文')
    valid_from = models.DateTimeField(null=True,blank=True)
    valid_to = models.DateTimeField(null=True,blank=True)
    parser_name = models.CharField(max_length=100,blank=True,default='')
    parser_version = models.CharField(max_length=50,blank=True,default='')
    ingestion_status = models.CharField(max_length=20,default='legacy',choices=INGESTION_STATES)
    source_metadata = models.JSONField(default=dict,blank=True)
    latest_index_version = models.CharField(max_length=64,blank=True,default='')
    created_at = models.DateTimeField(auto_now_add=True)


class MediaAsset(models.Model):
    """Image/video evidence metadata. Binary files stay on disk and never enter the text vector store."""
    MODALITIES = [('image', '图片'), ('video', '视频'), ('audio', '音频')]
    asset_id = models.CharField(max_length=100,unique=True)
    document = models.ForeignKey(KnowledgeDocument,on_delete=models.CASCADE,related_name='media_assets')
    modality = models.CharField(max_length=20,choices=MODALITIES)
    file_path = models.CharField(max_length=500)
    mime_type = models.CharField(max_length=100)
    sha256 = models.CharField(max_length=64,db_index=True)
    page_number = models.PositiveIntegerField(null=True,blank=True)
    bbox = models.JSONField(default=list,blank=True)
    start_time = models.FloatField(null=True,blank=True)
    end_time = models.FloatField(null=True,blank=True)
    ocr_text = models.TextField(blank=True,default='')
    asr_text = models.TextField(blank=True,default='')
    caption = models.TextField(blank=True,default='')
    manual_annotation = models.TextField(blank=True,default='')
    parser_confidence = models.FloatField(default=0.0)
    version = models.CharField(max_length=32,default='1')
    metadata = models.JSONField(default=dict,blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['document','page_number','start_time','asset_id']

    def __str__(self):
        return f'{self.modality}:{self.asset_id}'


class KnowledgeChunk(models.Model):
    CHUNK_TYPES = [('legacy', '旧版片段'), ('parent', '父块'), ('child', '子块'), ('media', '媒体证据')]
    document = models.ForeignKey(KnowledgeDocument,on_delete=models.CASCADE,related_name='chunks')
    chunk_id = models.CharField(max_length=100,unique=True)
    chapter = models.CharField(max_length=100)
    section = models.CharField(max_length=150)
    page_number = models.PositiveIntegerField()
    content = models.TextField()
    source_type = models.CharField(max_length=20,default='original')
    version = models.CharField(max_length=32,default='1')
    parent_chunk = models.ForeignKey('self',null=True,blank=True,on_delete=models.SET_NULL,related_name='children')
    chunk_type = models.CharField(max_length=20,default='legacy',choices=CHUNK_TYPES,db_index=True)
    heading_path = models.CharField(max_length=500,blank=True,default='')
    char_start = models.PositiveIntegerField(null=True,blank=True)
    char_end = models.PositiveIntegerField(null=True,blank=True)
    token_count = models.PositiveIntegerField(default=0)
    overlap_start = models.PositiveIntegerField(default=0)
    overlap_end = models.PositiveIntegerField(default=0)
    parser_confidence = models.FloatField(default=1.0)
    content_hash = models.CharField(max_length=64,blank=True,default='',db_index=True)
    media_asset = models.ForeignKey(MediaAsset,null=True,blank=True,on_delete=models.SET_NULL,related_name='chunks')
    is_active = models.BooleanField(default=True,db_index=True)
    deleted_at = models.DateTimeField(null=True,blank=True)

    class Meta:
        ordering = ['document','page_number','chunk_id']

class KnowledgeCorrection(models.Model):
    chunk = models.ForeignKey(KnowledgeChunk,on_delete=models.CASCADE,related_name='corrections')
    original_statement = models.TextField()
    suggested_statement = models.TextField()
    reason = models.TextField()
    verification = models.TextField()
    status = models.CharField(max_length=20,default='PENDING',choices=[('PENDING','待审核'),('APPROVED','已审核'),('REJECTED','已驳回')])
    reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.SET_NULL,null=True,blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class EvidenceClaim(models.Model):
    """A simplified, verifiable statement extracted from an evidence chunk."""
    claim_id = models.CharField(max_length=100,unique=True)
    source_chunk = models.ForeignKey(KnowledgeChunk,null=True,blank=True,on_delete=models.CASCADE,related_name='claims')
    subject = models.CharField(max_length=500,blank=True,default='')
    predicate = models.CharField(max_length=100,blank=True,default='')
    object = models.TextField(blank=True,default='')
    normalized_text = models.TextField()
    valid_from = models.DateTimeField(null=True,blank=True)
    valid_to = models.DateTimeField(null=True,blank=True)
    authority_level = models.PositiveSmallIntegerField(default=3)
    contradiction_group = models.CharField(max_length=100,blank=True,default='',db_index=True)
    detector_score = models.FloatField(default=0.0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.normalized_text[:60]


class KnowledgeQueryTrace(models.Model):
    trace_id = models.CharField(max_length=100,unique=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL,null=True,blank=True,on_delete=models.SET_NULL,related_name='knowledge_query_traces')
    original_query = models.TextField()
    query_variants = models.JSONField(default=list,blank=True)
    retrieval_mode = models.CharField(max_length=20,default='legacy')
    selected_chunk_ids = models.JSONField(default=list,blank=True)
    latency_ms = models.PositiveIntegerField(default=0)
    fallback_reason = models.CharField(max_length=255,blank=True,default='')
    evidence_sufficient = models.BooleanField(default=False)
    conflict_count = models.PositiveSmallIntegerField(default=0)
    metadata = models.JSONField(default=dict,blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.trace_id


class KnowledgeRetrievalTrace(models.Model):
    trace = models.ForeignKey(KnowledgeQueryTrace,on_delete=models.CASCADE,related_name='retrieval_traces')
    query_variant = models.TextField()
    retriever_name = models.CharField(max_length=50)
    chunk_id = models.CharField(max_length=100,db_index=True)
    rank = models.PositiveIntegerField()
    raw_score = models.FloatField(default=0.0)
    rrf_score = models.FloatField(default=0.0)
    rerank_score = models.FloatField(null=True,blank=True)
    selected = models.BooleanField(default=False)

    class Meta:
        ordering = ['trace','retriever_name','query_variant','rank']


class KnowledgeConflict(models.Model):
    VERDICTS = [('UNRESOLVED', '暂不能确定'), ('A_WINS', '证据 A 优先'), ('B_WINS', '证据 B 优先')]
    conflict_id = models.CharField(max_length=100,unique=True)
    query_trace = models.ForeignKey(KnowledgeQueryTrace,null=True,blank=True,on_delete=models.SET_NULL,related_name='conflicts')
    claim_a = models.ForeignKey(EvidenceClaim,on_delete=models.CASCADE,related_name='conflicts_as_a')
    claim_b = models.ForeignKey(EvidenceClaim,on_delete=models.CASCADE,related_name='conflicts_as_b')
    conflict_type = models.CharField(max_length=30,default='STANCE')
    confidence = models.FloatField(default=0.0)
    authority_scores = models.JSONField(default=dict,blank=True)
    freshness_scores = models.JSONField(default=dict,blank=True)
    verdict = models.CharField(max_length=20,default='UNRESOLVED',choices=VERDICTS)
    explanation = models.TextField(blank=True,default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.conflict_type}:{self.conflict_id}'


class WikipediaCache(models.Model):
    """Shared public article cache. Never stores users, conversations or API keys."""
    query = models.CharField(max_length=255, help_text='API 返回的公开词条标题，不存学生原始问题')
    normalized_query = models.CharField(max_length=255)
    public_aliases = models.JSONField(default=dict, help_text='已校验公开概念的规范化别名，不存原始问题')
    language = models.CharField(max_length=2, choices=[('zh', '中文'), ('en', 'English')])
    page_id = models.PositiveBigIntegerField()
    title = models.CharField(max_length=255)
    summary = models.TextField()
    source_url = models.URLField(max_length=1000)
    revision_id = models.PositiveBigIntegerField(null=True, blank=True)
    retrieved_at = models.DateTimeField()
    expires_at = models.DateTimeField(db_index=True)
    last_accessed_at = models.DateTimeField()
    content_hash = models.CharField(max_length=64)
    cache_version = models.PositiveSmallIntegerField(default=1)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['normalized_query', 'language'], name='unique_wikipedia_public_title'),
            models.UniqueConstraint(fields=['page_id', 'language'], name='unique_wikipedia_page_language'),
        ]
        ordering = ['-retrieved_at']

    def __str__(self):
        return f'{self.language}: {self.title}'
