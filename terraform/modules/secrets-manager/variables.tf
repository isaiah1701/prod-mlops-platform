variable "name" {
  description = "AWS Secrets Manager secret name."
  type        = string

  validation {
    condition     = length(trimspace(var.name)) > 0
    error_message = "name must not be empty."
  }
}

variable "description" {
  description = "Human-readable purpose of the secret."
  type        = string
}

variable "recovery_window_in_days" {
  description = "Recovery window used when deleting the secret."
  type        = number
  default     = 30
}

variable "secret_value" {
  description = "Optional write-only JSON payload; prefer populating it outside normal plans."
  type        = string
  default     = null
  nullable    = true
  sensitive   = true
}

variable "create_secret_version" {
  description = "Create a write-only secret version when a value is supplied securely."
  type        = bool
  default     = false
}

variable "secret_value_version" {
  description = "Positive rotation counter required when secret_value is supplied."
  type        = number
  default     = 1
}

variable "tags" {
  description = "Tags applied to the secret."
  type        = map(string)
  default     = {}
}
