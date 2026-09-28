variable "repository_name" {
  description = "Name of the ECR repository."
  type        = string
}

variable "image_tag_mutability" {
  description = "Whether image tags may be overwritten. Production repositories should be immutable."
  type        = string
  default     = "IMMUTABLE"

  validation {
    condition     = contains(["IMMUTABLE", "MUTABLE"], var.image_tag_mutability)
    error_message = "image_tag_mutability must be IMMUTABLE or MUTABLE."
  }
}

variable "scan_on_push" {
  description = "Enable basic vulnerability scanning when an image is pushed."
  type        = bool
  default     = true
}

variable "encryption_type" {
  description = "ECR at-rest encryption type. Set KMS and provide kms_key_arn to use a customer-managed key."
  type        = string
  default     = "AES256"

  validation {
    condition     = contains(["AES256", "KMS"], var.encryption_type)
    error_message = "encryption_type must be AES256 or KMS."
  }
}

variable "kms_key_arn" {
  description = "Customer-managed KMS key ARN used when encryption_type is KMS."
  type        = string
  default     = null
  nullable    = true

  validation {
    condition     = var.encryption_type != "KMS" || var.kms_key_arn != null
    error_message = "kms_key_arn is required when encryption_type is KMS."
  }
}

variable "expire_untagged_after_days" {
  description = "Expire untagged images after this many days. Set to null to disable the rule."
  type        = number
  default     = 14
  nullable    = true
}

variable "keep_tagged_image_count" {
  description = "Number of version-tagged images to retain. Set to null to disable the rule."
  type        = number
  default     = 30
  nullable    = true
}

variable "tag_prefix_list" {
  description = "Image-tag prefixes covered by the tagged-image retention rule."
  type        = list(string)
  default     = ["v"]

  validation {
    condition     = var.keep_tagged_image_count == null || length(var.tag_prefix_list) > 0
    error_message = "tag_prefix_list cannot be empty while keep_tagged_image_count is set."
  }
}

variable "force_delete" {
  description = "Allow Terraform to delete the repository and its images. Keep false outside disposable environments."
  type        = bool
  default     = false
}

variable "tags" {
  description = "Tags applied to the ECR repository."
  type        = map(string)
  default     = {}
}
