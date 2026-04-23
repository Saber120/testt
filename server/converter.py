"""Convert OpenAI-format messages to Ollama format.

Handles role mapping, content extraction, and tool call translation
between the two API formats.
"""

from .utils import json_loads, json_dumps


def extract_text_content(content):
    """Extract plain text from OpenAI content field.

    Handles string content and multimodal content arrays,
    returning only the text portions joined with spaces.

    Args:
        content: String, list of content items, or None.

    Returns:
        str: Extracted text content.
    """
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        texts = [item.get("text", "") for item in content if isinstance(item, dict) and item.get("type") == "text"]
        return " ".join(texts) if texts else ""
    return str(content)


def convert_messages_to_ollama(messages):
    """Convert OpenAI chat messages to Ollama format.

    Maps roles, extracts text content, and translates tool calls
    from OpenAI format to Ollama's expected structure.

    Args:
        messages: List of OpenAI-format message dicts.

    Returns:
        list: List of Ollama-format message dicts.
    """
    ollama_messages = []
    for m in messages:
        role = m.get("role")
        content = extract_text_content(m.get("content"))

        if role == "tool":
            tool_msg = {"role": "tool", "content": content or ""}
            if "tool_call_id" in m:
                tool_msg["tool_call_id"] = m["tool_call_id"]
            ollama_messages.append(tool_msg)
        elif role == "assistant":
            asst_msg = {"role": "assistant", "content": content or ""}
            if "tool_calls" in m and m["tool_calls"]:
                ollama_tc = []
                for tc in m["tool_calls"]:
                    func = tc.get("function", {})
                    args = func.get("arguments", "{}")
                    if isinstance(args, str):
                        try:
                            args = json_loads(args)
                        except (ValueError, TypeError):
                            args = {}
                    ollama_tc.append({"function": {"name": func.get("name", ""), "arguments": args}})
                asst_msg["tool_calls"] = ollama_tc
            ollama_messages.append(asst_msg)
        elif role == "system":
            ollama_messages.append({"role": "system", "content": content})
        elif role == "user" and content.strip():
            ollama_messages.append({"role": "user", "content": content})
    return ollama_messages
