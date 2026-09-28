variable "bucket_name" {
  description = "Globally unique name for the private MLflow artifact bucket."
  type        = string

  validation {
    condition     = length(var.bucket_name) >= 3 && length(var.bucket_name) <= 63
    error_message = "bucket_name must be between 3 and 63 characters long."
  }
}

variable "noncurrent_version_expiration_days" {
  description = "Number of days to retain noncurrent object versions. Set to null to disable expiration."
  type        = number
  default     = 90
  nullable    = true

  validation {
    condition     = var.noncurrent_version_expiration_days == null || var.noncurrent_version_expiration_days >= 1
    error_message = "noncurrent_version_expiration_days must be at least 1 when set."
  }
}

variable "tags" {
  description = "Tags applied to the S3 bucket."
  type        = map(string)
  default     = {}
}
