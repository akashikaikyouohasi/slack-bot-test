import json
import logging
import os
import re
import boto3
from slack_sdk import WebClient

logger = logging.getLogger()
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))

bedrock = boto3.client("bedrock-runtime")
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
        if not text:
            continue

        if msg.get("bot_id") or msg.get("user") == bot_user_id:
            messages.append({"role": "assistant", "content": text})
        else:
            messages.append({"role": "user", "content": text})

    # assistant が連続する場合やuserで始まらない場合を補正
    if not messages or messages[0]["role"] != "user":
        messages.insert(0, {"role": "user", "content": "Hello!"})

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

    # Bot自身のuser_idを取得（キャッシュはWebClientが内部で行う）
    bot_user_id = slack.auth_test()["user_id"]

    # スレッド履歴からmessages配列を構築
    messages = build_messages_from_thread(
        slack, channel, thread_ts, thinking_ts, bot_user_id
    )
    logger.info("Messages for Bedrock: %d turns, content: %s", len(messages), json.dumps(messages, ensure_ascii=False))

    try:
        model_id = os.environ.get(
            "BEDROCK_MODEL_ID", "global.anthropic.claude-haiku-4-5-20251001-v1:0"
        )
        logger.info("Calling Bedrock model: %s", model_id)
        response = bedrock.invoke_model(
            modelId=model_id,
            contentType="application/json",
            accept="application/json",
            body=json.dumps(
                {
                    "anthropic_version": "bedrock-2023-05-31",
                    "max_tokens": 1024,
                    "messages": messages,
                }
            ),
        )
        result = json.loads(response["body"].read())
        answer = result["content"][0]["text"]
        logger.info("Bedrock response received: %d chars", len(answer))
    except Exception as e:
        logger.error("Bedrock invocation failed: %s", e, exc_info=True)
        answer = f"Error: {str(e)}"

    # 「思考中...」を回答で更新
    slack.chat_update(channel=channel, ts=thinking_ts, text=answer)
    logger.info("Response updated: channel=%s, ts=%s", channel, thinking_ts)
