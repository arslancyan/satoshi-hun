"""Compatibility entrypoint for the Satoshi Hunt MCP worker server.

The runtime implementation lives at the repository root so the local
mcp documentation directory cannot shadow the official Python SDK.
"""
from satoshi_mcp_server import mcp

if __name__ == "__main__":
    mcp.run(transport="streamable-http")
