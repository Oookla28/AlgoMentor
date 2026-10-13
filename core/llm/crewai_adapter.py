from crewai import BaseLLM
from core.llm.deepseek_client import DeepSeekClient
from core.llm.model_registry import get_tier


class DeepSeekCrewLLM(BaseLLM):
    """CrewAI BaseLLM delegates every call to the same user-isolated audited provider."""
    def __init__(self,user,tier,deadline=None,client=None):
        super().__init__(model=get_tier(tier).model,temperature=None)
        self.client=client or DeepSeekClient(user,purpose='report',deadline=deadline)
        self.tier=tier

    def call(self,messages,tools=None,callbacks=None,available_functions=None,**kwargs):
        if isinstance(messages,str): messages=[{'role':'user','content':messages}]
        return self.client.complete(messages,tier=self.tier).text

    def supports_function_calling(self): return False
    def supports_stop_words(self): return False
    def get_context_window_size(self): return 32000
