locals {
  name = "${var.project_name}-${var.environment}"

  common_tags = merge({
    Project     = var.project_name
    Environment = var.environment
    ManagedBy   = "Terraform"
    System      = "mlops"
  }, var.tags)

  ecr_repositories = toset(["serving", "training"])

  access_entries = merge(
    var.platform_admin_principal_arn == null ? {} : {
      platform_admin = {
        principal_arn = var.platform_admin_principal_arn
        policy_associations = {
          cluster_admin = {
            policy_arn = "arn:aws:eks::aws:cluster-access-policy/AmazonEKSClusterAdminPolicy"
            access_scope = {
              type = "cluster"
            }
          }
        }
      }
    },
    var.access_entries
  )
}

module "vpc" {
  source = "../../modules/vpc"

  name                        = local.name
  cluster_name                = local.name
  vpc_cidr                    = var.vpc_cidr
  azs                         = var.azs
  public_subnet_cidrs         = var.public_subnet_cidrs
  private_subnet_cidrs        = var.private_subnet_cidrs
  single_nat_gateway          = var.single_nat_gateway
  enable_s3_gateway_endpoint  = true
  enable_interface_endpoints  = true
  interface_endpoint_services = var.interface_endpoint_services
  tags                        = local.common_tags
}

module "ecr" {
  for_each = local.ecr_repositories
  source   = "../../modules/ecr"

  repository_name = "${local.name}-${each.key}"
  force_delete    = var.ecr_force_delete
  tags            = local.common_tags
}

module "eks" {
  source = "../../modules/eks"

  cluster_name                         = local.name
  kubernetes_version                   = var.kubernetes_version
  vpc_id                               = module.vpc.vpc_id
  private_subnet_ids                   = module.vpc.private_subnet_ids
  load_balancer_security_group_id      = module.vpc.load_balancer_security_group_id
  cluster_endpoint_public_access       = var.cluster_endpoint_public_access
  cluster_endpoint_public_access_cidrs = var.cluster_endpoint_public_access_cidrs
  system_node_pool                     = var.system_node_pool
  serving_node_pool                    = var.serving_node_pool
  training_node_pool                   = var.training_node_pool
  access_entries                       = local.access_entries
  bootstrap_cluster_creator_admin      = var.platform_admin_principal_arn == null
  kms_key_administrators               = var.platform_admin_principal_arn == null ? var.kms_key_administrators : distinct(concat([var.platform_admin_principal_arn], var.kms_key_administrators))
  tags                                 = local.common_tags
}
