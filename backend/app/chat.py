"""Tool-using chat loop: Claude explores one client's dataset via get_schema / run_sql."""
import json

import anthropic

from . import data, storage
from .config import (DEFAULT_MODEL, FILE_KINDS, MAX_TOOL_RESULT_CHARS, MAX_TOOL_ROUNDS, MODELS)

TOOLS = [
    {
        "name": "get_schema",
        "description": "Return every table (activities, members, member_profile, open_ends, closed_ends) "
                       "with row counts, column names/types and a few sample rows. Call this first.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "run_sql",
        "description": "Run ONE read-only DuckDB SQL SELECT against the client's tables. "
                       "Results are capped; aggregate in SQL rather than pulling raw rows when possible.",
        "input_schema": {
            "type": "object",
            "properties": {"sql": {"type": "string", "description": "A single SELECT/WITH query."}},
            "required": ["sql"],
        },
    },
]


STYLE = {
    "short": """Answer style: SHORT. Lead with the direct answer in 1-3 sentences or a compact table (max ~8 rows). \
No preamble, no restating the question, no methodology, no caveats unless they change the answer. \
Include n for key numbers. Offer one short follow-up only if truly useful. Under ~120 words unless a table is needed.""",
    "detailed": """Answer style: DETAILED. Give a thorough analysis: key findings, supporting numbers with n, \
segment comparisons, representative verbatims for qualitative themes, and relevant caveats.""",
}


def _system_prompt(client: dict, detail: str = "short") -> str:
    notes = "\n".join(
        f"- {FILE_KINDS[k]} (table `{k}`): {client['notes'].get(k) or '(no description provided yet)'}"
        for k in FILE_KINDS
    )
    return f"""You are a research analyst assistant for the client "{client['name']}".
You answer questions using ONLY this client's data from a community-driven qualitative research panel.
Never use or mention data from other clients, and never invent data.

Domain background:
- Members (unique member ID) take part in activities (unique activity ID) of these types: Survey, Discussion, Conversation, Simple Survey, Quick Poll.
- Members have static profile fields used to segment/filter results.
- Participation data exists at the member x activity level (open-end and closed-end responses).

Data preparation already applied (do not re-filter for these):
- Only the five activity types above are present, as ActivityType = Survey, Discussion, Conversation, Simple Survey, Quick Poll.
- Members removed for low quality are excluded everywhere; non-member (moderator/staff) contributions are excluded.
- `member_profile` is one row per member (MemberId) with one column per demographic/firmographic field; names are not available.
- Closed-end answers are in AnswerLabel; a multi-select question has several rows per member. QuestionText is plain text.
- Open-end responses carry ActivityId but are not linked to a specific survey question; ParentContributionId marks replies.
- Very short open-end values such as "0" or "1" are often not real verbatims; ignore them when summarising themes.

Client description: {client['description'] or '(none)'}

Dataset (SQL tables):
{notes}

How to work:
1. Call get_schema first if you have not seen the schema, then use run_sql to compute answers.
2. Prefer SQL aggregation. Join tables on member/activity IDs found in the schema.
3. Report sample sizes (n) with any percentage or comparison, and say so when a base is small.
4. For open-end themes, query the relevant verbatims, then summarise themes and quote short representative verbatims.
5. If the data cannot answer the question, say what is missing. Use markdown tables where helpful.

{STYLE.get(detail, STYLE['short'])}"""


def _truncate(s: str) -> str:
    if len(s) > MAX_TOOL_RESULT_CHARS:
        return s[:MAX_TOOL_RESULT_CHARS] + "\n...[truncated: refine your query]"
    return s


def _run_tool(client_id: str, name: str, args: dict) -> tuple[str, bool]:
    try:
        if name == "get_schema":
            return _truncate(json.dumps(data.describe(client_id), default=str)), False
        if name == "run_sql":
            return _truncate(json.dumps(data.run_sql(client_id, args.get("sql", "")), default=str)), False
        return f"Unknown tool {name}", True
    except Exception as e:  # return errors to the model so it can self-correct
        return f"Error: {e}", True


def answer(client_id: str, history: list[dict], model_key: str | None = None, detail: str = "short") -> dict:
    client = storage.get_client(client_id)
    if not client["ready"]:
        missing = [k for k, v in client["files"].items() if not v]
        raise ValueError(f"Client is missing files: {', '.join(missing)}")
    model = MODELS.get(model_key or DEFAULT_MODEL, MODELS[DEFAULT_MODEL])

    api = anthropic.Anthropic()
    messages = [{"role": m["role"], "content": m["content"]} for m in history]
    trace = []

    for _ in range(MAX_TOOL_ROUNDS):
        resp = api.messages.create(model=model, max_tokens=1500 if detail == "short" else 4096,
                                   system=_system_prompt(client, detail),
                                   tools=TOOLS, messages=messages)
        if resp.stop_reason != "tool_use":
            text = "".join(b.text for b in resp.content if b.type == "text")
            return {"answer": text, "trace": trace, "model": model}

        messages.append({"role": "assistant", "content": resp.content})
        results = []
        for b in resp.content:
            if b.type == "tool_use":
                out, is_err = _run_tool(client_id, b.name, b.input)
                trace.append({"tool": b.name, "input": b.input, "error": is_err,
                              "output_preview": out[:500]})
                results.append({"type": "tool_result", "tool_use_id": b.id, "content": out,
                                "is_error": is_err})
        messages.append({"role": "user", "content": results})

    return {"answer": "I hit the tool-call limit before finishing. Try a narrower question.",
            "trace": trace, "model": model}
