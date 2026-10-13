"""LangChain adapter that explicitly round-trips DeepSeek reasoning on tool turns.
Reasoning stays in the transient graph state, never in trace payloads or HTML.
"""
import json
from typing import Any
from pydantic import ConfigDict,Field
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage,HumanMessage,SystemMessage,ToolMessage,BaseMessage
from langchain_core.outputs import ChatGeneration,ChatResult
from langchain_core.utils.function_calling import convert_to_openai_tool
from core.llm.deepseek_client import DeepSeekClient
from core.exceptions import LLMProviderError


def serialize_message(message: BaseMessage) -> dict:
    if isinstance(message,AIMessage):
        payload = {'role':'assistant','content':message.content or None}
        if 'reasoning_content' in message.additional_kwargs:
            payload['reasoning_content'] = message.additional_kwargs['reasoning_content']
        if message.tool_calls:
            payload['tool_calls'] = [{'id':call['id'],'type':'function','function':{'name':call['name'],'arguments':json.dumps(call['args'],ensure_ascii=False)}} for call in message.tool_calls]
        return payload
    if isinstance(message,ToolMessage):
        return {'role':'tool','tool_call_id':message.tool_call_id,'content':message.content}
    return {'role':'system' if isinstance(message,SystemMessage) else 'user','content':message.content}


class DeepSeekChatModel(BaseChatModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    client: Any = Field(exclude=True,repr=False)
    tier: str = 'fast'

    @property
    def _llm_type(self) -> str:
        return 'deepseek-byok-reasoning-preserving'

    @property
    def _identifying_params(self) -> dict:
        return {'tier':self.tier}

    def bind_tools(self,tools,*,tool_choice=None,**kwargs):
        return self.bind(tools=[convert_to_openai_tool(tool) for tool in tools],**kwargs)

    def _generate(self,messages,stop=None,run_manager=None,**kwargs) -> ChatResult:
        result = self.client.complete([serialize_message(m) for m in messages],tier=self.tier,tools=kwargs.get('tools'))
        calls=[]
        for call in result.tool_calls:
            try:
                args=json.loads(call['function']['arguments'])
                if not isinstance(args,dict): raise ValueError()
                calls.append({'id':call['id'],'name':call['function']['name'],'args':args,'type':'tool_call'})
            except (KeyError,TypeError,ValueError):
                raise LLMProviderError('模型返回了无效的工具调用参数。',code='INVALID_TOOL_CALL') from None
        usage = None
        if result.usage.input_tokens is not None and result.usage.output_tokens is not None:
            usage={'input_tokens':result.usage.input_tokens,'output_tokens':result.usage.output_tokens,'total_tokens':result.usage.total_tokens or result.usage.input_tokens+result.usage.output_tokens}
        msg=AIMessage(content=result.text,tool_calls=calls,additional_kwargs={'reasoning_content':result.reasoning_content},response_metadata={'model_name':result.model,'finish_reason':result.finish_reason},usage_metadata=usage)
        return ChatResult(generations=[ChatGeneration(message=msg)])
