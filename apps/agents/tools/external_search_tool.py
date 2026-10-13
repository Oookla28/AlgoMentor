from apps.knowledge.services.wikipedia_service import search_wikipedia


class ExternalKnowledgeProvider:
    def search(self,query: str) -> dict: raise NotImplementedError


class WikipediaProvider(ExternalKnowledgeProvider):
    def __init__(self,transport=None): self.transport=transport

    def search(self,query: str,language: str = 'zh',force_refresh: bool = False,cache_only: bool = False) -> dict:
        return search_wikipedia(query,language,force_refresh,cache_only,transport=self.transport)
