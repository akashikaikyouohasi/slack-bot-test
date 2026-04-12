# --- Processor Lambda ---

data "archive_file" "processor" {
  type        = "zip"
  source_dir  = "${path.module}/../lambda/processor/package"
  output_path = "${path.module}/../lambda/processor.zip"
}

resource "aws_lambda_function" "processor" {
  function_name    = "${var.project_name}-processor"
  filename         = data.archive_file.processor.output_path
  source_code_hash = data.archive_file.processor.output_base64sha256
  handler          = "handler.lambda_handler"
  runtime          = "python3.12"
  timeout          = 60
  memory_size      = 256
  role             = aws_iam_role.processor.arn

  environment {
    variables = {
      SLACK_SECRET_ARN = aws_secretsmanager_secret.slack.arn
      BEDROCK_MODEL_ID = var.bedrock_model_id
    }
  }
}

# IAM Role
resource "aws_iam_role" "processor" {
  name = "${var.project_name}-processor-role"

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

resource "aws_iam_role_policy" "processor" {
  name = "${var.project_name}-processor-policy"
  role = aws_iam_role.processor.id

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
        Effect = "Allow"
        Action = "bedrock:InvokeModel"
        Resource = [
          "arn:aws:bedrock:*::foundation-model/*",
          "arn:aws:bedrock:*:*:inference-profile/*",
        ]
      },
      {
        Effect   = "Allow"
        Action   = "secretsmanager:GetSecretValue"
        Resource = aws_secretsmanager_secret.slack.arn
      },
    ]
  })
}
