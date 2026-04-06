# LLM Query Agent Integration — Complete Plan

## Context

**Problem:** Our search engine requires users to manually choose between search types (text/image/hybrid/similar) and fill in structured filters. Natural language queries like *"metal pipes detected last week at AGR"* cannot be handled directly.

**Solution:** Add an LLM agent layer that interprets natural language, extracts structured search parameters, and orchestrates existing search infrastructure — without rebuilding anything.

**Constraint:** The LLM provider must be swappable (Claude, OpenAI/ChatGPT, Ollama local models) via environment variables alone.

**Status:** Phase 1 implementation is **complete**. All files are created and modified. This document serves as the comprehensive reference.

---

## 1. System Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              FRONTEND (React SPA)                               │
│                                                                                 │
│  ┌──────────────┐  ┌──────────────┐  ┌─────────────────────────────────────┐    │
│  │ Text Search  │  │ Image Search │  │  "Smart Search" (Agent)             │    │
│  │ /search/text │  │ /search/image│  │  POST /api/v1/agent/search          │    │
│  └──────┬───────┘  └──────┬───────┘  │  query: "metal pipes last week AGR" │    │
│         │                  │          └──────────────────┬──────────────────┘    │
│         │                  │                             │                       │
└─────────┼──────────────────┼─────────────────────────────┼───────────────────────┘
          │                  │                             │
          ▼                  ▼                             ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                          FASTAPI (port 8000)                                    │
│                                                                                 │
│  Existing Endpoints              New Agent Endpoint                             │
│  ┌────────────────────┐          ┌──────────────────────────────────────────┐   │
│  │ POST /search/text  │          │ POST /agent/search                      │   │
│  │ POST /search/image │          │                                          │   │
│  │ POST /search/hybrid│          │  AgentExecutor                           │   │
│  │ POST /search/similar│         │  ┌────────────────────────────────────┐  │   │
│  └────────┬───────────┘          │  │ 1. _run_llm_planning()            │  │   │
│           │                      │  │    ┌─────────────────────────┐     │  │   │
│           │                      │  │    │  LLM Provider           │     │  │   │
│           │                      │  │    │  (Claude/OpenAI/Ollama) │     │  │   │
│           │                      │  │    │                         │     │  │   │
│           │                      │  │    │  Input: NL query +      │     │  │   │
│           │                      │  │    │        tool definitions │     │  │   │
│           │                      │  │    │                         │     │  │   │
│           │                      │  │    │  Output: ToolCall       │     │  │   │
│           │                      │  │    │    name: search_text    │     │  │   │
│           │                      │  │    │    args: {query_text,   │     │  │   │
│           │                      │  │    │      plant_site, ...}   │     │  │   │
│           │                      │  │    └─────────────────────────┘     │  │   │
│           │                      │  │                                    │  │   │
│           │                      │  │ 2. Execute tool call               │  │   │
│           │                      │  │ 3. Build response                  │  │   │
│           │                      │  └──────────────┬─────────────────────┘  │   │
│           │                      └─────────────────┼────────────────────────┘   │
│           │                                        │                            │
│           ▼                                        ▼                            │
│  ┌─────────────────────────────────────────────────────────────────────┐        │
│  │                     SearchService (shared)                          │        │
│  │                                                                     │        │
│  │  search_by_text(query, top_k, search_type, filters)                │        │
│  │  search_by_image(image_bytes, top_k, search_type, filters)         │        │
│  │  search_hybrid(image_bytes, query, text_weight, ...)               │        │
│  │  search_similar(item_id, item_type, top_k, filters)                │        │
│  └───────────────────────┬─────────────────────────────────────────────┘        │
│                          │                                                      │
└──────────────────────────┼──────────────────────────────────────────────────────┘
                           │
          ┌────────────────┼────────────────┐
          ▼                ▼                ▼
