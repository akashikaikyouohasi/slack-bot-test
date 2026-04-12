import json
import hashlib
import hmac
import logging
import time
import os
import boto3

logger = logging.getLogger()
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))

lambda_client = boto3.client("lambda")
secrets_client = boto3.client("secretsmanager")

# Cache secrets across invocations
_secrets = None


def get_secrets():
    global _secrets
    if _secrets is None:
        resp = secrets_client.get_secret_value(
            SecretId=os.environ["SLACK_SECRET_ARN"]
        )
        _secrets = json.loads(resp["SecretString"])
        logger.info("Secrets loaded from Secrets Manager")
    return _secrets


def verify_slack_signature(event):
    signing_secret = get_secrets()["slack_signing_secret"]
    headers = event.get("headers", {})
    # API Gateway may lowercase headers
    normalized = {k.lower(): v for k, v in headers.items()}
    timestamp = normalized.get("x-slack-request-timestamp", "")
    signature = normalized.get("x-slack-signature", "")

    if not timestamp or not signature:
        logger.warning("Missing timestamp or signature header")
        return False
    if abs(time.time() - int(timestamp)) > 60 * 5:
        logger.warning("Request timestamp too old: %s", timestamp)
        return False

    sig_basestring = f"v0:{timestamp}:{event['body']}"
    my_sig = "v0=" + hmac.new(
        signing_secret.encode(), sig_basestring.encode(), hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(my_sig, signature)


def lambda_handler(event, context):
    logger.info("Received event: %s", json.dumps(event, ensure_ascii=False))

    body = json.loads(event.get("body", "{}"))

    # URL verification challenge
    if body.get("type") == "url_verification":
        logger.info("URL verification challenge received")
        return {
            "statusCode": 200,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({"challenge": body["challenge"]}),
        }

    # Verify signature
    if not verify_slack_signature(event):
        logger.warning("Invalid Slack signature")
        return {"statusCode": 401, "body": "Invalid signature"}

    # Skip retries from Slack
    headers = event.get("headers", {})
    normalized = {k.lower(): v for k, v in headers.items()}
    if normalized.get("x-slack-retry-num"):
        logger.info("Skipping Slack retry #%s", normalized["x-slack-retry-num"])
        return {"statusCode": 200, "body": "ok"}

    # Skip bot messages to avoid infinite loops
    slack_event = body.get("event", {})
    if slack_event.get("bot_id") or slack_event.get("subtype") == "bot_message":
        logger.info("Skipping bot message")
        return {"statusCode": 200, "body": "ok"}

    # Only handle app_mention events
    if slack_event.get("type") != "app_mention":
        logger.info("Skipping non app_mention event: %s", slack_event.get("type"))
        return {"statusCode": 200, "body": "ok"}

    # Async invoke processor
    logger.info(
        "Invoking processor: channel=%s, user=%s, text=%s",
        slack_event.get("channel"),
        slack_event.get("user"),
        slack_event.get("text"),
    )
    lambda_client.invoke(
        FunctionName=os.environ["PROCESSOR_FUNCTION_NAME"],
        InvocationType="Event",
        Payload=json.dumps(slack_event),
    )

    logger.info("Processor invoked successfully")
    return {"statusCode": 200, "body": "ok"}
