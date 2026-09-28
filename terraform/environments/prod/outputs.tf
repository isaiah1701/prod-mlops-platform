output "cluster_name" {
  description = "EKS cluster name."
  value       = module.eks.cluster_name
}

output "cluster_endpoint" {
  description = "EKS API endpoint."
  value       = module.eks.cluster_endpoint
}

output "ecr_repository_urls" {
  description = "Serving and training ECR repository URLs."
  value       = { for name, repository in module.ecr : name => repository.repository_url }
}

output "serving_certificate_arn" {
  description = "Validated ACM certificate for 5hort.site and its subdomains."
  value       = module.route53.certificate_arn
}

output "route53_hosted_zone_id" {
  description = "Route 53 zone that will hold serving DNS aliases."
  value       = module.route53.hosted_zone_id
}

output "node_pool_scheduling" {
  description = "Node selectors and tolerations required by serving and training workloads."
  value       = module.eks.node_pool_scheduling
}

output "inference_runtime_secret_name" {
  description = "Secrets Manager name configured in the production Helm values."
  value       = module.inference_runtime_secret.name
}

output "external_secrets_role_arn" {
  description = "Least-privilege EKS Pod Identity role used by ESO."
  value       = aws_iam_role.external_secrets.arn
}

output "inference_artifact_role_arn" {
  description = "Optional read-only MLflow S3 artifact role."
  value       = try(aws_iam_role.inference[0].arn, null)
}
