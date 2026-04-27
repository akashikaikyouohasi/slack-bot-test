import os
import sys

from strands.tools.mcp import MCPClient
from mcp.client.streamable_http import streamablehttp_client
from mcp.client.stdio import stdio_client
from mcp import StdioServerParameters


# stdio_client's get_default_environment() only inherits HOME, PATH, etc.
# AWS credentials and Lambda runtime vars must be passed explicitly.
_AWS_ENV_PREFIXES = ("AWS_", "LAMBDA_", "_HANDLER")


def _get_aws_env():
    """親プロセスからAWS関連の環境変数を収集する。"""
    env = {}
    for key, value in os.environ.items():
        if any(key.startswith(prefix) for prefix in _AWS_ENV_PREFIXES):
            env[key] = value
    return env


def create_mcp_clients():
    """MCPクライアントを生成する。呼び出しごとに新しいインスタンスを返す。"""
    billing_params = StdioServerParameters(
        command=sys.executable,
        args=["billing_mcp_bootstrap.py"],
        env={
            "FASTMCP_LOG_LEVEL": "ERROR",
            "FASTMCP_LOG_FILE": "/tmp/billing-mcp.log",
            **_get_aws_env(),
        },
    )

    return [
        # AWS Knowledge MCP Server (Streamable HTTP)
        # https://knowledge-mcp.global.api.aws
        MCPClient(
            lambda: streamablehttp_client(url="https://knowledge-mcp.global.api.aws")
        ),
        # AWS Billing and Cost Management MCP Server (stdio)
        # https://github.com/awslabs/mcp/tree/main/src/billing-cost-management-mcp-server
        MCPClient(
            lambda: stdio_client(billing_params)
        ),
    ]
