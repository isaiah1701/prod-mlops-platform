variable "hosted_zone_id" {
  description = "Existing Route 53 public hosted-zone ID for the domain. The module never creates a duplicate hosted zone."
  type        = string
}

variable "create_certificate" {
  description = "Create and DNS-validate a regional ACM certificate."
  type        = bool
  default     = false
}

variable "certificate_domain_name" {
  description = "Primary DNS name for the ACM certificate. Required when create_certificate is true."
  type        = string
  default     = null
  nullable    = true

  validation {
    condition     = !var.create_certificate || var.certificate_domain_name != null
    error_message = "certificate_domain_name is required when create_certificate is true."
  }
}

variable "certificate_subject_alternative_names" {
  description = "Additional DNS names for the ACM certificate, such as *.example.com."
  type        = list(string)
  default     = []
}

variable "records" {
  description = "Standard Route 53 records keyed by a stable Terraform identifier."
  type = map(object({
    name            = string
    type            = string
    ttl             = number
    records         = list(string)
    allow_overwrite = optional(bool, false)
  }))
  default = {}
}

variable "alias_records" {
  description = "Alias records keyed by a stable Terraform identifier. Use this for an ALB once serving ingress exists."
  type = map(object({
    name                   = string
    type                   = string
    target_dns_name        = string
    target_zone_id         = string
    evaluate_target_health = optional(bool, true)
  }))
  default = {}
}

variable "tags" {
  description = "Tags applied to the ACM certificate. Route 53 records do not support tags."
  type        = map(string)
  default     = {}
}
