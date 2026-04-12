# --- Dispatcher Lambda ---

data "archive_file" "dispatcher" {
  type        = "zip"
  source_dir  = "${path.module}/../lambda/dispatcher"
  output_path = "${path.module}/../lambda/dispatcher.zip"
}

resource "aws_lambda_function" "dispatcher" {
  function_name    = "${var.project_name}-dispatcher"
  filename         = data.archive_file.dispatcher.output_path
  source_code_hash = data.archive_file.dispatcher.output_base64sha256
  handler          = "handler.lambda_handler"
  runtime          = "python3.12"
  timeout          = 10
  role             = aws_iam_role.dispatcher.arn

  environment {
    variables = {
      SLACK_SECRET_ARN        = aws_secretsmanager_secret.slack.arn
      PROCESSOR_FUNCTION_NAME = aws_lambda_function.processor.function_name
    }
  }
}

# IAM Role
resource "aws_iam_role" "dispatcher" {
  name = "${var.project_name}-dispatcher-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = {
        Service = "lambda.amazonaws.com"
      }
    }]
  })
}

resource "aws_iam_role_policy" "dispatcher" {
  name = "${var.project_name}-dispatcher-policy"
  role = aws_iam_role.dispatcher.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents",
        ]
        Resource = "arn:aws:logs:*:*:*"
      },
      {
        Effect   = "Allow"
        Action   = "lambda:InvokeFunction"
        Resource = aws_lambda_function.processor.arn
      },
      {
        Effect   = "Allow"
        Action   = "secretsmanager:GetSecretValue"
        Resource = aws_secretsmanager_secret.slack.arn
      },
    ]
  })
}

# Allow API Gateway to invoke
resource "aws_lambda_permission" "api_gateway" {
  statement_id  = "AllowAPIGateway"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.dispatcher.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_api_gateway_rest_api.main.execution_arn}/*/*"
}
