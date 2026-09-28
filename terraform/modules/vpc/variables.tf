variable "name" {
  description = "Environment-qualified name used for VPC resources."
  type        = string
}

variable "cluster_name" {
  description = "EKS cluster name used in Kubernetes subnet discovery tags."
  type        = string
}

variable "vpc_cidr" {
  description = "IPv4 CIDR block for the VPC."
  type        = string
}

variable "azs" {
  description = "Availability zones. Each zone receives one public and one private subnet."
  type        = list(string)

  validation {
    condition     = length(var.azs) >= 2 && length(distinct(var.azs)) == length(var.azs)
    error_message = "Provide at least two distinct availability zones."
  }
}

variable "public_subnet_cidrs" {
  description = "Public subnet CIDRs, one for each availability zone."
  type        = list(string)

  validation {
    condition     = length(var.public_subnet_cidrs) == length(var.azs)
    error_message = "public_subnet_cidrs must have one entry per availability zone."
  }
}

variable "private_subnet_cidrs" {
  description = "Private subnet CIDRs, one for each availability zone."
  type        = list(string)

  validation {
    condition     = length(var.private_subnet_cidrs) == length(var.azs)
    error_message = "private_subnet_cidrs must have one entry per availability zone."
  }
}

variable "single_nat_gateway" {
  description = "Use one NAT gateway for a lower-cost disposable environment. Keep false for HA staging and production."
  type        = bool
  default     = false
}

variable "enable_s3_gateway_endpoint" {
  description = "Add a no-cost S3 gateway endpoint to private route tables."
  type        = bool
  default     = true
}

variable "enable_interface_endpoints" {
  description = "Create private interface endpoints for ECR, STS, and CloudWatch Logs."
  type        = bool
  default     = true
}

variable "interface_endpoint_services" {
  description = "AWS interface endpoint service suffixes."
  type        = list(string)
  default     = ["ecr.api", "ecr.dkr", "logs", "sts"]
}

variable "tags" {
  description = "Tags applied to VPC resources."
  type        = map(string)
  default     = {}
}
