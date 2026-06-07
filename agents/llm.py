"""Google Gemini Flash LLM wrapper with proper Phoenix/OpenInference tracing.

Span hierarchy:
  crew_request (CHAIN, session.id) 
    ├── safety_agent (LLM)
    ├── data_agent (AGENT)
    │     └── llm_call (LLM)
    └── advisor_agent (LLM)
"""
import os, time, json
import requests as http_requests
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("GOOGLE_API_KEY")
BASE_URL = "https://generativelanguage.googleapis.com/v1beta"
MODEL = "gemini-2.5-flash"

# ===== Phoenix/OpenInference tracing setup =====
_tracing_ok = False
try:
    from opentelemetry import trace, context as otel_context
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.resources import Resource

    resource = Resource.create({"service.name": "personal-finance-crew"})
    provider = TracerProvider(resource=resource)
    provider.add_span_processor(SimpleSpanProcessor(
        OTLPSpanExporter(endpoint="http://localhost:6006/v1/traces")
    ))
    trace.set_tracer_provider(provider)
    tracer = trace.get_tracer("personal-finance-crew")
    _tracing_ok = True
except Exception as e:
    tracer = None
    print(f"Tracing disabled: {e}")


# ===== Context management for parent spans =====

def start_request_span(name: str, session_id: str, input_text: str, span_kind: str = "CHAIN"):
    """Start a parent request span. Returns (span, context_token)."""
    if not _tracing_ok:
        return None, None
    span = tracer.start_span(name, attributes={
        "openinference.span.kind": span_kind,
        "session.id": session_id,
        "input.value": input_text,
        "input.mime_type": "text/plain",
    })
    token = otel_context.attach(trace.set_span_in_context(span))
    return span, token


def end_request_span(span, token, output_text: str = ""):
    """End a parent request span."""
    if span:
        span.set_attribute("output.value", output_text[:1000])
        span.set_attribute("output.mime_type", "text/plain")
        span.end()
    if token:
        otel_context.detach(token)


# ===== LLM call with OpenInference attributes =====

