resource "aws_ecr_repository" "this" {
  name                 = var.repository_name
  image_tag_mutability = var.image_tag_mutability
  force_delete         = var.force_delete

  image_scanning_configuration {
    scan_on_push = var.scan_on_push
  }

  encryption_configuration {
    encryption_type = var.encryption_type
    kms_key         = var.encryption_type == "KMS" ? var.kms_key_arn : null
  }

  tags = var.tags
}

locals {
  lifecycle_rules = concat(
    var.expire_untagged_after_days == null ? [] : [
      {
        rulePriority = 1
        description  = "Expire untagged images after ${var.expire_untagged_after_days} days"
        selection = {
          tagStatus   = "untagged"
          countType   = "sinceImagePushed"
          countUnit   = "days"
          countNumber = var.expire_untagged_after_days
        }
        action = {
          type = "expire"
        }
      }
    ],
    var.keep_tagged_image_count == null ? [] : [
      {
        rulePriority = 2
        description  = "Keep the most recent ${var.keep_tagged_image_count} versioned images"
        selection = {
          tagStatus     = "tagged"
          tagPrefixList = var.tag_prefix_list
          countType     = "imageCountMoreThan"
          countNumber   = var.keep_tagged_image_count
        }
        action = {
          type = "expire"
        }
      }
    ]
  )
}

# ECR permits one lifecycle policy per repository, so untagged and versioned
# cleanup rules must be composed into this single policy document.
resource "aws_ecr_lifecycle_policy" "this" {
  count      = length(local.lifecycle_rules) > 0 ? 1 : 0
  repository = aws_ecr_repository.this.name
  policy = jsonencode({
    rules = local.lifecycle_rules
  })
}
