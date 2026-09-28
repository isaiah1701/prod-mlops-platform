output "vpc_id" {
  description = "ID of the VPC."
  value       = aws_vpc.this.id
}

output "private_subnet_ids" {
  description = "Private subnet IDs for EKS control plane and nodes."
  value       = values(aws_subnet.private)[*].id
}

output "public_subnet_ids" {
  description = "Public subnet IDs for internet-facing load balancers."
  value       = values(aws_subnet.public)[*].id
}

output "load_balancer_security_group_id" {
  description = "Security group used by public application load balancers."
  value       = aws_security_group.load_balancer.id
}

output "interface_endpoint_security_group_id" {
  description = "Security group attached to interface endpoints, or null when endpoints are disabled."
  value       = try(aws_security_group.interface_endpoints[0].id, null)
}