def call_llm(messages: list[dict], system: str = None, temperature: float = 0.3,
             agent_name: str = "llm") -> dict:
    """Call Gemini Flash with proper OpenInference LLM span."""
    start = time.time()

    # Start LLM span as child of current context
    span = None
    span_token = None
    if _tracing_ok:
        span = tracer.start_span(f"llm.{agent_name}", attributes={
            "openinference.span.kind": "LLM",
            "llm.model_name": MODEL,
            "llm.invocation_parameters": json.dumps({"temperature": temperature}),
        })
        span_token = otel_context.attach(trace.set_span_in_context(span))
        # Set input messages per OpenInference convention
        for i, m in enumerate(messages):
            span.set_attribute(f"llm.input_messages.{i}.message.role", m["role"])
            span.set_attribute(f"llm.input_messages.{i}.message.content", m["content"][:500])
        if system:
            span.set_attribute("llm.system", system[:500])

    # Build request
    contents = []
    for m in messages:
        role = "user" if m["role"] == "user" else "model"
        contents.append({"role": role, "parts": [{"text": m["content"]}]})

    body = {"contents": contents, "generationConfig": {"temperature": temperature}}
    if system:
        body["systemInstruction"] = {"parts": [{"text": system}]}

    resp = http_requests.post(
        f"{BASE_URL}/models/{MODEL}:generateContent?key={API_KEY}",
        json=body, timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()

    latency = int((time.time() - start) * 1000)
    text = ""
    if "candidates" in data and data["candidates"]:
        parts = data["candidates"][0].get("content", {}).get("parts", [])
        text = "".join(p.get("text", "") for p in parts)

    usage_meta = data.get("usageMetadata", {})
    usage = {
        "input_tokens": usage_meta.get("promptTokenCount", 0),
        "output_tokens": usage_meta.get("candidatesTokenCount", 0),
    }

    # Set output on span
    if span:
        span.set_attribute("llm.output_messages.0.message.role", "assistant")
        span.set_attribute("llm.output_messages.0.message.content", text[:1000])
        span.set_attribute("llm.token_count.prompt", usage["input_tokens"])
        span.set_attribute("llm.token_count.completion", usage["output_tokens"])
        span.set_attribute("llm.token_count.total", usage["input_tokens"] + usage["output_tokens"])
        span.set_attribute("output.value", text[:1000])
        span.set_attribute("output.mime_type", "text/plain")
        span.end()
        otel_context.detach(span_token)

    return {"text": text, "usage": usage, "latency_ms": latency}


def call_llm_with_tools(messages: list[dict], tools_schema: list[dict],
                        system: str = None, temperature: float = 0.1,
                        agent_name: str = "llm") -> dict:
    """Call Gemini with function calling, traced as LLM span."""
    start = time.time()

    span = None
    span_token = None
    if _tracing_ok:
        span = tracer.start_span(f"llm_tools.{agent_name}", attributes={
            "openinference.span.kind": "LLM",
            "llm.model_name": MODEL,
            "llm.invocation_parameters": json.dumps({"temperature": temperature}),
        })
        span_token = otel_context.attach(trace.set_span_in_context(span))
        for i, m in enumerate(messages[-3:]):  # last 3 to avoid huge spans
            span.set_attribute(f"llm.input_messages.{i}.message.role", m["role"])
            span.set_attribute(f"llm.input_messages.{i}.message.content", m["content"][:300])
        # Log available tools
        for i, t in enumerate(tools_schema):
            span.set_attribute(f"llm.tools.{i}.tool.json_schema", json.dumps({"type": "function", "function": {"name": t["name"], "description": t["description"]}}))

    contents = []
    for m in messages:
        if m["role"] == "user":
            contents.append({"role": "user", "parts": [{"text": m["content"]}]})
        elif m["role"] == "assistant":
            contents.append({"role": "model", "parts": [{"text": m["content"]}]})
        elif m["role"] == "tool_result":
            contents.append({"role": "user", "parts": [{"text": f"Tool result: {m['content']}"}]})

    func_declarations = []
    for t in tools_schema:
        decl = {"name": t["name"], "description": t["description"]}
        if t.get("parameters") and t["parameters"].get("properties"):
            decl["parameters"] = {
                "type": "OBJECT",
                "properties": {
                    k: {"type": v.get("type", "STRING").upper(), "description": v.get("description", "")}
                    for k, v in t["parameters"]["properties"].items()
                },
            }
            if t["parameters"].get("required"):
                decl["parameters"]["required"] = t["parameters"]["required"]
        func_declarations.append(decl)

    body = {
        "contents": contents,
        "generationConfig": {"temperature": temperature},
        "tools": [{"functionDeclarations": func_declarations}],
        "toolConfig": {"functionCallingConfig": {"mode": "AUTO"}},
    }
    if system:
        body["systemInstruction"] = {"parts": [{"text": system}]}

    resp = http_requests.post(
        f"{BASE_URL}/models/{MODEL}:generateContent?key={API_KEY}",
        json=body, timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()

    latency = int((time.time() - start) * 1000)
    text = ""
    tool_calls = []

    if "candidates" in data and data["candidates"]:
        parts = data["candidates"][0].get("content", {}).get("parts", [])
        for part in parts:
            if "text" in part:
                text += part["text"]
            if "functionCall" in part:
                fc = part["functionCall"]
                tool_calls.append({"name": fc["name"], "args": fc.get("args", {})})

    usage_meta = data.get("usageMetadata", {})
    usage = {
        "input_tokens": usage_meta.get("promptTokenCount", 0),
        "output_tokens": usage_meta.get("candidatesTokenCount", 0),
    }

    if span:
        if text:
            span.set_attribute("llm.output_messages.0.message.role", "assistant")
            span.set_attribute("llm.output_messages.0.message.content", text[:500])
        for i, tc in enumerate(tool_calls):
            span.set_attribute(f"llm.output_messages.0.message.tool_calls.{i}.tool_call.function.name", tc["name"])
            span.set_attribute(f"llm.output_messages.0.message.tool_calls.{i}.tool_call.function.arguments", json.dumps(tc["args"]))
        span.set_attribute("llm.token_count.prompt", usage["input_tokens"])
        span.set_attribute("llm.token_count.completion", usage["output_tokens"])
        span.set_attribute("llm.token_count.total", usage["input_tokens"] + usage["output_tokens"])
        span.set_attribute("output.value", text[:500] or json.dumps([tc["name"] for tc in tool_calls]))
        span.end()
        otel_context.detach(span_token)

    return {"text": text, "tool_calls": tool_calls, "usage": usage, "latency_ms": latency}
