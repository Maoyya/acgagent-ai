"""
创作工坊数据模型。所有模型走 pydantic v2，沿用项目统一 Result<T> 信封（见 app/models/common.py）。
Shot/Character 为单条结构化记录；StoryboardResult/CharactersResult 为容器（供 with_structured_output）。
"""
from pydantic import BaseModel, Field


class PlotRequest(BaseModel):
    """剧情生成请求：故事梗概。"""
    story: str = Field(description="故事梗概（用户输入）")


class Shot(BaseModel):
    """单个分镜。"""
    shot: str = Field(description="景别：远景/中景/近景/特写")
    description: str = Field(description="镜头画面描述")
    duration: str = Field(default="3s", description="时长，如 3s")
    movement: str = Field(default="静止", description="镜头运动：静止/推进/跟随...")
    dialogue: str = Field(default="", description="该镜台词，可为空")


class Character(BaseModel):
    """单个角色。color 不含——由前端按 name 自动配色。"""
    name: str = Field(description="角色名")
    role: str = Field(description="角色定位：主角/配角/引导者...")
    description: str = Field(description="角色外貌与性格描述")


class StoryboardResult(BaseModel):
    """分镜结构化输出容器（供 with_structured_output）。"""
    shots: list[Shot] = Field(default_factory=list)


class CharactersResult(BaseModel):
    """角色结构化输出容器（供 with_structured_output）。"""
    characters: list[Character] = Field(default_factory=list)
