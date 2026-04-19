from strands.tools.mcp import MCPClient
from mcp.client.streamable_http import streamablehttp_client


def create_mcp_clients():
    """MCPクライアントを生成する。呼び出しごとに新しいインスタンスを返す。"""
    return [
        # AWS Knowledge MCP Server
        # https://knowledge-mcp.global.api.aws
        MCPClient(
            lambda: streamablehttp_client(url="https://knowledge-mcp.global.api.aws")
        ),
    ]
