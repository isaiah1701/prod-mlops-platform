locals {
  environment = "prod"
  name        = "${var.project_name}-${local.environment}"

  common_tags = merge({
    Project     = var.project_name
    Environment = local.environment
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
  single_nat_gateway          = false
  interface_endpoint_services = var.interface_endpoint_services
  tags                        = local.common_tags
}

module "route53" {
  source = "../../modules/route-53"

  hosted_zone_id                        = var.route53_hosted_zone_id
  create_certificate                    = true
  certificate_domain_name               = var.domain_name
  certificate_subject_alternative_names = ["*.${var.domain_name}"]
  tags                                  = local.common_tags
}

module "ecr" {
  for_each = local.ecr_repositories
  source   = "../../modules/ecr"

  repository_name = "${local.name}-${each.key}"
  force_delete    = false
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

module "inference_runtime_secret" {
  source = "../../modules/secrets-manager"

  name                    = var.inference_runtime_secret_name
  description             = "Runtime configuration consumed by the Airbnb inference service"
  recovery_window_in_days = 30
  tags                    = local.common_tags
}

data "aws_iam_policy_document" "external_secrets_assume_role" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole", "sts:TagSession"]

    principals {
      type        = "Service"
      identifiers = ["pods.eks.amazonaws.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "aws:RequestTag/kubernetes-namespace"
      values   = [var.external_secrets_namespace]
    }

    condition {
      test     = "StringEquals"
      variable = "aws:RequestTag/kubernetes-service-account"
      values   = [var.external_secrets_service_account]
    }
  }
}

resource "aws_iam_role" "external_secrets" {
  name               = "${local.name}-external-secrets"
  description        = "Read only the inference runtime secret through EKS Pod Identity"
  assume_role_policy = data.aws_iam_policy_document.external_secrets_assume_role.json
  tags               = local.common_tags
}

data "aws_iam_policy_document" "external_secrets" {
  statement {
    sid       = "ReadInferenceRuntimeSecret"
    effect    = "Allow"
    actions   = ["secretsmanager:DescribeSecret", "secretsmanager:GetSecretValue"]
    resources = [module.inference_runtime_secret.arn]
  }
}

resource "aws_iam_role_policy" "external_secrets" {
  name   = "read-inference-runtime-secret"
  role   = aws_iam_role.external_secrets.id
  policy = data.aws_iam_policy_document.external_secrets.json
}

resource "aws_eks_pod_identity_association" "external_secrets" {
  cluster_name    = module.eks.cluster_name
  namespace       = var.external_secrets_namespace
  service_account = var.external_secrets_service_account
  role_arn        = aws_iam_role.external_secrets.arn
}

data "aws_iam_policy_document" "inference_assume_role" {
  count = var.mlflow_artifact_bucket_arn == null ? 0 : 1

  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole", "sts:TagSession"]

    principals {
      type        = "Service"
      identifiers = ["pods.eks.amazonaws.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "aws:RequestTag/kubernetes-namespace"
      values   = [var.inference_namespace]
    }

    condition {
      test     = "StringEquals"
      variable = "aws:RequestTag/kubernetes-service-account"
      values   = [var.inference_service_account]
    }
  }
}

resource "aws_iam_role" "inference" {
  count = var.mlflow_artifact_bucket_arn == null ? 0 : 1

  name               = "${local.name}-inference"
  description        = "Read only the configured MLflow artifact prefix"
  assume_role_policy = data.aws_iam_policy_document.inference_assume_role[0].json
  tags               = local.common_tags
}

data "aws_iam_policy_document" "inference_artifacts" {
  count = var.mlflow_artifact_bucket_arn == null ? 0 : 1

  statement {
    sid       = "ListArtifactPrefix"
    effect    = "Allow"
    actions   = ["s3:ListBucket"]
    resources = [var.mlflow_artifact_bucket_arn]
    condition {
      test     = "StringLike"
      variable = "s3:prefix"
      values   = ["${trimsuffix(var.mlflow_artifact_prefix, "/")}/*"]
    }
  }

  statement {
    sid       = "ReadArtifacts"
    effect    = "Allow"
    actions   = ["s3:GetObject"]
    resources = ["${var.mlflow_artifact_bucket_arn}/${trimsuffix(var.mlflow_artifact_prefix, "/")}/*"]
  }
}

resource "aws_iam_role_policy" "inference_artifacts" {
  count = var.mlflow_artifact_bucket_arn == null ? 0 : 1

  name   = "read-mlflow-artifacts"
  role   = aws_iam_role.inference[0].id
  policy = data.aws_iam_policy_document.inference_artifacts[0].json
}

resource "aws_eks_pod_identity_association" "inference" {
  count = var.mlflow_artifact_bucket_arn == null ? 0 : 1

  cluster_name    = module.eks.cluster_name
  namespace       = var.inference_namespace
  service_account = var.inference_service_account
  role_arn        = aws_iam_role.inference[0].arn
}
