output "arn" {
  description = "ARN used for least-privilege read policies."
  value       = aws_secretsmanager_secret.this.arn
}

output "name" {
  description = "Name consumed by ExternalSecret remote references."
  value       = aws_secretsmanager_secret.this.name
}
