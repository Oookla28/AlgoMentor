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
    created_at = models.DateTimeField(auto_now_add=True)

class KnowledgeChunk(models.Model):
    document = models.ForeignKey(KnowledgeDocument,on_delete=models.CASCADE,related_name='chunks')
    chunk_id = models.CharField(max_length=100,unique=True)
    chapter = models.CharField(max_length=100)
    section = models.CharField(max_length=150)
    page_number = models.PositiveIntegerField()
    content = models.TextField()
    source_type = models.CharField(max_length=20,default='original')
    version = models.CharField(max_length=32,default='1')

class KnowledgeCorrection(models.Model):
    chunk = models.ForeignKey(KnowledgeChunk,on_delete=models.CASCADE,related_name='corrections')
    original_statement = models.TextField()
    suggested_statement = models.TextField()
    reason = models.TextField()
    verification = models.TextField()
    status = models.CharField(max_length=20,default='PENDING',choices=[('PENDING','待审核'),('APPROVED','已审核'),('REJECTED','已驳回')])
    reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.SET_NULL,null=True,blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


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
