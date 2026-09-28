resource "aws_secretsmanager_secret" "this" {
  name                    = var.name
  description             = var.description
  recovery_window_in_days = var.recovery_window_in_days
  tags                    = var.tags
}

# Uses the AWS provider's write-only field so secret material is not persisted
# in Terraform state. Leave secret_value null to create only the container.
resource "aws_secretsmanager_secret_version" "this" {
  count = var.create_secret_version ? 1 : 0

  secret_id                = aws_secretsmanager_secret.this.id
  secret_string_wo         = var.secret_value
  secret_string_wo_version = var.secret_value_version

  lifecycle {
    precondition {
      condition     = var.secret_value != null && var.secret_value_version > 0
      error_message = "secret_value and a positive secret_value_version are required when create_secret_version is true."
    }
  }
}
