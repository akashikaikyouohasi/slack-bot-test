# Slack Bot with Bedrock

Slackでボットをメンションすると、Amazon Bedrock (LLM) が応答するチャットボット。

## アーキテクチャ

```
User @mentions bot
  → Slack Events API
  → API Gateway (REST)
  → Dispatcher Lambda  ... 即座に200返却 (3秒制約対応)
  → Processor Lambda   ... Bedrock呼び出し → Slackに返信
```

Slackは3秒以内のHTTPレスポンスを要求するため、受信用 (Dispatcher) と処理用 (Processor) の2つのLambdaに分離し、非同期で処理する。

## 前提条件

- AWS CLI (認証済み)
- Terraform >= 1.0
- Python 3.12
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
3. 数秒後にLLMの応答が投稿される

## Terraform変数

| 変数 | デフォルト | 説明 |
|---|---|---|
| `aws_region` | `us-east-1` | AWSリージョン |
| `bedrock_model_id` | `anthropic.claude-3-haiku-20240307-v1:0` | Bedrockのモデル ID |
| `project_name` | `slack-bot` | リソース名のプレフィックス |

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
