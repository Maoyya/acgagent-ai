import json
import logging
from pathlib import Path
from typing import Optional

from app.config import settings
from app.models.agent import AgentConfig

logger = logging.getLogger("acgagent-ai")


class AgentStore:
    def __init__(self):
        self._dir: Path = settings.data_dir / "agents"
        self._dir.mkdir(parents=True, exist_ok=True)

    def _path(self, agent_id: str) -> Path:
        return self._dir / f"{agent_id}.json"

    def list_all(self) -> list[AgentConfig]:
        agents = []
        for f in sorted(self._dir.glob("*.json")):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                agents.append(AgentConfig(**data))
            except Exception as e:
                logger.warning("Failed to load agent %s: %s", f.name, e)
        return agents

    def get(self, agent_id: str) -> Optional[AgentConfig]:
        path = self._path(agent_id)
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        return AgentConfig(**data)

    def save(self, agent: AgentConfig) -> AgentConfig:
        path = self._path(agent.id)
        path.write_text(agent.model_dump_json(indent=2), encoding="utf-8")
        return agent

    def delete(self, agent_id: str) -> bool:
        path = self._path(agent_id)
        if path.exists():
            path.unlink()
            return True
        return False


agent_store = AgentStore()
