from playwright.async_api import async_playwright

# Global browser state that is initialized on first tool call
_browser = None
_page = None

async def _get_page():
    global _browser, _page

    # If a browser and page are already active, reuse them instead of reopening
    if _browser and _page:
        return _page

    # Start Playwright
    pw = await async_playwright().start()

    # Launch a new Chromium browser instance
    # 'headless=False' means that the browser window will be visible during execution
    _browser = await pw.chromium.launch(headless=False)

    # Open a new page (tab) in the launched browser
    _page = await _browser.new_page()

    return _page

# Tool definitions for available tools
tools = [
    {
        "name": "browse_url",
        "description": "Navigate to a URL and return the page title and text content.",
        "parameters": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "The URL to visit"},
            },
            "required": ["url"],
        },
    },
    {
        "name": "click_element",
        "description": "Click an element on the page by CSS selector or text.",
        "parameters": {
            "type": "object",
            "properties": {
                "selector": {
                    "type": "string",
                    "description": "CSS selector or text content, e.g. 'button.submit' or 'text=Sign In'",
                },
            },
            "required": ["selector"],
        },
    },
    {
        "name": "fill_input",
        "description": "Type text into an input field.",
        "parameters": {
            "type": "object",
            "properties": {
                "selector": {"type": "string", "description": "CSS selector for the input"},
                "text": {"type": "string", "description": "Text to type"},
            },
            "required": ["selector", "text"],
        },
    },
    {
        "name": "get_page_content",
        "description": "Get the text content of the current page or a specific element.",
        "parameters": {
            "type": "object",
            "properties": {
                "selector": {
                    "type": "string",
                    "description": "Optional CSS selector to extract text from, e.g. '#title' or '.content' If empty, returns full page text.",
                },
            },
            "required": [],
        },
    },
]

# Function called when the agent invokes a tool
async def execute(tool_name, tool_input, context):
    try:
        # Create a browser page
        page = await _get_page()

        if tool_name == "browse_url":
            url = tool_input["url"] # Extract the URL from the tool input

            # Add "https://" if the URL doesn’t already include it
            if not url.startswith("http"):
                url = "https://" + url 
            
            # Visit URL ('wait_until' ensures the DOM is ready, 'timeout' prevent hanging indefinitely)
            await page.goto(url, wait_until="domcontentloaded", timeout=10000)

            # Get the page title
            title = await page.title()

            # Get the all text from the <body> element
            text = await page.inner_text("body")

            # Return a structured response
            return {
                "title": title,
                "url": page.url,
                "content_preview": text.strip()[:3000],  # Trim to stay within LLM context limits
            }

        elif tool_name == "click_element":
            # Click using a CSS selector ('timeout' prevent hanging if element isn't found)
            await page.click(tool_input["selector"], timeout=3000)
            
            # Wait for page to update after the click
            await page.wait_for_load_state("domcontentloaded")

            # Return a structured response
            return {
                "clicked": tool_input["selector"],
                "new_url": page.url,
                "new_title": await page.title(),
            }

        elif tool_name == "fill_input":
            # Fill the specified input field with given text
            await page.fill(tool_input["selector"], tool_input["text"])
            
            # Return a structured response for confirmation
            return {
                "filled": tool_input["selector"],
                "text": tool_input["text"],
            }

        elif tool_name == "get_page_content":
            # Use the given selector or the page body
            selector = tool_input.get("selector") or "body"

            # Extract text from selected element 
            text = await page.inner_text(selector)

            # Return trimmed content to stay within LLM context limits
            return {
                "url": page.url,
                "content": text.strip()[:5000],
            }

        # elif tool_name == "get_form_fields":
        #     fields = await page.evaluate("""
        #         () => {
        #             const inputs = document.querySelectorAll('input, textarea, select, button');
        #             return Array.from(inputs).map(el => ({
        #                 tag: el.tagName.toLowerCase(),
        #                 type: el.type || '',
        #                 name: el.name || '',
        #                 id: el.id || '',
        #                 placeholder: el.placeholder || '',
        #                 selector: el.id ? '#' + el.id : 
        #                           el.name ? el.tagName.toLowerCase() + '[name="' + el.name + '"]' : '',
        #             }));
        #         }
        #     """)
        #     return {"fields": fields}
        
        # Handle error for unknown tool
        return {"error": f"Unknown tool: {tool_name}"}

    except Exception as e:
        return {"error": str(e)}
