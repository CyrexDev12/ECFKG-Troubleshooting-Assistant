# API setup — ASU Capstone IEE-018

The active model route supports OpenAI Responses and compatible Chat Completions APIs. The local app and
deterministic demo remain available; local LLM hosting is deferred. The project label
appears above the title and in the sidebar, with a subtle bottom-right text watermark.

## Configure and run

1. Select **API-assisted** in the sidebar.
2. Enter the provider's HTTPS API **base** URL, usually ending in `/v1`. Do not include
   `/responses`, `/chat/completions`, query parameters or credentials in the URL.
3. Enter a model ID your account can use and a key in the masked field. Alternatively set
   `ECFKG_MODEL`, `ECFKG_API_BASE_URL` and `ECFKG_API_KEY` in the server environment.
   `OPENAI_API_KEY` is used if `ECFKG_API_KEY` is unset. No key is prefilled into the browser.
4. **Check API connection** calls `GET /models`. Some providers restrict this route; a
   successful inventory check does not establish tool-calling or structured-output support.
   Inference does not depend on the inventory route being available.
5. Click **Assess symptom**. Each model turn can issue at most eight inference requests
   and six read-only graph tool calls. Provider charges may apply.

In **Provider compatibility**, leave **API protocol** at `auto` for normal use. It selects
Responses for `api.openai.com` and Chat Completions for other providers. Override it for a
provider that supports a different route, or set `ECFKG_API_PROTOCOL`. The selected route
is shown below the controls. **GPT-6.1 Sol requires Responses for tool calls.** Keep the
base URL `https://api.openai.com/v1` and model `gpt-6.1-sol`; do not add `/responses` to the URL.

JSON schema is the default output format. JSON object mode is available for providers
without schema support; both undergo identical local validation. Responses uses `text.format`,
`max_output_tokens=4096`, and a 60-second request timeout. GPT-6.1 Sol uses low reasoning
effort for this bounded retrieval task. Chat Completions uses `response_format`, a 25-second
request timeout, and 2,048 tokens via `max_completion_tokens` or `max_tokens`. All routes
retain the 120-second turn deadline. No temperature/seed determinism is claimed.

## Connection troubleshooting

The initial adapter sent tool calls through Chat Completions for every model. That route
is incompatible with GPT-6.1 Sol tool calling. The old assessment banner also hid HTTP error
details behind `ModelError`, so the screenshot alone could not establish the exact provider
failure. The corrected OpenAI route uses Responses and shows application-authored errors:

| Message | Next step |
|---|---|
| Authentication failed (401) | Check the active API key and its project/provider. |
| Access denied (403) | Check key permissions and model access. |
| Model or route not found (404) | Check the model ID, account access and base URL. |
| Quota exhausted / rate limit (429) | Check API billing/spending limits or wait for rate limits to reset. |
| Request or tool calling rejected (400) | Check the protocol and provider compatibility settings. |
| Model reached output limit | The response was incomplete and was discarded. |

Connection checking uses the model inventory only; a green result does not establish that
inference and tools work. **Assess symptom** tests those capabilities. After restarting the
app, re-enter the key in the masked field if needed; do not paste it into chat or source files.

## Transport and key handling

The adapter uses `POST <base>/responses` or `POST <base>/chat/completions`, Bearer
authentication and standard function tools. Responses uses flattened function definitions,
`function_call_output` items and matching `call_id` values. It requests `store: false` and
replays output items, including encrypted reasoning, within the current tool loop. That
internal context is never rendered or exported. This setting does not claim zero provider
retention. Chat Completions uses nested function definitions and `tool_call_id` messages.
Both normalize responses into the existing agent contract. Tool arguments and final selections still pass
the existing allowlists and validation. Truncated output, refusal, bad arguments, authentication,
quota and timeout errors do not invoke a baseline fallback or a different provider.

API keys are held in a private adapter field or the current Streamlit session/environment.
They are not added to prompts, tool arguments, metadata, diagnostic exports or error messages.
No key is written by the application. Clearing the entered key does not remove an environment
key. `.env.example` is documentation only and is not automatically loaded.

The API receives the symptom, categorical observations, relevant graph results and system
instructions. Local storage does not make inference local. Use only approved generic or
synthetic material and review provider/account data-handling settings before sharing other
approved material. The user authorized this exploratory API route; it is not evidence that
the original scope's deployment/data-compliance acceptance criteria have been satisfied.

HTTP redirects and proxy environment variables are disabled. Requests require HTTPS, have
timeouts, and cap responses at 256 KiB. The configured provider receives the key; enter only
the intended provider's URL. Do not put secrets in the model name or symptom field.

## Verification

Mock HTTP tests cover complete four-request diagnostic exchanges for both protocols, tool-call
ID matching, reasoning-context replay, both response formats, credential separation,
safe actionable HTTP errors, malformed responses, timeouts,
response limits and missing configuration. They do not establish successful live inference.
The initial evaluation workbook remains a historical baseline. Run an API evaluation explicitly:

```powershell
.\.venv\Scripts\python.exe -m ecfkg.evaluate --mode api --out outputs/local-api
```

`--mode llm` is a compatibility alias for the API route. No active CLI mode selects Ollama.

Official interfaces checked: [Chat Completions](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create)
and [structured outputs](https://developers.openai.com/api/docs/guides/structured-outputs),
[GPT-6.1 Sol](https://developers.openai.com/api/docs/models/gpt-6.1-sol),
[Responses migration](https://developers.openai.com/api/docs/guides/migrate-to-responses),
[function calling](https://developers.openai.com/api/docs/guides/function-calling),
[reasoning context](https://developers.openai.com/api/docs/guides/reasoning),
and [API errors](https://developers.openai.com/api/docs/guides/error-codes).

