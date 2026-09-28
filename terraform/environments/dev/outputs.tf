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

output "node_pool_scheduling" {
  description = "Node selectors and tolerations required by serving and training workloads."
  value       = module.eks.node_pool_scheduling
}

output "private_subnet_ids" {
  description = "Private subnets used by EKS."
  value       = module.vpc.private_subnet_ids
}
