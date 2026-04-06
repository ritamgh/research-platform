"""RAG A2A agent server — FastAPI + a2a-sdk."""
import json
import os
from pathlib import Path

import uvicorn
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.apps import A2AFastAPIApplication
from a2a.server.events import EventQueue
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore, TaskUpdater
from a2a.types import AgentCapabilities, AgentCard, AgentSkill, Part, TextPart
from a2a.utils import new_agent_text_message, new_task
from dotenv import load_dotenv

from agents.rag.agent import run_rag_lookup

load_dotenv()

_CARD_PATH = Path(__file__).parent / "agent_card.json"


def _load_card() -> AgentCard:
    raw = json.loads(_CARD_PATH.read_text())
    url = os.environ.get("RAG_AGENT_URL", raw["url"])
    return AgentCard(
        name=raw["name"],
        description=raw["description"],
        version=raw["version"],
        url=f"{url}/",
        capabilities=AgentCapabilities(
            streaming=raw["capabilities"]["streaming"],
            push_notifications=raw["capabilities"]["push_notifications"],
        ),
        skills=[
            AgentSkill(
                id=s["id"],
                name=s["name"],
                description=s["description"],
                tags=s.get("tags", []),
                examples=s.get("examples", []),
            )
            for s in raw["skills"]
        ],
        default_input_modes=raw.get("default_input_modes", ["text/plain"]),
        default_output_modes=raw.get("default_output_modes", ["text/plain"]),
    )


class RagAgentExecutor(AgentExecutor):
    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        task = context.current_task or new_task(context.message)
        updater = TaskUpdater(event_queue, task.id, task.context_id)

        await updater.submit()
        await updater.start_work()

        try:
            query = ""
            if context.message and context.message.parts:
                query = context.message.parts[0].root.text

            if not query:
                raise ValueError("No query provided in task message")

            result_text = await run_rag_lookup(query)

            await updater.add_artifact(
                [Part(root=TextPart(text=result_text))]
            )
            await updater.complete()
        except Exception as exc:
            error_msg = new_agent_text_message(
                f"RAG lookup failed: {exc}", task.context_id, task.id
            )
            await updater.failed(error_msg)

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        if context.current_task:
            updater = TaskUpdater(
                event_queue,
                context.current_task.id,
                context.current_task.context_id,
            )
            await updater.cancel()


def build_app():
    agent_card = _load_card()
    task_store = InMemoryTaskStore()
    executor = RagAgentExecutor()
    handler = DefaultRequestHandler(
        agent_executor=executor, task_store=task_store
    )
    return A2AFastAPIApplication(agent_card=agent_card, http_handler=handler).build()


app = build_app()

if __name__ == "__main__":
    port = int(os.environ.get("RAG_PORT", 8002))
    uvicorn.run(app, host="0.0.0.0", port=port)
