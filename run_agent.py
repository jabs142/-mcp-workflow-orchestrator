#!/usr/bin/env python3
"""
Workflow Agent - Orchestrates request processing using MCP tools.

The agent connects to the MCP server and uses Claude to:
1. Validate presets (validate_preset)
2. Plan workflow steps (plan_steps)
3. Assign artists (assign_artist)
4. Record decisions (record_decision)

Outputs decisions.json with rationale and tool call trace.
"""

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime
from pathlib import Path

from anthropic import Anthropic
from dotenv import load_dotenv
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.types import TextContent, Tool

# Load environment variables from .env file
load_dotenv()


# ============================================================================
# AGENT CONFIGURATION
# ============================================================================

# Claude model to use for reasoning
MODEL = "claude-3-5-sonnet-20241022"

# MCP server command
SERVER_COMMAND = "python3"
SERVER_ARGS = ["server.py"]


# ============================================================================
# AGENT CORE
# ============================================================================

async def process_request(
    request_id: str,
    session: ClientSession,
    anthropic_client: Anthropic
) -> dict:
    """
    Process a single request through the workflow.

    Args:
        request_id: The request ID to process
        session: Active MCP client session
        anthropic_client: Anthropic API client

    Returns:
        Dictionary containing decision, rationale, and trace
    """
    print(f"\n{'='*60}")
    print(f"Processing request: {request_id}")
    print(f"{'='*60}")

    # Track all tool calls for audit trail
    tool_trace = []

    # Get available tools from MCP server
    tools_response = await session.list_tools()
    available_tools = tools_response.tools

    # Convert MCP tools to Anthropic tool format
    anthropic_tools = [
        {
            "name": tool.name,
            "description": tool.description or "",
            "input_schema": tool.inputSchema
        }
        for tool in available_tools
    ]

    # Initial prompt for the agent
    initial_prompt = f"""You are a workflow orchestration agent. Process request "{request_id}" by following these steps in order:

1. First, read the resources to understand context:
   - resource://requests (to get request details)
   - resource://presets (to check preset configuration)
   - resource://artists (to see available artists)
   - resource://rules (to understand workflow rules)

2. Then call the tools in this sequence:
   - validate_preset: Check if the account's preset is valid (has all 4 texture channels: r, g, b, a)
   - If validation FAILS: Stop here and return a customer-safe error message explaining what's missing
   - plan_steps: Determine workflow steps based on rules
   - assign_artist: Assign an artist based on skills and capacity
   - record_decision: Save the decision with all details

3. After completing all steps, provide a summary with:
   - The decision that was made
   - A natural-language rationale explaining why these choices were made
   - Reference to the tool calls that were executed

Be thorough in your rationale - explain WHY each decision was made based on the data you observed."""

    messages = [{"role": "user", "content": initial_prompt}]

    iteration = 0
    max_iterations = 20  # Safety limit to prevent infinite loops

    validation_failed = False
    validation_errors = []

    while iteration < max_iterations:
        iteration += 1
        print(f"\n--- Iteration {iteration} ---")

        # Call Claude with available tools
        response = anthropic_client.messages.create(
            model=MODEL,
            max_tokens=4096,
            tools=anthropic_tools,
            messages=messages
        )

        print(f"Stop reason: {response.stop_reason}")

        # Check if Claude wants to use tools
        if response.stop_reason == "tool_use":
            messages.append({"role": "assistant", "content": response.content})

            # Process each tool call
            tool_results = []

            for content_block in response.content:
                if content_block.type == "tool_use":
                    tool_name = content_block.name
                    tool_input = content_block.input
                    tool_use_id = content_block.id

                    print(f"Calling tool: {tool_name}")
                    print(f"Input: {json.dumps(tool_input, indent=2)}")

                    # Record tool call in trace
                    tool_trace.append({
                        "tool": tool_name,
                        "input": tool_input,
                        "timestamp": datetime.utcnow().isoformat()
                    })

                    # Execute the tool via MCP
                    try:
                        result = await session.call_tool(tool_name, arguments=tool_input)

                        # Extract text content from result
                        if result.content:
                            tool_output = ""
                            for content_item in result.content:
                                if isinstance(content_item, TextContent):
                                    tool_output += content_item.text

                            # Parse the JSON result
                            tool_result_data = json.loads(tool_output)

                            print(f"Result: {json.dumps(tool_result_data, indent=2)}")

                            # Add to trace
                            tool_trace[-1]["output"] = tool_result_data

                            # Check for validation failure
                            if tool_name == "validate_preset" and not tool_result_data.get("ok"):
                                validation_failed = True
                                validation_errors = tool_result_data.get("errors", [])

                            # Add tool result to messages
                            tool_results.append({
                                "type": "tool_result",
                                "tool_use_id": tool_use_id,
                                "content": tool_output
                            })
                        else:
                            # No content returned
                            tool_results.append({
                                "type": "tool_result",
                                "tool_use_id": tool_use_id,
                                "content": json.dumps({"error": "No result returned"})
                            })

                    except Exception as e:
                        print(f"Error calling tool: {e}")
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": tool_use_id,
                            "content": json.dumps({"error": str(e)}),
                            "is_error": True
                        })

            # Add all tool results to message history
            messages.append({"role": "user", "content": tool_results})

            if validation_failed:
                print("\n⚠️  Validation failed - asking agent to generate customer error message")
                messages.append({
                    "role": "user",
                    "content": f"Validation failed with errors: {validation_errors}. Stop the workflow here and generate a customer-safe error message explaining what's wrong and how to fix it. Do not proceed with plan_steps, assign_artist, or record_decision."
                })

        elif response.stop_reason == "end_turn":
            print("\n✅ Agent completed processing")

            final_text = ""
            for content_block in response.content:
                if hasattr(content_block, "text"):
                    final_text += content_block.text

            print(f"\nFinal response:\n{final_text}")

            return {
                "request_id": request_id,
                "validation_passed": not validation_failed,
                "rationale": final_text,
                "trace": tool_trace,
                "completed_at": datetime.utcnow().isoformat()
            }

        else:
            print(f"⚠️  Unexpected stop reason: {response.stop_reason}")
            break
        
    print(f"\n⚠️  Reached maximum iterations ({max_iterations})")
    return {
        "request_id": request_id,
        "validation_passed": False,
        "rationale": "Agent exceeded maximum iteration limit",
        "trace": tool_trace,
        "completed_at": datetime.utcnow().isoformat(),
        "error": "max_iterations_exceeded"
    }


