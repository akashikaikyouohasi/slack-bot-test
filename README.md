# Slack Bot with Strands Agents

Slackでボットをメンションすると、Strands Agentsによるエージェントループで応答するチャットボット。AWSリソースの調査やCloudWatch Logsの検索を自律的に行える。

## アーキテクチャ

```
User @mentions bot
  → Slack Events API
  → API Gateway (REST)
  → Dispatcher Lambda  ... 即座に200返却 (3秒制約対応)
  → Processor Lambda   ... Strands Agent (エージェントループ) → Slackに返信
```

Slackは3秒以内のHTTPレスポンスを要求するため、受信用 (Dispatcher) と処理用 (Processor) の2つのLambdaに分離し、非同期で処理する。

### エージェント構成

Processor Lambda内でStrands Agentsのエージェントループを実行する。エージェントはユーザーの質問に応じてツールを自律的に選択・実行し、結果を踏まえて回答する。

**利用可能なツール:**

| ツール | 説明 |
|---|---|
| `use_aws` | boto3経由で任意のAWS APIを呼び出す (ReadOnly) |
| `list_log_groups` | CloudWatch Logsのロググループ一覧を取得 |
| `search_logs` | CloudWatch Logs Insightsでログを検索 |

**MCP Server連携:**

| サーバー | 説明 |
|---|---|
| [AWS Knowledge MCP Server](https://knowledge-mcp.global.api.aws) | AWSドキュメント・ベストプラクティスを参照 |

### スレッド対応

スレッド内の会話履歴をエージェントのコンテキストとして渡すため、文脈を踏まえた応答が可能。

## 前提条件

- AWS CLI (認証済み)
- Terraform >= 1.0
- Python 3.12
- [uv](https://docs.astral.sh/uv/) (パッケージング用)
- Bedrockのモデルアクセスが有効化済み (AWS Console > Bedrock > Model access)

## セットアップ

### 1. Slackアプリの作成

1. https://api.slack.com/apps にアクセスし「Create New App」→「From scratch」
2. アプリ名とワークスペースを選択して作成
3. 以下の情報を控える:
   - **Signing Secret**: 「Basic Information」→「App Credentials」→「Signing Secret」
   - **Bot Token**: 「OAuth & Permissions」でBot Token Scopesを追加後、ワークスペースにインストールして取得

### 2. Slackアプリの権限設定

「OAuth & Permissions」→「Bot Token Scopes」に以下を追加:

| Scope | 用途 |
|---|---|
| `app_mentions:read` | ボットへのメンション検知 |
| `chat:write` | チャンネルへのメッセージ投稿・更新 |
| `channels:history` | パブリックチャンネルのスレッド履歴取得 |
| `groups:history` | プライベートチャンネルのスレッド履歴取得 |

スコープ追加後、「Install to Workspace」でアプリをインストールし、`xoxb-` で始まるBot User OAuth Tokenを取得する。

### 3. インフラのデプロイ

```bash
# Processor Lambdaのパッケージング
./scripts/package.sh

# Terraform変数の設定
vim terraform/terraform.tfvars

# デプロイ
cd terraform
terraform init
terraform plan
terraform apply
```

### 4. Secrets Managerにシークレットを登録

Terraform適用後、AWS CLIまたはコンソールでシークレットの値をJSON形式で設定する:

```bash
aws secretsmanager put-secret-value \
  --secret-id slack-bot/slack-secrets \
  --secret-string '{"slack_bot_token": "xoxb-your-bot-token", "slack_signing_secret": "your-signing-secret"}'
```

`slack-bot/` の部分は `project_name` 変数を変更した場合はそれに合わせる。

### 5. SlackアプリにEvent Subscriptions URLを設定

1. Terraformの出力からURLを取得:
   ```bash
   terraform output api_gateway_url
   ```
2. Slackアプリ設定画面 →「Event Subscriptions」→ Enable Events を ON
3. Request URL に上記URLを貼り付け (自動的にURL検証が行われる)
4. 「Subscribe to bot events」で `app_mention` を追加
5. 変更を保存

### 6. 動作確認

1. ボットをSlackチャンネルに招待: `/invite @ボット名`
2. チャンネルで `@ボット名 こんにちは` とメンション
3. 数秒後にエージェントの応答が投稿される

質問例:
- `@ボット名 S3バケットの一覧を教えて`
- `@ボット名 最近のLambdaのエラーログを調べて`

## Terraform変数

| 変数 | デフォルト | 説明 |
|---|---|---|
| `aws_region` | `us-east-1` | AWSリージョン |
| `bedrock_model_id` | `global.anthropic.claude-haiku-4-5-20251001-v1:0` | Bedrockのモデル ID |
| `project_name` | `slack-bot` | リソース名のプレフィックス |

## IAM権限

Processor LambdaのIAMロールには以下の権限が付与される:

| ポリシー | 用途 |
|---|---|
| `ReadOnlyAccess` (AWSマネージド) | `use_aws` ツールによるAWSリソース参照 |
| カスタムポリシー | CloudWatch Logs書き込み、Bedrock呼び出し、Secrets Manager読み取り |

`use_aws` ツールはReadOnlyAccessの範囲内で動作するため、変更操作はIAMレベルで拒否される。

## Secrets Manager

シークレット `{project_name}/slack-secrets` に以下のJSON形式で格納:

```json
{
  "slack_bot_token": "xoxb-...",
  "slack_signing_secret": "..."
}
```

## トラブルシューティング

- **Slackで応答がない**: CloudWatch Logsで両Lambdaのログを確認
- **URL検証が失敗する**: API GatewayのURLが正しいか、Dispatcher Lambdaがデプロイ済みか確認
- **Bedrockエラー**: 対象リージョンでモデルアクセスが有効化されているか確認 (AWS Console > Bedrock > Model access)
- **use_awsでアクセス拒否**: Processor LambdaのIAMロールに`ReadOnlyAccess`がアタッチされているか確認
