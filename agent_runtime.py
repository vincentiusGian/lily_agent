import json
import httpx
from context_builder import build_system_prompt

# Max times the agent can call tools before stopping
MAX_TOOL_ROUNDS = 5

class AgentRuntime:
    def __init__(self, provider, model, api_key, skills, memory):
        self.provider = provider  # "anthropic" | "groq" | "openrouter"
        self.model = model
        self.api_key = api_key
        self.skills = skills
        self.memory = memory

    async def run(self, history, session_id, callbacks):
        on_token = callbacks.get("on_token")
        on_tool_use = callbacks.get("on_tool_use")

        system_prompt = build_system_prompt(self.skills.get_active_skills(), self.memory)
        messages = [{"role": m["role"], "content": m["content"]} for m in history]
        tools = self.skills.get_tools()

        response = ""
        rounds = 0

        while rounds < MAX_TOOL_ROUNDS:
            rounds += 1

            # Route to the correct provider
            if self.provider == "anthropic":
                result = await self._call_anthropic(system_prompt, messages, tools or None)
            elif self.provider == "groq":
                result = await self._call_openai_compatible(
                    system_prompt, messages, tools or None,
                    base_url="https://api.groq.com/openai/v1",
                )
            elif self.provider == "openrouter":
                result = await self._call_openai_compatible(
                    system_prompt, messages, tools or None,
                    base_url="https://openrouter.ai/api/v1",
                )
            else:
                raise Exception(f"Unknown provider: {self.provider}")

            if result["tool_calls"]:
                if self.provider == "anthropic":
                    messages.append({"role": "assistant", "content": result["raw_content"]})
                else:
                    # For Groq/OpenRouter: raw_content is already the full message dict
                    messages.append(result["raw_content"])

                for tool_call in result["tool_calls"]:
                    if on_tool_use:
                        await on_tool_use(tool_call["name"], tool_call["input"])

                    tool_result = await self.skills.execute_tool(
                        tool_call["name"],
                        tool_call["input"],
                        {"session_id": session_id, "memory": self.memory},
                    )

                    # Anthropic uses tool_result blocks; OpenAI-compatible uses tool role
                    if self.provider == "anthropic":
                        messages.append({
                            "role": "user",
                            "content": [{
                                "type": "tool_result",
                                "tool_use_id": tool_call["id"],
                                "content": json.dumps(tool_result),
                            }],
                        })
                    else:
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tool_call["id"],
                            "content": json.dumps(tool_result),
                        })

                continue

            if result["text"]:
                if on_token:
                    await on_token(result["text"])
                response = result["text"]

            break

        return response

    # ------------------------------------------------------------------ #
    #  Anthropic                                                           #
    # ------------------------------------------------------------------ #
    async def _call_anthropic(self, system_prompt, messages, tools):
        body = {
            "model": self.model,
            "max_tokens": 4096,
            "system": system_prompt,
            "messages": messages,
        }
        if tools:
            body["tools"] = [{
                "name": t["name"],
                "description": t["description"],
                "input_schema": t["parameters"],
            } for t in tools]

        try:
            async with httpx.AsyncClient(timeout=120) as client:
                res = await client.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={
                        "Content-Type": "application/json",
                        "x-api-key": self.api_key,
                        "anthropic-version": "2023-06-01",
                    },
                    json=body,
                )
        except httpx.ConnectError as e:
            raise Exception(f"Could not connect to Anthropic API: {e}")
        except httpx.TimeoutException as e:
            raise Exception(f"Anthropic API timed out: {e}")

        if res.status_code != 200:
            raise Exception(f"Anthropic API error ({res.status_code}): {res.text}")

        data = res.json()
        text_parts, tool_calls = [], []
        for block in data["content"]:
            if block["type"] == "text":
                text_parts.append(block["text"])
            elif block["type"] == "tool_use":
                tool_calls.append({"id": block["id"], "name": block["name"], "input": block["input"]})

        return {"text": "".join(text_parts), "tool_calls": tool_calls or None, "raw_content": data["content"]}

    # ------------------------------------------------------------------ #
    #  OpenAI-compatible  (Groq & OpenRouter share the same format)       #
    # ------------------------------------------------------------------ #
    async def _call_openai_compatible(self, system_prompt, messages, tools, base_url):
        full_messages = [{"role": "system", "content": system_prompt}] + messages

        body = {
            "model": self.model,
            "max_tokens": 4096,
            "messages": full_messages,
        }
        if tools:
            body["tools"] = [{
                "type": "function",
                "function": {
                    "name": t["name"],
                    "description": t["description"],
                    "parameters": t["parameters"],
                },
            } for t in tools]
            body["tool_choice"] = "auto"

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }
        # OpenRouter needs a site URL header (any value is fine for testing)
        if "openrouter" in base_url:
            headers["HTTP-Referer"] = "https://github.com/your-bot"

        try:
            async with httpx.AsyncClient(timeout=120) as client:
                res = await client.post(
                    f"{base_url}/chat/completions",
                    headers=headers,
                    json=body,
                )
        except httpx.ConnectError as e:
            raise Exception(f"Could not connect to {base_url}: {e}")
        except httpx.TimeoutException as e:
            raise Exception(f"API timed out ({base_url}): {e}")

        if res.status_code != 200:
            raise Exception(f"API error ({res.status_code}): {res.text}")

        data = res.json()
        message = data["choices"][0]["message"]
        text = message.get("content") or ""
        raw_tool_calls = message.get("tool_calls") or []

        tool_calls = []
        for tc in raw_tool_calls:
            fn = tc["function"]
            try:
                parsed_input = json.loads(fn["arguments"])
            except json.JSONDecodeError:
                parsed_input = {}
            tool_calls.append({"id": tc["id"], "name": fn["name"], "input": parsed_input})

        # raw_content must be a proper assistant message dict (with role)
        # so it can be appended directly to messages in the next round
        raw_content = {
            "role": "assistant",
            "content": text or None,
            "tool_calls": raw_tool_calls if raw_tool_calls else None,
        }

        return {"text": text, "tool_calls": tool_calls or None, "raw_content": raw_content}
