from typing import Any, Dict
import json
import os
import sys
import asyncio
import argparse
import httpx

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import (
    ErrorData,
    GetPromptResult,
    Prompt,
    PromptArgument,
    PromptMessage,
    TextContent,
    Tool,
    INVALID_PARAMS,
    INTERNAL_ERROR,
)

# Default server settings
DEFAULT_SERVER_URL = "http://localhost:8000"
DEFAULT_ENDPOINT = "/mcp"

MAX_TOOL_OUTPUT_LENGTH = 40000 # Maximum characters for tool output to prevent exceeding Claude's limits

def truncate_preserving_early_entries(data: Any, max_length: int = MAX_TOOL_OUTPUT_LENGTH) -> Any:
    if not isinstance(data, dict) or "content" not in data or not isinstance(data["content"], list):
        return {"content": [{"type": "text", "text": "... (truncated)"}]}

    output = {"content": []}
    base_size = len(json.dumps(output))
    
    for item in data["content"]:
        if not isinstance(item, dict) or "text" not in item:
            continue
        
        item_json = json.dumps(item)
        next_size = len(json.dumps(output["content"] + [item]))
        
        if next_size <= max_length:
            output["content"].append(item)
        else:
            # If it's the first item, we still want to show part of it
            if not output["content"]:
                available_space = max_length - base_size - len(json.dumps({k: v for k, v in item.items() if k != "text"})) - 20
                truncated_text = item["text"][:available_space] + "... (truncated)"
                new_item = dict(item)
                new_item["text"] = truncated_text
                output["content"].append(new_item)
            else:
                output["content"].append({"type": "text", "text": "... (truncated)"})
            break

    return output

async def forward_to_nlweb(method: str, params: Dict[str, Any], server_url: str, endpoint: str) -> Dict[str, Any]:
    """Forward a request to the NLWeb MCP endpoint"""
    nlweb_mcp_url = f"{server_url}{endpoint}"
    try:
        # Format the request in MCP JSON-RPC 2.0 format
        payload = {
            "jsonrpc": "2.0",
            "id": 1, # Use a dummy ID as the mcp.server library manages the actual IDs
            "method": method,
            "params": params
        }
        
        print(f"Forwarding to {nlweb_mcp_url}: method={method}", file=sys.stderr)
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                nlweb_mcp_url,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=30
            )
            
            response.raise_for_status() # Raise an exception for HTTP errors (4xx or 5xx)
            
            result = response.json()
            
            if "error" in result:
                print(f"MCP error response: {result["error"]}", file=sys.stderr)
                return {"error": result["error"].get("message", "Unknown MCP error")}
            
            return {"response": result.get("result")}
            
    except httpx.HTTPStatusError as e:
        print(f"HTTP error occurred: {e.response.status_code} - {e.response.text}", file=sys.stderr)
        return {"error": f"HTTP error: {e.response.status_code} - {e.response.text}"}
    except httpx.RequestError as e:
        print(f"Request failed: {str(e)}", file=sys.stderr)
        return {"error": f"Request failed: {str(e)}"}
    except Exception as e:
        print(f"An unexpected error occurred: {str(e)}", file=sys.stderr)
        return {"error": f"An unexpected error occurred: {str(e)}"}