┌──────────────┐  ┌──────────────┐  ┌──────────────┐
│  Embedding   │  │   Qdrant     │  │  PostgreSQL  │
│  Model (CLIP)│  │  Vector DB   │  │  (Django ORM)│
│              │  │              │  │              │
│ encode_text()│  │  search()    │  │  Image       │
│ encode_image │  │  with filters│  │  Detection   │
│              │  │              │  │  SearchQuery │
└──────────────┘  └──────────────┘  └──────────────┘
```

---

## 2. LLM Abstraction Layer Diagram

```
┌──────────────────────────────────────────────────────────────────┐
│                    LLM Abstraction Layer                         │
│                 backend/infrastructure/llm/                      │
│                                                                  │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │                   BaseLLMClient (ABC)                      │  │
│  │                      base.py                               │  │
│  │                                                            │  │
│  │  chat_with_tools(messages, tools, system_prompt)           │  │
│  │      → LLMResponse(tool_calls: [ToolCall], text, raw)     │  │
│  │                                                            │  │
│  │  format_tool_result(tool_call_id, result)                  │  │
│  │      → provider-specific message dict                      │  │
│  │                                                            │  │
│  │  format_assistant_message(response)                        │  │
│  │      → provider-specific message dict                      │  │
│  └──────────────────────┬─────────────────────────────────────┘  │
│                         │ implements                              │
│            ┌────────────┼────────────┐                           │
│            ▼            ▼            ▼                            │
│  ┌──────────────┐ ┌──────────┐ ┌──────────────┐                 │
│  │  Anthropic   │ │  OpenAI  │ │   Ollama     │                 │
│  │  Client      │ │  Client  │ │   Client     │                 │
│  │              │ │          │ │              │                  │
│  │ AsyncAnthropic│ │AsyncOpenAI│ │  httpx POST │                 │
│  │ messages.    │ │ chat.    │ │  /api/chat   │                 │
│  │   create()   │ │completions│ │              │                 │
│  │              │ │ .create()│ │              │                  │
│  │ Tool format: │ │ Tool fmt:│ │ Tool format: │                 │
│  │ Anthropic    │ │ OpenAI   │ │ OpenAI-compat│                 │
│  │ native       │ │ function │ │ function     │                 │
│  └──────────────┘ └──────────┘ └──────────────┘                 │
│                                                                  │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │              Factory (factory.py)                           │  │
│  │                                                            │  │
│  │  get_llm_client() → BaseLLMClient                         │  │
│  │                                                            │  │
│  │  Reads LLM_PROVIDER env var:                               │  │
│  │    "anthropic" → AnthropicLLMClient(ANTHROPIC_API_KEY)     │  │
│  │    "openai"    → OpenAILLMClient(OPENAI_API_KEY)           │  │
│  │    "ollama"    → OllamaLLMClient(OLLAMA_BASE_URL)          │  │
│  │                                                            │  │
│  │  Singleton pattern — one client instance per process       │  │
│  └────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────┘
```

---

## 3. Agent Search Request Flow (Detailed Sequence)

```
Client                    AgentEndpoint              LLM Provider           SearchService        Qdrant
  │                           │                          │                      │                  │
  │  POST /agent/search       │                          │                      │                  │
  │  {query: "metal pipes     │                          │                      │                  │
  │   detected last week      │                          │                      │                  │
  │   at AGR"}                │                          │                      │                  │
  │ ─────────────────────────>│                          │                      │                  │
  │                           │                          │                      │                  │
  │                           │  chat_with_tools(        │                      │                  │
  │                           │    query + AGENT_TOOLS)  │                      │                  │
  │                           │ ────────────────────────>│                      │                  │
  │                           │                          │                      │                  │
  │                           │   [OPTIONAL: LLM calls   │                      │                  │
  │                           │    get_available_metadata]│                      │                  │
  │                           │ <────────────────────────│                      │                  │
  │                           │                          │                      │                  │
  │                           │  execute_get_metadata()  │                      │                  │
  │                           │  (Django ORM query)      │                      │                  │
  │                           │──────────────────────────┼─────────────────────>│                  │
  │                           │  {plant_sites:[AGR,...],  │                      │                  │
  │                           │   labels:[...],          │                      │                  │
  │                           │   shifts:[...]}          │                      │                  │
  │                           │<─────────────────────────┼──────────────────────│                  │
  │                           │                          │                      │                  │
  │                           │  chat_with_tools(        │                      │                  │
  │                           │    metadata result +     │                      │                  │
  │                           │    original query)       │                      │                  │
  │                           │ ────────────────────────>│                      │                  │
  │                           │                          │                      │                  │
  │                           │  ToolCall: search_text(  │                      │                  │
  │                           │    query="metal pipe",   │                      │                  │
  │                           │    plant_site="AGR",     │                      │                  │
  │                           │    date_from="2026-03-15"│                      │                  │
  │                           │  )                       │                      │                  │
  │                           │ <────────────────────────│                      │                  │
  │                           │                          │                      │                  │
  │                           │  Parse ToolCall          │                      │                  │
  │                           │  → SearchPlan            │                      │                  │
  │                           │                          │                      │                  │
  │                           │  execute_search_text()   │                      │                  │
  │                           │─────────────────────────>│                      │                  │
  │                           │                          │  search_by_text()    │                  │
  │                           │                          │  encode query text   │                  │
  │                           │                          │  ───────────────────>│  CLIP encode     │
  │                           │                          │                      │  ───────────────>│
  │                           │                          │                      │  query_points()  │
  │                           │                          │                      │  with filters    │
  │                           │                          │                      │  <───────────────│
  │                           │                          │  vector results      │                  │
  │                           │<─────────────────────────│  <───────────────────│                  │
  │                           │                          │                      │                  │
  │                           │  Build AgentSearchResponse                      │                  │
  │                           │  ┌────────────────────┐  │                      │                  │
  │                           │  │ results            │  │                      │                  │
  │                           │  │ + SearchPlan       │  │                      │                  │
  │                           │  │ + timing           │  │                      │                  │
  │                           │  │ + llm_provider     │  │                      │                  │
  │                           │  │ + model_version    │  │                      │                  │
  │                           │  └────────────────────┘  │                      │                  │
  │                           │                          │                      │                  │
  │  AgentSearchResponse      │                          │                      │                  │
  │ <─────────────────────────│                          │                      │                  │
  │                           │                          │                      │                  │
```

---

## 4. Fallback Flow (LLM Failure / Timeout)

```
Client                    AgentEndpoint              LLM Provider           SearchService
  │                           │                          │                      │
  │  POST /agent/search       │                          │                      │
  │  {query: "rusty pipes"}   │                          │                      │
  │ ─────────────────────────>│                          │                      │
  │                           │                          │                      │
  │                           │  chat_with_tools()       │                      │
  │                           │ ────────────────────────>│                      │
  │                           │                          │                      │
  │                           │  ✗ EXCEPTION / TIMEOUT   │                      │
  │                           │  (API error, network,    │                      │
  │                           │   or asyncio timeout)    │                      │
  │                           │ <──── ✗ ────────────────│                      │
  │                           │                          │                      │
  │                           │  Create fallback plan:   │                      │
  │                           │  ┌────────────────────┐  │                      │
  │                           │  │ method: "text"     │  │                      │
  │                           │  │ query: "rusty pipes│  │                      │
  │                           │  │ (raw user input)   │  │                      │
  │                           │  │ fallback: true     │  │                      │
  │                           │  └────────────────────┘  │                      │
  │                           │                          │                      │
  │                           │  execute_search_text()   │                      │
  │                           │─────────────────────────>│  search_by_text()    │
  │                           │                          │  (standard CLIP      │
  │                           │                          │   vector search)     │
  │                           │  results                 │                      │
  │                           │<─────────────────────────│                      │
  │                           │                          │                      │
  │  AgentSearchResponse      │                          │                      │
  │  {                        │                          │                      │
  │    fallback_used: true,   │                          │                      │
  │    search_plan: {         │                          │                      │
  │      reasoning: "Fallback:│                          │                      │
  │        LLM planning       │                          │                      │
  │        failed..."         │                          │                      │
  │    }                      │                          │                      │
  │  }                        │                          │                      │
  │ <─────────────────────────│                          │                      │
```

---

## 5. Tool Calling Decision Tree

```
                         User Query
                             │
                             ▼
                ┌─────────────────────────┐
                │  Does query mention     │
                │  a specific item ID     │
                │  or "similar to"?       │
                └─────────┬───────────────┘
                     yes/ │ \no
                    /     │  \
                   ▼      │   ▼
        ┌──────────────┐  │  ┌────────────────────────────┐
        │search_similar │  │  │ Does query mention a       │
        │              │  │  │ location, label, or shift  │
        │  (item_id,   │  │  │ that might need            │
        │   item_type) │  │  │ normalization?              │
        └──────────────┘  │  └───────────┬────────────────┘
                          │         yes/ │ \no
                          │        /     │  \
                          │       ▼      │   ▼
                          │ ┌──────────────────┐  ┌──────────────────┐
                          │ │get_available_     │  │  search_text     │
                          │ │metadata()         │  │                  │
                          │ │                   │  │  (query_text +   │
                          │ │ Returns real      │  │   extracted      │
                          │ │ filter values     │  │   filters)       │
                          │ │                   │  │                  │
                          │ │ Then on next turn:│  └──────────────────┘
                          │ │ → search_text()   │
                          │ │   with normalized │
                          │ │   filter values   │
                          │ └──────────────────┘
```

---

## 6. Agent Orchestration Loop (Internal Logic)

```
┌─────────────────────────────────────────────────────────────────────┐
│                    _run_llm_planning(request, ctx)                   │
│                                                                     │
│  messages = [{role: "user", content: request.query}]                │
│  system_prompt = AGENT_SYSTEM_PROMPT.format(today=today)            │
│                                                                     │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │  for turn in range(MAX_LLM_TURNS):     # default: 3         │   │
│  │      │                                                       │   │
│  │      ▼                                                       │   │
│  │  response = client.chat_with_tools(                          │   │
│  │      messages, AGENT_TOOLS, system_prompt                    │   │
│  │  )                                                           │   │
│  │      │                                                       │   │
│  │      ├─── response has no tool_calls?                        │   │
│  │      │         │ yes                                         │   │
│  │      │         ▼                                             │   │
│  │      │    BREAK → fall through to fallback below             │   │
│  │      │                                                       │   │
│  │      ├─── tool_call.name == "get_available_metadata"?        │   │
│  │      │         │ yes                                         │   │
│  │      │         ▼                                             │   │
│  │      │    metadata = execute_get_metadata(tenant)            │   │
│  │      │    messages.append(assistant_message)                  │   │
│  │      │    messages.append(tool_result(metadata))              │   │
│  │      │    CONTINUE → next turn                               │   │
│  │      │                                                       │   │
│  │      ├─── tool_call.name == "search_text"?                   │   │
│  │      │         │ yes                                         │   │
│  │      │         ▼                                             │   │
│  │      │    RETURN SearchPlan(                                  │   │
│  │      │        method="text",                                  │   │
│  │      │        query_text=args.query_text,                     │   │
│  │      │        filters=extract_filters(args)                   │   │
│  │      │    )                                                   │   │
│  │      │                                                       │   │
│  │      └─── tool_call.name == "search_similar"?                │   │
│  │                │ yes                                         │   │
│  │                ▼                                             │   │
│  │           RETURN SearchPlan(                                  │   │
│  │               method="similar",                               │   │
│  │               item_id=args.item_id,                           │   │
│  │               item_type=args.item_type                        │   │
│  │           )                                                   │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                                                                     │
│  # Loop exhausted without a search tool call:                       │
│  RETURN SearchPlan(                                                  │
│      method="text",                                                  │
│      query_text=request.query,   # raw user input                    │
│      reasoning="LLM did not produce a search tool call"              │
│  )                                                                   │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 7. File Structure (Complete)

```
backend/
├── infrastructure/
│   ├── llm/                              ← NEW MODULE
│   │   ├── __init__.py                   # Exports: BaseLLMClient, ToolCall, LLMResponse, get_llm_client
│   │   ├── base.py                       # BaseLLMClient ABC + ToolCall/LLMResponse dataclasses
│   │   ├── anthropic_client.py           # AnthropicLLMClient (AsyncAnthropic SDK)
│   │   ├── openai_client.py              # OpenAILLMClient (AsyncOpenAI SDK)
│   │   ├── ollama_client.py              # OllamaLLMClient (httpx → /api/chat)
│   │   ├── factory.py                    # get_llm_client() singleton factory
│   │   └── prompts.py                    # AGENT_SYSTEM_PROMPT template
│   ├── embeddings/                       # (existing, untouched)
│   ├── vectordb/                         # (existing, untouched)
│   └── storage/                          # (existing, untouched)
│
├── api/routers/
│   ├── agent/                            ← NEW ROUTER (auto-discovered)
│   │   ├── __init__.py                   # from . import endpoint
│   │   ├── endpoint.py                   # TimedRoute + auto-discovery (same pattern as search/)
│   │   ├── schemas.py                    # AgentSearchRequest, SearchPlan, AgentSearchResponse
│   │   ├── tools.py                      # AGENT_TOOLS definitions + execute_* functions
│   │   └── queries/
│   │       ├── __init__.py
│   │       └── agent.py                  # POST /agent/search handler + _run_llm_planning()
│   │
│   ├── search/                           # (existing, untouched — agent reuses helpers)
│   │   ├── endpoint.py
│   │   ├── schemas.py                    # SearchFilterParams, ImageSearchResult, DetectionSearchResult
│   │   └── queries/
│   │       └── search.py                 # _build_image_result(), _build_detection_result()
│   ├── media/                            # (existing, untouched)
│   ├── upload/                           # (existing, untouched)
│   └── auth/                             # (existing, untouched)
│
├── search/
│   └── services.py                       # (existing, untouched — SearchService called by agent)
│
├── Dockerfile.backend                    ← MODIFIED (added: pip3 install anthropic openai httpx)
└── docker-compose.yml                    ← MODIFIED (added: LLM env vars to search-engine service)
```

---

## 8. Data Flow Schemas

### 8.1 Request
```json
POST /api/v1/agent/search
{
    "query": "metal pipes detected last week at AGR",
    "top_k": 10,
    "search_type": "detections",
    "filters": null,
    "enable_reasoning": false
}
```

### 8.2 LLM Tool Call (internal — not exposed to client)
```json
{
    "name": "search_text",
    "arguments": {
        "query_text": "metal pipe",
        "plant_site": "AGR",
        "date_from": "2026-03-15T00:00:00",
        "date_to": "2026-03-22T23:59:59",
        "search_type": "detections",
        "top_k": 10
    }
}
```

### 8.3 SearchPlan (returned in response for transparency)
```json
{
    "search_method": "text",
    "query_text": "metal pipe",
    "item_id": null,
    "item_type": null,
    "filters": {
        "plant_site": "AGR",
        "date_from": "2026-03-15T00:00:00",
        "date_to": "2026-03-22T23:59:59"
    },
    "top_k": 10,
    "reasoning": "LLM selected text search: 'metal pipe'"
}
```

### 8.4 Response
```json
{
    "query_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
    "original_query": "metal pipes detected last week at AGR",
    "search_plan": {
        "search_method": "text",
        "query_text": "metal pipe",
        "filters": {
            "plant_site": "AGR",
            "date_from": "2026-03-15T00:00:00",
            "date_to": "2026-03-22T23:59:59"
        },
        "top_k": 10,
        "reasoning": "LLM selected text search: 'metal pipe'"
    },
    "detection_results": [
        {
            "id": 42,
            "detection_id": "b2c3d4e5-f6a7-8901-bcde-f12345678901",
            "similarity_score": 0.87,
            "label": "metal_pipe",
            "confidence": 0.92,
            "bbox": {
                "x": 0.1,
                "y": 0.2,
                "width": 0.3,
                "height": 0.4,
                "format": "normalized"
            },
            "image_id": 15,
            "image_uuid": "c3d4e5f6-a7b8-9012-cdef-123456789012",
            "image_filename": "frame_00142.jpg",
            "image_storage_key": "images/tenant_abc/frame_00142.jpg",
            "plant_site": "AGR",
            "shift": "morning",
            "inspection_line": "Line-3",
            "captured_at": "2026-03-18T14:30:00",
            "tags": ["defect"],
            "image_url": "/api/v1/media/files/images/tenant_abc/frame_00142.jpg",
            "crop_url": null
        }
    ],
    "image_results": null,
    "total_results": 8,
    "execution_time_ms": 320,
    "llm_time_ms": 1450,
    "llm_provider": "anthropic",
    "model_version": "clip-vit-b-32",
    "agent_summary": null,
    "fallback_used": false
}
```

---

## 9. Provider-Neutral Tool Definitions

Three tools stored in Anthropic format (superset). Each provider adapts internally.

| Tool | Maps To | When Used |
|------|---------|-----------|
| `search_text` | `SearchService.search_by_text()` | Any visual/descriptive query |
| `search_similar` | `SearchService.search_similar()` | "Similar to item #X" queries |
| `get_available_metadata` | Django ORM distinct queries | Resolve informal filter terms |

### 9.1 search_text parameters

| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `query_text` | string | yes | Visual description for CLIP encoding |
| `plant_site` | string | no | Filter by plant site |
| `shift` | string | no | Filter by shift |
| `inspection_line` | string | no | Filter by inspection line |
| `labels` | string[] | no | Filter by detection labels |
| `date_from` | ISO string | no | Start of date range |
| `date_to` | ISO string | no | End of date range |
| `min_confidence` | float | no | Min confidence 0-1 |
| `max_confidence` | float | no | Max confidence 0-1 |
| `top_k` | int | no | Results count (default 10, max 50) |
| `search_type` | enum | no | `images` / `detections` / `both` |

### 9.2 search_similar parameters

| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `item_id` | int | yes | Image or detection ID |
| `item_type` | enum | yes | `image` / `detection` |
| `top_k` | int | no | Results count |
| `plant_site` | string | no | Filter results by site |
| `date_from` | ISO string | no | Date range start |
| `date_to` | ISO string | no | Date range end |

### 9.3 get_available_metadata

No parameters. Returns:
```json
{
    "plant_sites": ["AGR", "Plant_B", "Plant_C"],
    "labels": ["metal_scrap", "plastic", "wood", "contamination"],
    "shifts": ["morning", "afternoon", "night"],
    "inspection_lines": ["Line-1", "Line-2", "Line-3"]
}
```

---

## 10. Pydantic Schemas (Python)

### 10.1 AgentSearchRequest
```python
class AgentSearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=1000)
    top_k: int = Field(default=10, ge=1, le=50)
    search_type: Literal['images', 'detections', 'both'] = 'detections'
    filters: Optional[SearchFilterParams] = None    # explicit overrides
    enable_reasoning: bool = False                   # Phase 3
```

### 10.2 SearchPlan
```python
class SearchPlan(BaseModel):
    search_method: Literal['text', 'similar']
    query_text: Optional[str] = None
    item_id: Optional[int] = None
    item_type: Optional[Literal['image', 'detection']] = None
    filters: Optional[SearchFilterParams] = None
    top_k: int = 10
    reasoning: str = ""
```

### 10.3 AgentSearchResponse
```python
class AgentSearchResponse(BaseModel):
    query_id: UUID4
    original_query: str
    search_plan: SearchPlan
    image_results: Optional[List[ImageSearchResult]] = None
    detection_results: Optional[List[DetectionSearchResult]] = None
    total_results: int
    execution_time_ms: int
    llm_time_ms: int
    llm_provider: str
    model_version: str
    agent_summary: Optional[str] = None
    fallback_used: bool = False
```

### 10.4 BaseLLMClient (ABC)
```python
class BaseLLMClient(ABC):
    async def chat_with_tools(messages, tools, system_prompt, max_tokens) -> LLMResponse
    def format_tool_result(tool_call_id, result) -> Dict
    def format_assistant_message(response) -> Dict

@dataclass
class ToolCall:
    id: str
    name: str
    arguments: Dict[str, Any]

@dataclass
class LLMResponse:
    tool_calls: List[ToolCall]
    text: Optional[str]
    raw_response: Any
```

---

## 11. Phased Rollout

### Phase 1: LLM Query Parsing ✅ (IMPLEMENTED)
- LLM abstraction layer with Anthropic, OpenAI, and Ollama providers
- New `agent/` router with `POST /api/v1/agent/search`
- LLM parses NL → `search_text` or `search_similar` tool call
- `get_available_metadata` for filter value resolution
- Fallback to plain text search on LLM failure
- No streaming, no reranking

### Phase 2: Multi-Step Tool Calling (future)
- Allow LLM to chain multiple searches (text search → similar on best result)
- Feed search results back as tool results for refinement
- Add `refine_search` tool for iterative narrowing
- Increase `MAX_LLM_TURNS`

### Phase 3: Post-Retrieval Reasoning (future)
- When `enable_reasoning=True`, feed result metadata (not images) back to LLM
- LLM produces `agent_summary` explaining relevance and patterns
- Optional SSE streaming endpoint for real-time reasoning

---

## 12. Configuration

### 12.1 Environment Variables

```bash
# ── LLM Provider (pick one) ──────────────────────────────
LLM_PROVIDER=anthropic              # "anthropic" | "openai" | "ollama"
LLM_MODEL=claude-sonnet-4-20250514  # model ID (provider-specific)

# ── Provider API Keys (only the active one is required) ──
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...
OLLAMA_BASE_URL=http://host.docker.internal:11434

# ── Agent Behavior ───────────────────────────────────────
AGENT_ENABLED=true                   # kill switch
AGENT_MAX_TURNS=3                    # max LLM conversation turns
AGENT_TIMEOUT_SECONDS=10             # LLM timeout before fallback
```

### 12.2 Quick-Switch Examples

```bash
# Claude (default)
LLM_PROVIDER=anthropic
LLM_MODEL=claude-sonnet-4-20250514
ANTHROPIC_API_KEY=sk-ant-...

# OpenAI / ChatGPT
LLM_PROVIDER=openai
LLM_MODEL=gpt-4o
OPENAI_API_KEY=sk-...

# Local via Ollama (free, no API key needed)
LLM_PROVIDER=ollama
LLM_MODEL=llama3.1
OLLAMA_BASE_URL=http://host.docker.internal:11434
```

---

## 13. Performance Budget

| Item | Target |
|------|--------|
| LLM planning (cloud, 1 turn) | < 2s |
| LLM planning (cloud, 2 turns with metadata) | < 4s |
| LLM planning (Ollama local) | < 5-8s (hardware dependent) |
| Vector search (existing) | < 500ms |
| Total agent endpoint (cloud) | < 5s |
| Total agent endpoint (local) | < 10s |
| Max LLM turns | 3 (configurable) |
| Max top_k | 50 (capped in tool executors) |
| Max query length | 1000 characters |

**Key rules:**
- Never send image bytes to the LLM — only text and metadata
- Cap `top_k` at 50 in tool executors regardless of request
- `asyncio.wait_for` enforces timeout → automatic fallback to plain search
- `get_available_metadata` is lightweight (Django distinct queries, cacheable)

---

## 14. Risks and Mitigations

| Risk | Mitigation |
|------|------------|
| LLM produces invalid tool params | Pydantic validation on extraction; fallback to raw text search |
| LLM latency spikes | `asyncio.wait_for` with configurable timeout (default 10s) |
| LLM hallucinates filter values | `get_available_metadata` tool resolves against real DB values |
| Cost per query (cloud providers) | Monitor usage; cache common patterns; use Ollama for free |
| LLM API down | Automatic fallback to text search; `AGENT_ENABLED=false` kill switch |
| Ollama weak tool calling | Validate strictly; fallback aggressively on parse failure |
| Provider format differences | Abstraction layer normalizes all responses to `ToolCall` dataclass |
| Concurrent request load | Singleton LLM client with async SDK; no thread-safety issues |

---

## 15. Key Integration Points (Existing Code Reused)

| What | File | Usage |
|------|------|-------|
| `SearchService` | `backend/search/services.py` | Agent tools call `search_by_text()`, `search_similar()` |
| `_build_image_result()` | `backend/api/routers/search/queries/search.py:41` | Builds image results from vector payloads |
| `_build_detection_result()` | `backend/api/routers/search/queries/search.py:75` | Builds detection results from vector payloads |
| `SearchFilterParams` | `backend/api/routers/search/schemas.py:17` | Filter schema reused in agent request/plan |
| `ImageSearchResult` | `backend/api/routers/search/schemas.py:71` | Result schema reused in agent response |
| `DetectionSearchResult` | `backend/api/routers/search/schemas.py:102` | Result schema reused in agent response |
| `require_scope('search')` | `backend/api/dependencies.py:119` | Same auth dependency as existing search endpoints |
| `ModelVersion.objects.get(is_active=True)` | `backend/embeddings/models.py` | Gets active embedding model name for response |
| Router auto-discovery | `backend/api/main.py` | No changes needed — new router picked up automatically |

---

## 16. Verification & Testing

### 16.1 Deploy
```bash
# Rebuild the backend container
docker compose up --build search-engine -d

# Check logs for router discovery
docker compose logs search-engine | grep -i agent
```

### 16.2 Swagger
Visit `http://localhost:8000/docs` and verify `/api/v1/agent/search` appears in the endpoint list.

### 16.3 Test with curl
```bash
# Authenticate first
TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/token \
  -H "Content-Type: application/json" \
  -d '{"email": "admin@example.com", "password": "yourpassword"}' | jq -r '.access')

# Agent search
curl -X POST http://localhost:8000/api/v1/agent/search \
  -H "Authorization: Bearer $TOKEN" \
  -H "X-Tenant-ID: <your-tenant-uuid>" \
  -H "Content-Type: application/json" \
  -d '{"query": "metal pipes detected last week at AGR"}'
```

### 16.4 Test Queries

| Query | Expected Behavior |
|-------|-------------------|
| `"metal pipes detected last week at AGR"` | text search + plant_site="AGR" + date_from/date_to |
| `"large objects causing blockage"` | text search, no filters |
| `"show me images from night shift"` | text search + shift filter, search_type="images" |
| `"unusual contamination events"` | text search, broad CLIP query |
| `"similar to detection 42"` | similarity search, item_id=42, item_type="detection" |

### 16.5 Test Fallback
```bash
# Set invalid API key to trigger fallback
ANTHROPIC_API_KEY=invalid docker compose up search-engine -d

# Search should still work (fallback_used: true in response)
curl -X POST http://localhost:8000/api/v1/agent/search \
  -H "Authorization: Bearer $TOKEN" \
  -H "X-Tenant-ID: <uuid>" \
  -H "Content-Type: application/json" \
  -d '{"query": "metal pipes"}'
```

### 16.6 Test Provider Swap
```bash
# Switch to OpenAI
LLM_PROVIDER=openai LLM_MODEL=gpt-4o OPENAI_API_KEY=sk-... docker compose up search-engine -d

# Same endpoint, same request format, different LLM backend
curl -X POST http://localhost:8000/api/v1/agent/search \
  -H "Authorization: Bearer $TOKEN" \
  -H "X-Tenant-ID: <uuid>" \
  -H "Content-Type: application/json" \
  -d '{"query": "metal pipes detected last week at AGR"}'
# Response should have llm_provider: "openai"
```