async def run_agent(request_ids: list[str]):
    """
    Main agent entry point - processes multiple requests.

    Args:
        request_ids: List of request IDs to process
    """
    # Check for API key
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("❌ Error: ANTHROPIC_API_KEY not found in environment")
        print("Please create a .env file with your API key:")
        print("  ANTHROPIC_API_KEY=your-key-here")
        sys.exit(1)

    # Initialize Anthropic client
    anthropic_client = Anthropic(api_key=api_key)

    # Connect to MCP server
    server_params = StdioServerParameters(
        command=SERVER_COMMAND,
        args=SERVER_ARGS,
        env=None
    )

    print(f"🚀 Starting MCP server: {SERVER_COMMAND} {' '.join(SERVER_ARGS)}")
    print(f"📋 Processing {len(request_ids)} request(s)")

    decisions = []

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            # Initialize the session
            await session.initialize()

            print("✅ Connected to MCP server")

            # List available tools and resources
            tools = await session.list_tools()
            resources = await session.list_resources()

            print(f"\n📦 Available tools: {[tool.name for tool in tools.tools]}")
            print(f"📚 Available resources: {[resource.uri for resource in resources.resources]}")

            # Process each request
            for request_id in request_ids:
                try:
                    result = await process_request(request_id, session, anthropic_client)
                    decisions.append(result)
                except Exception as e:
                    print(f"\n❌ Error processing {request_id}: {e}")
                    decisions.append({
                        "request_id": request_id,
                        "error": str(e),
                        "completed_at": datetime.utcnow().isoformat()
                    })

    # Write decisions to file
    output_file = Path(__file__).parent / "decisions.json"
    with open(output_file, "w") as f:
        json.dump(decisions, f, indent=2)

    print(f"\n{'='*60}")
    print(f"✅ Completed processing {len(request_ids)} request(s)")
    print(f"📄 Decisions written to: {output_file}")
    print(f"{'='*60}")


# ============================================================================
# CLI
# ============================================================================

def main():
    """Command-line interface for the agent."""
    parser = argparse.ArgumentParser(
        description="Workflow orchestration agent using MCP"
    )

    parser.add_argument(
        "--request-ids",
        nargs="+",
        help="Request IDs to process (e.g., req-001 req-002)",
        default=["req-001", "req-002", "req-003"]
    )

    args = parser.parse_args()

    # Run the async agent
    asyncio.run(run_agent(args.request_ids))


if __name__ == "__main__":
    main()
