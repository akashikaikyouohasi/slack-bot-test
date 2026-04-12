# --- Secrets Manager ---
# Values are managed manually via AWS Console or CLI
# Format: {"slack_bot_token": "xoxb-...", "slack_signing_secret": "..."}

resource "aws_secretsmanager_secret" "slack" {
  name = "${var.project_name}/slack-secrets"
}
