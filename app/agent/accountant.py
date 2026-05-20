"""The accountant agent loop: Claude + tool use."""
import json
from flask import current_app
from anthropic import Anthropic
from app.agent.prompts import SYSTEM_PROMPT
from app.agent.tools import TOOL_SCHEMAS, execute_tool


def _client():
    api_key = current_app.config.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY غير مضبوط في .env")
    return Anthropic(api_key=api_key)


def run_agent(messages, company_id, user_id, company_context=None, max_iters=8):
    """Run a conversation turn with the agent.

    messages: list of {role, content} dicts (Anthropic format)
    Returns: (final_text, updated_messages, tool_trace)
    """
    client = _client()
    model = current_app.config.get("ANTHROPIC_MODEL", "claude-sonnet-4-5")

    system = SYSTEM_PROMPT
    if company_context:
        system += f"\n\nسياق الشركة الحالية:\n{company_context}"

    tool_trace = []
    iterations = 0
    final_text = ""

    while iterations < max_iters:
        iterations += 1
        response = client.messages.create(
            model=model,
            max_tokens=4096,
            system=system,
            tools=TOOL_SCHEMAS,
            messages=messages,
        )

        # Collect assistant content
        assistant_content = []
        tool_uses = []
        for block in response.content:
            if block.type == "text":
                assistant_content.append({"type": "text", "text": block.text})
                final_text += block.text
            elif block.type == "tool_use":
                assistant_content.append({
                    "type": "tool_use",
                    "id": block.id,
                    "name": block.name,
                    "input": block.input,
                })
                tool_uses.append(block)

        messages.append({"role": "assistant", "content": assistant_content})

        if response.stop_reason != "tool_use" or not tool_uses:
            break

        # Execute each tool and feed results back
        tool_results = []
        for tu in tool_uses:
            result = execute_tool(tu.name, tu.input, company_id, user_id)
            tool_trace.append({"tool": tu.name, "input": tu.input, "result": result})
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": tu.id,
                "content": json.dumps(result, default=str, ensure_ascii=False),
            })
        messages.append({"role": "user", "content": tool_results})
        final_text = ""  # reset; final text only from last assistant turn

    return final_text, messages, tool_trace
