# CLAUDE.md

## プロジェクト概要

Strands Agentsを使ったSlack botで、AWSリソースの調査・回答を自律的に行う。

## アーキテクチャ

- **Dispatcher Lambda** (`lambda/dispatcher/handler.py`) — Slack Events APIからの受信、署名検証、Processor非同期呼び出し
- **Processor Lambda** (`lambda/processor/handler.py`) — Strands Agentによるエージェントループ実行、Slackへの回答投稿
- **Terraform** (`terraform/`) — インフラ定義

## 主要ファイル

| ファイル | 役割 |
|---|---|
| `lambda/processor/handler.py` | エージェント実行のメインロジック |
| `lambda/processor/system_prompt.py` | エージェントのシステムプロンプト |
| `lambda/processor/cloudwatch_tools.py` | CloudWatch Logs用カスタムツール |
| `lambda/processor/mcp_servers.py` | MCP Serverクライアント設定 |
| `terraform/lambda_processor.tf` | Processor LambdaのIAMポリシー含むインフラ定義 |

## エージェントのツール構成

- `use_aws` (`strands_tools`) — boto3経由で任意のAWS API呼び出し（ReadOnly）
- `list_log_groups`, `search_logs` (`cloudwatch_tools.py`) — CloudWatch Logs専用ツール
- AWS Knowledge MCP Server — AWSドキュメント参照

## セキュリティ上の制約

- IAMは `ReadOnlyAccess` + 機密データアクセスのDenyポリシー
- Denyされている操作: `s3:GetObject`, `ssm:GetParameter*`, `lambda:GetFunction`, `dynamodb:GetItem/Query/Scan/BatchGetItem`, `sqs:ReceiveMessage`
- `kms:Decrypt` はDenyしてはいけない（Lambda環境変数の復号に必要）
- `secretsmanager:GetSecretValue` はカスタムポリシーでSlack用ARNのみAllowしており、`ReadOnlyAccess` には含まれないため他のシークレットは読めない

## デプロイ

```bash
./scripts/package.sh   # パッケージング（uv使用）
cd terraform && terraform apply
```

## 開発時の注意

- システムプロンプト (`system_prompt.py`) を変更した場合、パッケージングとデプロイが必要
- Processor Lambdaのタイムアウトは120秒、メモリは256MB
- Slackの3秒制約のためDispatcher/Processorの2Lambda構成にしている
- `callback_handler` は未設定（Lambda環境ではstdout出力不要）
