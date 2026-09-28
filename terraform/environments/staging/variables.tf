variable "aws_region" {
  description = "AWS region for this environment."
  type        = string
  default     = "eu-west-2"
}

variable "project_name" {
  description = "Short project identifier used in resource names."
  type        = string
  default     = "prod-mlops"
}

variable "platform_admin_principal_arn" {
  description = "Optional stable IAM administrator for EKS and its KMS key. When omitted, the Terraform caller is the initial cluster administrator."
  type        = string
  default     = null
  nullable    = true
  sensitive   = true
}

variable "vpc_cidr" {
  description = "CIDR block for the environment VPC."
  type        = string
  default     = "10.21.0.0/20"
}

variable "azs" {
  description = "Availability zones for the VPC."
  type        = list(string)
  default     = ["eu-west-2a", "eu-west-2b"]
}

variable "public_subnet_cidrs" {
  description = "Public subnet CIDRs."
  type        = list(string)
  default     = ["10.21.0.0/24", "10.21.1.0/24"]
}

variable "private_subnet_cidrs" {
  description = "Private subnet CIDRs."
  type        = list(string)
  default     = ["10.21.8.0/24", "10.21.9.0/24"]
}

variable "interface_endpoint_services" {
  description = "Private AWS services exposed to workloads through interface endpoints."
  type        = list(string)
  default     = ["ecr.api", "ecr.dkr", "logs", "sts"]
}

variable "kubernetes_version" {
  description = "EKS Kubernetes minor version."
  type        = string
  default     = "1.35"
}

variable "cluster_endpoint_public_access" {
  description = "Expose a public EKS API endpoint."
  type        = bool
  default     = false
}

variable "cluster_endpoint_public_access_cidrs" {
  description = "CIDRs allowed to access the public EKS API endpoint when enabled."
  type        = list(string)
  default     = []
}

variable "system_node_pool" {
  description = "Capacity for cluster add-ons and system components."
  type = object({
    instance_types = list(string)
    min_size       = number
    max_size       = number
    desired_size   = number
    disk_size      = optional(number, 50)
    capacity_type  = optional(string, "ON_DEMAND")
  })
  default = {
    instance_types = ["m7i.large"]
    min_size       = 2
    max_size       = 3
    desired_size   = 2
  }
}

variable "serving_node_pool" {
  description = "Dedicated online-serving capacity."
  type = object({
    instance_types = list(string)
    min_size       = number
    max_size       = number
    desired_size   = number
    disk_size      = optional(number, 50)
    capacity_type  = optional(string, "ON_DEMAND")
  })
  default = {
    instance_types = ["m7i.large"]
    min_size       = 2
    max_size       = 4
    desired_size   = 2
  }
}

variable "training_node_pool" {
  description = "Dedicated offline CPU training capacity."
  type = object({
    instance_types = list(string)
    min_size       = number
    max_size       = number
    desired_size   = number
    disk_size      = optional(number, 100)
    capacity_type  = optional(string, "ON_DEMAND")
  })
  default = {
    instance_types = ["m7i.xlarge"]
    min_size       = 0
    max_size       = 3
    desired_size   = 0
    capacity_type  = "SPOT"
  }
}

variable "access_entries" {
  description = "Additional explicit EKS API access entries for CI or operators."
  type = map(object({
    principal_arn     = string
    kubernetes_groups = optional(list(string))
    type              = optional(string, "STANDARD")
    user_name         = optional(string)
    tags              = optional(map(string), {})
    policy_associations = optional(map(object({
      policy_arn = string
      access_scope = object({
        namespaces = optional(list(string))
        type       = string
      })
    })), {})
  }))
  default = {}
}

variable "kms_key_administrators" {
  description = "Additional IAM principal ARNs allowed to administer the EKS KMS key."
  type        = list(string)
  default     = []
}

variable "tags" {
  description = "Additional resource tags."
  type        = map(string)
  default = {
    Owner = "isaiah1701"
  }
}
