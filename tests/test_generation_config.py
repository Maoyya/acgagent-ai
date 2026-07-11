# tests/test_generation_config.py
from app.config import settings


def test_generation_config_defaults():
    assert settings.generation_base_url == "https://dashscope.aliyuncs.com/api/v1"
    assert settings.generation_image_model == "wanx2.1-t2i-turbo"
    assert settings.generation_video_model == "wan2.1-i2v-turbo"
    assert isinstance(settings.generation_api_key, str)
