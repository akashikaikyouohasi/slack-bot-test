import json
import hashlib
import hmac
import time
import os
import boto3

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
    return _secrets


def verify_slack_signature(event):
    signing_secret = get_secrets()["slack_signing_secret"]
    headers = event.get("headers", {})
    # API Gateway may lowercase headers
    normalized = {k.lower(): v for k, v in headers.items()}
    timestamp = normalized.get("x-slack-request-timestamp", "")
    signature = normalized.get("x-slack-signature", "")

    if not timestamp or not signature:
        return False
    if abs(time.time() - int(timestamp)) > 60 * 5:
        return False

    sig_basestring = f"v0:{timestamp}:{event['body']}"
    my_sig = "v0=" + hmac.new(
        signing_secret.encode(), sig_basestring.encode(), hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(my_sig, signature)


def lambda_handler(event, context):
    body = json.loads(event.get("body", "{}"))

    # URL verification challenge
    if body.get("type") == "url_verification":
        return {
            "statusCode": 200,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({"challenge": body["challenge"]}),
        }

    # Verify signature
    if not verify_slack_signature(event):
        return {"statusCode": 401, "body": "Invalid signature"}

    # Skip retries from Slack
    headers = event.get("headers", {})
    normalized = {k.lower(): v for k, v in headers.items()}
    if normalized.get("x-slack-retry-num"):
        return {"statusCode": 200, "body": "ok"}

    # Skip bot messages to avoid infinite loops
    slack_event = body.get("event", {})
    if slack_event.get("bot_id") or slack_event.get("subtype") == "bot_message":
        return {"statusCode": 200, "body": "ok"}

    # Only handle app_mention events
    if slack_event.get("type") != "app_mention":
        return {"statusCode": 200, "body": "ok"}

    # Async invoke processor
    lambda_client.invoke(
        FunctionName=os.environ["PROCESSOR_FUNCTION_NAME"],
        InvocationType="Event",
        Payload=json.dumps(slack_event),
    )

    return {"statusCode": 200, "body": "ok"}
