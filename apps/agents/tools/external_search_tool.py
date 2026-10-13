from urllib.parse import quote
import requests
from core.exceptions import ExternalServiceError,ValidationError


class ExternalKnowledgeProvider:
    def search(self,query: str) -> dict: raise NotImplementedError


class WikipediaProvider(ExternalKnowledgeProvider):
    def __init__(self,transport=None): self.transport=transport or requests.Session()

    def search(self,query: str,language: str = 'zh') -> dict:
        if not isinstance(query,str) or not query.strip() or len(query)>120 or language not in ('zh','en'):
            raise ValidationError('百科关键词或语言无效。')
        url=f'https://{language}.wikipedia.org/api/rest_v1/page/summary/'+quote(query.strip(),safe='')
        try:
            response=self.transport.get(url,headers={'User-Agent':'AlgoMentor/1.0 (educational course assistant)'},timeout=(5,10),allow_redirects=False)
            if response.status_code==404: return {'found':False,'source':'Wikipedia','query':query}
            if response.status_code>=300:
                raise ExternalServiceError('维基百科接口暂不可用。',code='EXTERNAL_KNOWLEDGE_UNAVAILABLE')
            value=response.json()
            extract=value.get('extract')
            if not isinstance(extract,str):
                raise ValueError()
            return {'found':bool(extract),'title':value.get('title',query),'extract':extract[:6000],'source':'Wikipedia（外部补充资料）','url':value.get('content_urls',{}).get('desktop',{}).get('page',f'https://{language}.wikipedia.org/wiki/'+quote(query.strip(),safe=''))}
        except requests.Timeout:
            raise ExternalServiceError('百科查询超时。',code='EXTERNAL_KNOWLEDGE_TIMEOUT',status_code=504) from None
        except requests.RequestException:
            raise ExternalServiceError('百科服务网络不可用。',code='EXTERNAL_KNOWLEDGE_NETWORK_ERROR',status_code=503) from None
        except (ValueError,TypeError):
            raise ExternalServiceError('百科服务响应格式无效。',code='INVALID_EXTERNAL_RESPONSE') from None
