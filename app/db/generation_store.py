"""
媒体生成任务 JSON 文件存储。

每个任务保存为 data/generation_tasks/{id}.json，模式与 tool_store / knowledge_store 一致。
"""
import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from app.config import settings
from app.models.generation import GenerationTask


class GenerationStore:
    """生成任务的 JSON 文件存储（持久化到 data/generation_tasks/）。"""

    def __init__(self):
        self._dir: Path = settings.data_dir / "generation_tasks"
        self._dir.mkdir(parents=True, exist_ok=True)

    def _path(self, task_id: str) -> Path:
        return self._dir / f"{task_id}.json"

    def create(self, task: GenerationTask) -> GenerationTask:
        """新建任务（覆盖写）。"""
        self._path(task.id).write_text(
            task.model_dump_json(indent=2), encoding="utf-8"
        )
        return task

    def get(self, task_id: str) -> Optional[GenerationTask]:
        """按 ID 读取任务；文件不存在返回 None。"""
        path = self._path(task_id)
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        return GenerationTask(**data)

    def update(self, task_id: str, **fields) -> GenerationTask:
        """更新任务字段并刷新 updated_at；任务不存在抛 KeyError。"""
        task = self.get(task_id)
        if task is None:
            raise KeyError(task_id)
        for k, v in fields.items():
            setattr(task, k, v)
        task.updated_at = datetime.now()
        self._path(task_id).write_text(
            task.model_dump_json(indent=2), encoding="utf-8"
        )
        return task


generation_store = GenerationStore()
