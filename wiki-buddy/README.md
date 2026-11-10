# Wiki-Buddy: agente di esempio per WSO2 Agent Manager

Agente Python simpatico che usa un **LLM OpenAI** e un **MCP di terze parti** ([DeepWiki](https://mcp.deepwiki.com), pubblico e senza autenticazione) per spiegare repository GitHub, chiudendo ogni risposta con una battuta.

```
utente -> POST /chat -> Wiki-Buddy -> OpenAI (via AI Gateway di Agent Manager)
                                   -> MCP DeepWiki (tool: read_wiki_structure, read_wiki_contents, ask_question)
```

## Provalo in locale

```bash
cd wiki-buddy
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # imposta OPENAI_API_KEY (lascia vuote le LLM_PROVIDER_*)
python agent.py chat        # chat da terminale
python agent.py serve       # API su http://localhost:8000
curl -s localhost:8000/chat -H 'content-type: application/json' \
  -d '{"message":"Di cosa si occupa wso2/agent-manager?"}'
```

## Collegarlo a WSO2 Agent Manager (agente Externally-Hosted)

1. Console > progetto > **+ Add Agent > Externally-Hosted Agent** > nome `Wiki-Buddy` > **Register**.
2. **Setup Agent**: genera la API key e copia `AMP_OTEL_ENDPOINT` e `AMP_AGENT_API_KEY` nel `.env`.
3. **Configure > LLM Configurations > Add > OpenAI**: dal pannello *Connect to LLM Provider* copia
   Endpoint URL in `LLM_PROVIDER_URL`, API key in `LLM_PROVIDER_KEY` e il nome dell'header in `LLM_API_KEY_HEADER`.
   Da quel momento l'LLM passa dall'AI Gateway: token, costi e trace sono governati dalla piattaforma.
4. (Facoltativo) Registra DeepWiki come **MCP Proxy** (Organization > Resources > MCP Proxies, endpoint
   `https://mcp.deepwiki.com/mcp`), poi **Tool Configurations > Add** e usa l'URL del proxy in `MCP_URL`
   (e la chiave in `MCP_API_KEY`). Così anche le chiamate MCP sono governate e visibili nelle trace.
5. Avvia con la strumentazione OpenTelemetry:
   ```bash
   pip install amp-instrumentation   # solo per l'esecuzione Externally-Hosted
   amp-instrument python agent.py serve
   ```
6. Fai qualche domanda e apri **Traces** nella console: vedi le chiamate LLM e i tool MCP.

Per eseguirlo come agente Platform-Hosted: Source Code, Project Path `/wiki-buddy`, Python, Start Command `python main.py` (la porta è 8000). La strumentazione la inietta la piattaforma, quindi non serve `amp-instrumentation`.

## Idee per la demo

- "Spiegami l'architettura di wso2/agent-manager" / "Come si installa?"
- Confronta due repo: "Differenze tra wso2/api-manager e wso2/agent-manager?"

Nota: `mcp` è fissato alla serie 1.x e `openai` alla 1.x perché l'instrumentation Traceloop della piattaforma è compatibile con quelle API. Il client MCP è stato verificato contro un server locale; il giro con OpenAI richiede una tua chiave.
