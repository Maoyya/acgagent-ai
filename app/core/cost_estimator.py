"""
消耗估算。

一期口径：估算'生成的 system_prompt 将来每次对话会多吃多少 prompt token'，
即模板自身大小 + 用户 hints。复用 app/core/memory.count_tokens（tiktoken）。
纯计算，无 LLM 调用。est_completion_tokens 一期恒为 0（二期接 LLM 真实 usage）。
"""
from app.core.memory import count_tokens
from app.models.prompt import CostEstimate


class CostEstimator:
    def __init__(self, model: str):
        self.model = model

    def estimate(self, system_prompt: str, user_hints: list[str]) -> CostEstimate:
        """估算模板的 prompt 侧 token 开销。"""
        prompt_tokens = count_tokens(system_prompt, self.model)
        prompt_tokens += sum(count_tokens(h, self.model) for h in user_hints)
        return CostEstimate(
            prompt_tokens=prompt_tokens,
            est_completion_tokens=0,
            model=self.model,
        )
