"""创作工坊生成服务测试。

覆盖三条核心路径：
- plot_stream：astream 流式 → SSE content/done 帧（镜像 prompt_service.generate_stream）
- storyboard：with_structured_output(StoryboardResult) → 结构化分镜列表
- characters：with_structured_output(CharactersResult) → 结构化角色列表

mock 策略：用 monkeypatch 替换 workshop_service 单例的 _get_gen_llm，
返回 MagicMock 充当 ChatOpenAI，避免命中真实 API（沿用 prompt 测试的 mock 思路）。

注意：
- storyboard/characters 走同步 structured.invoke（meta-LLM 非流式，见 CRITICAL 约定），
  故 mock 用 MagicMock.return_value，而非 AsyncMock。
- plot_stream 每个 chunk 独立发一帧 SSE（镜像 prompt_service.generate_stream），
  故 body 里"# 角"与"色"分处两帧，不会出现连写的"角色"。
"""
import pytest
from unittest.mock import MagicMock

from app.models.workshop import PlotRequest, Shot, Character, StoryboardResult, CharactersResult


@pytest.mark.asyncio
async def test_plot_stream_emits_content_done(monkeypatch):
    """plot_stream：astream 吐多个 token 时，每个 token 一帧 content，末尾一帧 done。"""
    from app.services import workshop_service as ws

    # mock astream：吐两个 token 再结束
    async def fake_astream(messages):
        for t in ["# 角", "色"]:
            yield MagicMock(content=t)

    fake_llm = MagicMock()
    fake_llm.astream = fake_astream
    monkeypatch.setattr(ws.workshop_service, "_get_gen_llm", lambda: fake_llm)
    chunks = []
    async for sse in ws.workshop_service.plot_stream(PlotRequest(story="x")):
        chunks.append(sse)
    body = "".join(chunks)
    assert 'data: {"type": "content"' in body
    assert "# 角" in body  # 第一帧 content
    assert "色" in body    # 第二帧 content（与"# 角"分处两帧，不连写）
    assert 'data: {"type": "done"}' in body


def test_storyboard_returns_structured(monkeypatch):
    """storyboard：同步 with_structured_output → StoryboardResult.shots → Result.success(list)。"""
    from app.services import workshop_service as ws

    structured = MagicMock()
    # impl 用 structured.invoke(...)（同步），故 mock invoke 的 return_value
    structured.invoke.return_value = StoryboardResult(
        shots=[Shot(shot="远景", description="雨夜")]
    )
    fake_llm = MagicMock()
    fake_llm.with_structured_output.return_value = structured
    monkeypatch.setattr(ws.workshop_service, "_get_gen_llm", lambda: fake_llm)
    res = ws.workshop_service.storyboard("一段剧情")
    assert res.code == 200
    assert res.data[0].shot == "远景"


def test_characters_returns_structured(monkeypatch):
    """characters：同步 with_structured_output → CharactersResult.characters → Result.success(list)。"""
    from app.services import workshop_service as ws

    structured = MagicMock()
    structured.invoke.return_value = CharactersResult(
        characters=[Character(name="林月", role="主角", description="少女")]
    )
    fake_llm = MagicMock()
    fake_llm.with_structured_output.return_value = structured
    monkeypatch.setattr(ws.workshop_service, "_get_gen_llm", lambda: fake_llm)
    res = ws.workshop_service.characters("一段剧情")
    assert res.code == 200
    assert res.data[0].name == "林月"
