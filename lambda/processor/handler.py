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


def lambda_handler(event, context):
    logger.info("Received event: %s", json.dumps(event, ensure_ascii=False))

    channel = event["channel"]
    user_text = event.get("text", "")

    # Strip bot mention: "<@U12345> hello" -> "hello"
    user_text = re.sub(r"<@[A-Z0-9]+>\s*", "", user_text).strip()

    if not user_text:
        user_text = "Hello!"

    logger.info("Processing message: channel=%s, text=%s", channel, user_text)

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
                    "messages": [{"role": "user", "content": user_text}],
                }
            ),
        )
        result = json.loads(response["body"].read())
        answer = result["content"][0]["text"]
        logger.info("Bedrock response received: %d chars", len(answer))
    except Exception as e:
        logger.error("Bedrock invocation failed: %s", e, exc_info=True)
        answer = f"Error: {str(e)}"

    slack = get_slack_client()
    slack.chat_postMessage(channel=channel, text=answer)
    logger.info("Response posted to channel=%s", channel)
