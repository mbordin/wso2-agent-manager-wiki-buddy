"""Wiki-Buddy: agente simpatico (OpenAI + MCP di terze parti) per WSO2 Agent Manager.

Risponde a domande su repository GitHub usando il server MCP pubblico DeepWiki
e le condisce con una battuta. Funziona in due modi:

    python agent.py chat            # chat da terminale
    python agent.py serve           # API HTTP: POST /chat  {"message": "..."}

Con Agent Manager si avvia con la strumentazione OpenTelemetry:

    amp-instrument python agent.py serve
"""
import asyncio
import json
import os
import sys
from contextlib import AsyncExitStack

from dotenv import load_dotenv
from openai import AsyncOpenAI
from mcp import ClientSession
import httpx2
from mcp.client.streamable_http import streamable_http_client

load_dotenv()

MODEL = os.getenv("LLM_MODEL", "gpt-4o-mini")
MCP_URL = os.getenv("MCP_URL", "https://mcp.deepwiki.com/mcp")
MAX_STEPS = 6

SYSTEM_PROMPT = """Sei Wiki-Buddy, un assistente tecnico con la passione per i giochi di parole.
Aiuti le persone a capire i repository GitHub (architettura, moduli, come si usano)
usando i tool MCP di DeepWiki: prima guarda la documentazione, poi rispondi.
Regole:
- Rispondi nella lingua dell'utente, in modo chiaro e breve.
- Non inventare: se i tool non bastano, dillo.
- Chiudi sempre con UNA battuta o gioco di parole a tema informatica, mai offensiva.
- I repository vanno indicati come owner/repo (es. wso2/agent-manager)."""


def make_llm() -> AsyncOpenAI:
    """Gateway di Agent Manager se configurato, altrimenti OpenAI diretto."""
    url = os.getenv("LLM_PROVIDER_URL")
    if url:
        header = os.getenv("LLM_API_KEY_HEADER", "API-Key")
        return AsyncOpenAI(
            base_url=url,
            api_key="unused",  # la chiave viaggia nell'header del gateway
            default_headers={header: os.environ["LLM_PROVIDER_KEY"]},
        )
    return AsyncOpenAI(api_key=os.environ["OPENAI_API_KEY"])


def mcp_headers() -> dict:
    key = os.getenv("MCP_API_KEY")
    return {os.getenv("MCP_API_KEY_HEADER", "X-API-Key"): key} if key else {}


class WikiBuddy:
    def __init__(self) -> None:
        self.llm = make_llm()
        self.stack = AsyncExitStack()
        self.session: ClientSession | None = None
        self.tools: list[dict] = []

    async def start(self) -> None:
        http = await self.stack.enter_async_context(httpx2.AsyncClient(headers=mcp_headers()))
        read, write = await self.stack.enter_async_context(
            streamable_http_client(MCP_URL, http_client=http)
        )
        self.session = await self.stack.enter_async_context(ClientSession(read, write))
        await self.session.initialize()
        listed = await self.session.list_tools()
        self.tools = [
            {
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description or "",
                    "parameters": t.input_schema,
                },
            }
            for t in listed.tools
        ]
        print(f"MCP collegato: {MCP_URL} ({', '.join(t['function']['name'] for t in self.tools)})")

    async def stop(self) -> None:
        await self.stack.aclose()

    async def ask(self, message: str, history: list[dict] | None = None) -> str:
        messages = [{"role": "system", "content": SYSTEM_PROMPT}, *(history or []),
                    {"role": "user", "content": message}]
        for _ in range(MAX_STEPS):
            resp = await self.llm.chat.completions.create(
                model=MODEL, messages=messages, tools=self.tools or None
            )
            msg = resp.choices[0].message
            if not msg.tool_calls:
                return msg.content or ""
            messages.append(msg.model_dump(exclude_none=True))
            for call in msg.tool_calls:
                args = json.loads(call.function.arguments or "{}")
                try:
                    result = await self.session.call_tool(call.function.name, args)
                    text = "\n".join(c.text for c in result.content if hasattr(c, "text"))
                except Exception as exc:  # il tool puo' fallire: l'LLM lo spiega all'utente
                    text = f"Errore del tool: {exc}"
                messages.append({"role": "tool", "tool_call_id": call.id, "content": text[:12000]})
        return "Ho girato troppo a lungo tra i tool: riprova con una domanda piu' precisa."


async def chat_cli() -> None:
    buddy = WikiBuddy()
    await buddy.start()
    history: list[dict] = []
    print("Wiki-Buddy pronto. Prova: 'Di cosa si occupa wso2/agent-manager?' (Ctrl-C per uscire)")
    try:
        while True:
            q = await asyncio.get_event_loop().run_in_executor(None, input, "tu> ")
            a = await buddy.ask(q, history)
            history += [{"role": "user", "content": q}, {"role": "assistant", "content": a}]
            print(f"buddy> {a}\n")
    except (KeyboardInterrupt, EOFError):
        pass
    finally:
        await buddy.stop()


def serve() -> None:
    import uvicorn
    from fastapi import FastAPI
    from pydantic import BaseModel

    buddy = WikiBuddy()

    class ChatIn(BaseModel):
        message: str
        session_id: str | None = None

    sessions: dict[str, list[dict]] = {}

    async def lifespan(app: FastAPI):
        await buddy.start()
        yield
        await buddy.stop()

    app = FastAPI(title="Wiki-Buddy", lifespan=lifespan)

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    @app.post("/chat")
    async def chat(body: ChatIn):
        hist = sessions.setdefault(body.session_id or "default", [])
        answer = await buddy.ask(body.message, hist[-10:])
        hist += [{"role": "user", "content": body.message}, {"role": "assistant", "content": answer}]
        return {"response": answer}

    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8000")))


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "chat"
    serve() if mode == "serve" else asyncio.run(chat_cli())
