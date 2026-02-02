# NEAR AI Tool Calling Issue Report

## Issue Summary
When using NEAR AI's OpenAI-compatible endpoint with LangChain's tool calling feature, the model correctly identifies and calls tools, but returns **empty responses** after receiving tool results via `ToolMessage`.

## Environment
- **Endpoint**: `https://cloud-api.near.ai/v1`
- **Model**: `openai/gpt-oss-120b`
- **Framework**: LangChain (`langchain-openai`)
- **Tool binding**: `llm.bind_tools()`
- **Message format**: OpenAI-standard `ToolMessage`

## Steps to Reproduce

1. **Create a tool and bind to LLM:**
```python
from langchain_core.tools import tool

@tool
def get_weather(location: str) -> str:
    """Get the weather for a location."""
    return f"The weather in {location} is sunny, 22°C"

llm_with_tools = llm.bind_tools([get_weather])
```

2. **Send initial request:**
```python
messages = [
    SystemMessage(content="You are a helpful assistant."),
    HumanMessage(content="What's the weather in Paris?")
]
response = await llm_with_tools.ainvoke(messages)
```

3. **LLM correctly calls tool:**
```python
# response.tool_calls = [{'name': 'get_weather', 'args': {'location': 'Paris'}, ...}]
✓ Tool calling works!
```

4. **Execute tool and send result back:**
```python
tool_result = await get_weather.ainvoke({'location': 'Paris'})
# tool_result = "The weather in Paris is sunny, 22°C"

messages.append(response)  # AIMessage with tool_calls
messages.append(ToolMessage(
    content=tool_result,
    tool_call_id=response.tool_calls[0]['id']
))

final_response = await llm.ainvoke(messages)
```

5. **Result: Empty response**
```python
final_response.content = ""  # ❌ Empty string!
```

## Expected Behavior
After receiving the tool result, the LLM should summarize it:
```
"The weather in Paris is sunny with a temperature of 22°C."
```

## Actual Behavior
```python
final_response.content = ""  # Empty string
```

## Workaround (Works)
Using `HumanMessage` instead of `ToolMessage`:
```python
messages = [
    SystemMessage(content="You are a helpful assistant."),
    HumanMessage(content="What's the weather in Paris?"),
    HumanMessage(content="Tool 'get_weather' returned: The weather in Paris is sunny, 22°C")
]
response = await llm.ainvoke(messages)
# ✓ Returns proper response!
```

## Question for Community
1. Is the OpenAI-standard `ToolMessage` format fully supported by NEAR AI's endpoint?
2. Is there a different format required for sending tool results?
3. Are there any known limitations with tool calling on `openai/gpt-oss-120b`?

## Test Script
Run `near_ai_tool_issue.py` to reproduce the issue locally.

## Impact
This prevents us from using standard LangChain tool calling patterns with NEAR AI, requiring custom workarounds that bypass the standard OpenAI tool message format.
