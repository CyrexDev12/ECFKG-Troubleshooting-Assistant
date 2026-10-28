# Official implementation references checked

API-first revision: [OpenAI Chat Completions](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create)
and [structured outputs](https://developers.openai.com/api/docs/guides/structured-outputs)
were checked for tool-call IDs, JSON arguments and response formats. The Ollama references
below document the retained, deferred implementation, not the active UI route.

Accessed 2026-10-27. These references guide software interfaces; they are not diagnostic
knowledge-graph evidence or claims of project approval for manufacturer content.

Connection fix: [GPT-6.1 Sol](https://developers.openai.com/api/docs/models/gpt-6.1-sol)
requires Responses for tool calling. The adapter follows the
[Responses migration](https://developers.openai.com/api/docs/guides/migrate-to-responses),
[function-calling](https://developers.openai.com/api/docs/guides/function-calling),
[reasoning-context](https://developers.openai.com/api/docs/guides/reasoning) and
[error-code](https://developers.openai.com/api/docs/guides/error-codes) guidance.

| Dependency | Checked interface | Official reference |
|---|---|---|
| Streamlit | AppTest.from_file, run and widget manipulation | https://docs.streamlit.io/develop/api-reference/app-testing/st.testing.v1.apptest |
| Streamlit | graphviz_chart | https://docs.streamlit.io/develop/api-reference/charts/st.graphviz_chart |
| NetworkX | MultiDiGraph, directed parallel edges and attributes | https://networkx.org/documentation/stable/reference/classes/multidigraph.html |
| Pydantic | Models, validation and JSON schema | https://docs.pydantic.dev/latest/concepts/models/ |
| HTTPX | Connection/read/write/pool timeouts | https://www.python-httpx.org/advanced/timeouts/ |
| pytest | CLI invocation | https://docs.pytest.org/en/stable/how-to/usage.html |
| Ollama | /api/chat, messages, tools, format and stream | https://docs.ollama.com/api/chat |
| Ollama | Native tool calls and tool result messages | https://docs.ollama.com/capabilities/tool-calling |
| Ollama | Installed model inventory | https://docs.ollama.com/api/tags |
| Ollama | Model details via /api/show | https://docs.ollama.com/api-reference/show-model-details |
| Ollama | Local-only server setting | https://docs.ollama.com/faq |

Installed versions are recorded in `requirements-lock.txt` and each evaluation JSON. The
local model integration is implemented against these interfaces but has only been exercised
with mocks because a live Ollama service was unavailable.

