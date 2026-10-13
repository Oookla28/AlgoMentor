from dataclasses import asdict, dataclass
from core.exceptions import ValidationError


@dataclass(frozen=True)
class ModelTier:
    key: str
    label: str
    model: str
    thinking: bool
    reasoning_effort: str

    def payload(self, effort: str | None = None) -> dict:
        level = effort or self.reasoning_effort
        if self.thinking and level not in ('low', 'high', 'max'):
            raise ValidationError('推理强度仅支持 low、high、max。')
        return {'model': self.model, 'thinking': {'type': 'enabled' if self.thinking else 'disabled'}, 'reasoning_effort': level if self.thinking else 'none'}


MODEL_TIERS = {
    'fast': ModelTier('fast', 'DeepSeek 极速', 'deepseek-flash', False, 'none'),
    'deep': ModelTier('deep', 'DeepSeek 深度', 'deepseek-flash', True, 'high'),
    'expert': ModelTier('expert', 'DeepSeek 专家', 'deepseek-v4-pro', True, 'high'),
}


def get_tier(key: str) -> ModelTier:
    try:
        return MODEL_TIERS[key]
    except (KeyError, TypeError):
        raise ValidationError('请选择有效的模型档位。') from None


def model_options() -> list[dict]:
    return [asdict(tier) for tier in MODEL_TIERS.values()]
