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
  timeout          = 120
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

resource "aws_iam_role_policy_attachment" "processor_readonly" {
  role       = aws_iam_role.processor.name
  policy_arn = "arn:aws:iam::aws:policy/ReadOnlyAccess"
}

resource "aws_iam_role_policy" "processor_deny_sensitive" {
  name = "${var.project_name}-processor-deny-sensitive"
  role = aws_iam_role.processor.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "DenySensitiveDataAccess"
        Effect = "Deny"
        Action = [
          "s3:GetObject",
          "ssm:GetParameter",
          "ssm:GetParameters",
          "ssm:GetParametersByPath",
          "lambda:GetFunction",
          "dynamodb:GetItem",
          "dynamodb:Query",
          "dynamodb:Scan",
          "dynamodb:BatchGetItem",
          "sqs:ReceiveMessage",
          "kms:Decrypt",
        ]
        Resource = "*"
      },
    ]
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
        Action = [
          "bedrock:InvokeModel",
          "bedrock:InvokeModelWithResponseStream",
        ]
        Resource = [
          "arn:aws:bedrock:*::foundation-model/*",
          "arn:aws:bedrock:*:*:inference-profile/*",
        ]
      },
      {
        Effect = "Allow"
        Action = [
          "logs:DescribeLogGroups",
          "logs:StartQuery",
          "logs:GetQueryResults",
        ]
        Resource = "*"
      },
      {
        Effect   = "Allow"
        Action   = "secretsmanager:GetSecretValue"
        Resource = aws_secretsmanager_secret.slack.arn
      },
    ]
  })
}