async def serve(server_url: str = DEFAULT_SERVER_URL, endpoint: str = DEFAULT_ENDPOINT) -> None:
    """
    Run the simplified MCP server that forwards requests to NLWeb
    
    Args:
        server_url: The NLWeb server URL
        endpoint: The NLWeb server endpoint
    """
    print(f"Starting NLWeb MCP interface - connecting to {server_url}{endpoint}", file=sys.stderr)
    server = Server("nlweb-interface")

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        """Forward list_tools request to NLWeb"""
        result = await forward_to_nlweb("tools/list", {}, server_url, endpoint)
        
        if "error" in result:
            # Fallback to default if server is unavailable
            return [
                Tool(
                    name="ask_nlw",
                    description="Connects with the NLWeb server to answer questions",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "The query string to send to the NLWeb server"
                            }
                        },
                        "required": ["query"]
                    }
                )
            ]
        
        # Extract tools from the response
        try:
            tools = result.get("response", {}).get("tools", [])
            return [Tool(
                name=tool["name"],
                description=tool["description"],
                inputSchema=tool["inputSchema"]
            ) for tool in tools]
        except (KeyError, TypeError) as e:
            print(f"Error processing tools: {str(e)}", file=sys.stderr)
            # Fallback to default
            return [
                Tool(
                    name="ask_nlw",
                    description="Connects with the NLWeb server to answer questions",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "The query string to send to the NLWeb server"
                            }
                        },
                        "required": ["query"]
                    }
                )
            ]

    @server.list_prompts()
    async def list_prompts() -> list[Prompt]:
        """Forward list_prompts request to NLWeb"""
        result = await forward_to_nlweb("tools/list_prompts", {}, server_url, endpoint)
        
        if "error" in result:
            # Fallback to default if server is unavailable
            return [
                Prompt(
                    name="ask_nlw",
                    description="Connects with the NLWeb server to answer questions",
                    arguments=[
                        PromptArgument(
                            name="query", 
                            description="query string in english", 
                            required=True
                        )
                    ]
                )
            ]
        
        # Extract prompts from the response
        try:
            prompts = result.get("response", {}).get("prompts", [])
            return [Prompt(
                name=prompt["id"],
                description=prompt["description"],
                arguments=[
                    PromptArgument(
                        name="query", 
                        description="query string in english", 
                        required=True
                    )
                ]
            ) for prompt in prompts]
        except (KeyError, TypeError) as e:
            print(f"Error processing prompts: {str(e)}", file=sys.stderr)
            # Fallback to default
            return [
                Prompt(
                    name="ask_nlw",
                    description="Connects with the NLWeb server to answer questions",
                    arguments=[
                        PromptArgument(
                            name="query", 
                            description="query string in english", 
                            required=True
                        )
                    ]
                )
            ]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict) -> list[TextContent]:
        """Forward tool calls to NLWeb"""
        result = await forward_to_nlweb("tools/call", {"name": name, "arguments": arguments}, server_url, endpoint)
        
        if "error" in result:
            return [TextContent(type="text", text=f"Error: {result['error']}")]
        
        # Extract response from the result
        try:
            response_data = result.get("response", {})
            
            # Truncate the JSON response if it's too long
            if isinstance(response_data, (dict, list)):
                response_data = truncate_preserving_early_entries(response_data, MAX_TOOL_OUTPUT_LENGTH)

            response_text = json.dumps(response_data, indent=2)
            
            return [TextContent(type="text", text=response_text)]
        except Exception as e:
            print(f"Error processing tool response: {str(e)}", file=sys.stderr)
            return [TextContent(type="text", text=f"Error processing response: {str(e)}")]

    @server.get_prompt()
    async def get_prompt(name: str, arguments: dict | None) -> GetPromptResult:
        """Forward get_prompt to NLWeb"""
        if not arguments:
            arguments = {}
            
        # Add the prompt name as prompt_id if not present
        if "prompt_id" not in arguments:
            arguments["prompt_id"] = name
        
        result = await forward_to_nlweb("tools/get_prompt", {"name": name, "arguments": arguments}, server_url, endpoint)
        
        if "error" in result:
            return GetPromptResult(
                description=f"Failed to get prompt {arguments.get('prompt_id', name)}",
                messages=[
                    PromptMessage(
                        role="user",
                        content=TextContent(type="text", text=f"Error: {result['error']}")
                    )
                ]
            )
        
        # Extract prompt from the response
        try:
            prompt_data = result.get("response", {})
            prompt_text = prompt_data.get("prompt_text", f"Prompt for {name}")
            
            return GetPromptResult(
                description=f"Prompt: {prompt_data.get('name', name)}",
                messages=[
                    PromptMessage(
                        role="user", 
                        content=TextContent(type="text", text=prompt_text)
                    )
                ]
            )
        except Exception as e:
            print(f"Error processing prompt: {str(e)}", file=sys.stderr)
            return GetPromptResult(
                description=f"Error getting prompt {name}",
                messages=[
                    PromptMessage(
                        role="user",
                        content=TextContent(type="text", text=f"Error: {str(e)}")
                    )
                ]
            )

    # Run the server
    options = server.create_initialization_options()
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, options, raise_exceptions=True)

# Main entry point when script is executed directly
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Claude interface for NLWeb")
    parser.add_argument("--server", default=DEFAULT_SERVER_URL, help="NLWeb server URL")
    parser.add_argument("--endpoint", default=DEFAULT_ENDPOINT, help="NLWeb server endpoint")
    
    args = parser.parse_args()
    
    # Run the server with the specified parameters
    asyncio.run(serve(args.server, args.endpoint))