import json
import logging
import os
import re
from datetime import datetime, timezone
import boto3
from slack_sdk import WebClient
from strands import Agent
from strands.models.bedrock import BedrockModel
from strands.models.model import CacheConfig
from strands_tools import use_aws, file_read
from system_prompt import SYSTEM_PROMPT
from cloudwatch_tools import list_log_groups, search_logs
from mcp_servers import create_mcp_clients

logger = logging.getLogger()
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))

# Bedrock料金テーブル (USD per 1M tokens)
# https://aws.amazon.com/jp/bedrock/pricing/
# cache_writeは5分TTLの料金を使用
MODEL_PRICING = {
    "claude-opus-4-7": {"input": 5.00, "output": 25.00, "cache_read": 0.50, "cache_write": 6.25},
    "claude-sonnet-4-6": {"input": 3.00, "output": 15.00, "cache_read": 0.30, "cache_write": 3.75},
    "claude-sonnet-4-5": {"input": 3.00, "output": 15.00, "cache_read": 0.30, "cache_write": 3.75},
    "claude-haiku-4-5": {"input": 1.00, "output": 5.00, "cache_read": 0.10, "cache_write": 1.25},
}


def calculate_cost(model_id, input_tokens, output_tokens, cache_read_tokens=0, cache_write_tokens=0):
    """モデルIDからトークン料金を計算する (USD)"""
    for key, pricing in MODEL_PRICING.items():
        if key in model_id:
            input_cost = input_tokens * pricing["input"] / 1_000_000
            output_cost = output_tokens * pricing["output"] / 1_000_000
            cache_read_cost = cache_read_tokens * pricing["cache_read"] / 1_000_000
            cache_write_cost = cache_write_tokens * pricing["cache_write"] / 1_000_000
            return input_cost + output_cost + cache_read_cost + cache_write_cost
    return None

secrets_client = boto3.client("secretsmanager")

# Cache secret and client across invocations
_slack_client = None


def get_slack_client():
    global _slack_client
    if _slack_client is None:
        resp = secrets_client.get_secret_value(
            SecretId=os.environ["SLACK_SECRET_ARN"]
        )
        secrets = json.loads(resp["SecretString"])
        _slack_client = WebClient(token=secrets["slack_bot_token"])
        logger.info("Slack client initialized from Secrets Manager")
    return _slack_client


def build_messages_from_thread(slack, channel, thread_ts, thinking_ts, bot_user_id):
    """スレッドのメッセージ履歴からBedrock用のmessages配列を構築する"""
    result = slack.conversations_replies(channel=channel, ts=thread_ts)
    thread_messages = result.get("messages", [])

    messages = []
    for msg in thread_messages:
        # 「思考中...」メッセージは除外
        if msg.get("ts") == thinking_ts:
            continue

        text = msg.get("text", "")
        # メンション部分を除去
        text = re.sub(r"<@[A-Z0-9]+>\s*", "", text).strip()
        # ボットが付与したコスト行を除去
        text = re.sub(r"\n*_消費コスト: .+_$", "", text).strip()
        if not text:
            continue

        if msg.get("bot_id") or msg.get("user") == bot_user_id:
            messages.append({"role": "assistant", "content": [{"text": text}]})
        else:
            messages.append({"role": "user", "content": [{"text": text}]})

    # userで始まらない場合を補正
    if not messages or messages[0]["role"] != "user":
        messages.insert(0, {"role": "user", "content": [{"text": "Hello!"}]})

    return messages


def lambda_handler(event, context):
    logger.info("Received event: %s", json.dumps(event, ensure_ascii=False))

    channel = event["channel"]
    thread_ts = event.get("thread_ts", event.get("ts"))
    user_text = event.get("text", "")

    # Strip bot mention: "<@U12345> hello" -> "hello"
    user_text = re.sub(r"<@[A-Z0-9]+>\s*", "", user_text).strip()

    if not user_text:
        user_text = "Hello!"

    logger.info("Processing message: channel=%s, text=%s", channel, user_text)

    slack = get_slack_client()

    # 「思考中...」を先に投稿
    thinking_msg = slack.chat_postMessage(
        channel=channel, text="思考中...", thread_ts=thread_ts
    )
    thinking_ts = thinking_msg["ts"]
    logger.info("Thinking message posted: ts=%s", thinking_ts)

    # Bot自身のuser_idを取得
    bot_user_id = slack.auth_test()["user_id"]

    # スレッド履歴からmessages配列を構築
    messages = build_messages_from_thread(
        slack, channel, thread_ts, thinking_ts, bot_user_id
    )
    logger.info("Messages for agent: %d turns, content: %s", len(messages), json.dumps(messages, ensure_ascii=False))

    try:
        model_id = os.environ.get(
            "BEDROCK_MODEL_ID", "global.anthropic.claude-haiku-4-5-20251001-v1:0"
        )
        logger.info("Calling Strands Agent with model: %s", model_id)

        model = BedrockModel(model_id=model_id, cache_config=CacheConfig(strategy="auto"))

        mcp_clients = create_mcp_clients()

        try:
            today = datetime.now(timezone.utc).strftime("%Y年%m月%d日")
            system_prompt = f"今日の日付は{today}です。\n\n{SYSTEM_PROMPT}"

            agent = Agent(
                model=model,
                system_prompt=system_prompt,
                messages=messages,
                tools=[list_log_groups, search_logs, use_aws, file_read] + mcp_clients,
            )

            # エージェントループ実行
            result = agent(user_text)
            answer = str(result)

            # 料金を計算
            usage = agent.event_loop_metrics.accumulated_usage
            input_tokens = usage.get("inputTokens", 0)
            output_tokens = usage.get("outputTokens", 0)
            cache_read_tokens = usage.get("cacheReadInputTokens", 0)
            cache_write_tokens = usage.get("cacheWriteInputTokens", 0)
            cost = calculate_cost(model_id, input_tokens, output_tokens, cache_read_tokens, cache_write_tokens)
            if cost is not None:
                answer += (
                    f"\n\n_消費コスト: ${cost:.4f}"
                    f" | in: {input_tokens:,} out: {output_tokens:,}"
                    f" cache r/w: {cache_read_tokens:,}/{cache_write_tokens:,}_"
                )
        finally:
            for mcp in mcp_clients:
                try:
                    mcp.stop(None, None, None)
                except Exception:
                    pass
        logger.info("Agent response received: %d chars", len(answer))
    except Exception as e:
        logger.error("Agent invocation failed: %s", e, exc_info=True)
        answer = f"Error: {str(e)}"

    # Slackのメッセージ上限（約40,000文字）を超える場合は切り詰め
    SLACK_MAX_LENGTH = 39000
    if len(answer) > SLACK_MAX_LENGTH:
        answer = answer[:SLACK_MAX_LENGTH] + "\n\n_（回答が長すぎるため省略されました）_"

    # 「思考中...」を回答で更新
    slack.chat_update(channel=channel, ts=thinking_ts, text=answer)
    logger.info("Response updated: channel=%s, ts=%s", channel, thinking_ts)
