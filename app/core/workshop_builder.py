"""
创作工坊生成器。

构造 plot / storyboard / characters 三类元提示词消息（[SystemMessage, HumanMessage]），
交给 meta-LLM 处理。消息构造风格镜像 prompt_builder.build_messages。
"""
from langchain_core.messages import HumanMessage, SystemMessage

_PLOT_SYS = "你是一名资深剧本作家，擅长把简短的故事梗概扩展为有画面感、有起伏的完整剧情（Markdown，分章节）。"
_SB_SYS = "你是一名分镜师，把剧情拆成可拍摄的分镜清单，只返回结构化结果。"
_CH_SYS = "你是一名角色设计师，根据剧情提炼角色，只返回结构化结果。"


class WorkshopBuilder:
    """创作工坊的元提示词构造器（无状态，纯消息组装）。"""

    def plot_messages(self, story: str) -> list:
        """剧情生成的 [System, Human] 消息：把故事梗概扩展为完整剧情正文。"""
        payload = (
            f"把下面的故事梗概扩展为完整剧情，要求：画面感强、有起承转合、分章节（Markdown）。\n"
            f"故事梗概：\n{story}\n"
            f"输出：只输出剧情正文，不要解释、不要前缀。"
        )
        return [SystemMessage(content=_PLOT_SYS), HumanMessage(content=payload)]

    def storyboard_messages(self, plot: str) -> list:
        """分镜生成的 [System, Human] 消息：把剧情拆为 5~8 个可拍摄分镜。"""
        payload = (
            f"把下面的剧情拆分为 5~8 个分镜。每个分镜含：景别(远景/中景/近景/特写)、画面描述、时长、镜头运动、台词(可空)。\n"
            f"剧情：\n{plot}\n"
            f"只返回结构化结果。"
        )
        return [SystemMessage(content=_SB_SYS), HumanMessage(content=payload)]

    def characters_messages(self, plot: str) -> list:
        """角色提炼的 [System, Human] 消息：从剧情中提取 2~4 个主要角色。"""
        payload = (
            f"从下面的剧情中提炼主要角色（通常 2~4 个）。每个角色含：姓名、定位(主角/配角/引导者...)、外貌与性格描述。\n"
            f"剧情：\n{plot}\n"
            f"只返回结构化结果。"
        )
        return [SystemMessage(content=_CH_SYS), HumanMessage(content=payload)]
