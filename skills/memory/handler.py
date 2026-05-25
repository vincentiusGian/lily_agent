tools = [
    {
        "name": "save_note",
        "description": "Save a note or fact about the user to memory.",
        "parameters": {
            "type": "object",
            "properties": {
                "key": {"type": "string", "description": "Short descriptive key"},
                "content": {"type": "string", "description": "Note content"},
            },
            "required": ["key", "content"],
        },
    },
]

# Function called when the agent invokes this tool
async def execute(tool_name, tool_input, context):
    memory = context["memory"]

    if tool_name == "save_note":
        # Save to memory
        memory.set(f"note:{tool_input['key']}", {
            "content": tool_input["content"],
        })

        return {"success": True, "key": tool_input["key"]}

    return {"error": f"Unknown tool: {tool_name}"}
