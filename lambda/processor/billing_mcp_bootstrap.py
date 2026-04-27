"""Billing MCP Server の起動スクリプト。

Lambda環境（/var/task が読み取り専用）向けに、
ログとセッションDBの保存先を /tmp にリダイレクトしてからサーバーを起動する。
- ログ: FASTMCP_LOG_FILE 環境変数で /tmp に指定済み（mcp_servers.py で設定）
- セッションDB: グローバル変数 _SESSION_DB_PATH を直接セットしてディレクトリ作成をスキップ
"""

import os

# セッションDBの保存先を /tmp に設定（関数パッチではなくグローバル変数を直接セット）
os.makedirs("/tmp/sessions", exist_ok=True)
import awslabs.billing_cost_management_mcp_server.utilities.sql_utils as sql_utils
sql_utils._SESSION_DB_PATH = "/tmp/sessions/session.db"

# サーバー起動
from awslabs.billing_cost_management_mcp_server.server import main
main()
