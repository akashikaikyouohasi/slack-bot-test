output "api_gateway_url" {
  description = "Slack Event Subscriptions Request URL"
  value       = "${aws_api_gateway_stage.main.invoke_url}/slack/events"
}
