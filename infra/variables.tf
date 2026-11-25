variable "project_id" {
  description = "Google Cloud project that holds the warehouse."
  type        = string
}

variable "region" {
  description = "Location of every dataset. Sao Paulo keeps Brazilian customer data in Brazil (LGPD)."
  type        = string
  default     = "southamerica-east1"
}

variable "github_repository" {
  description = "owner/name of the only repository allowed to authenticate as the CI service accounts."
  type        = string
  default     = "DiegoTDDD/olist-cloud-warehouse"
}

variable "github_repository_owner_id" {
  description = "Numeric GitHub id of the repository owner. Checked as well as the name, so a renamed or re-created account with the same login cannot take over the trust."
  type        = string
  default     = "183739024"
}

variable "analyst_members" {
  description = "IAM members (user:, group:) allowed to read the marts. They see nothing in raw or staging."
  type        = list(string)
  default     = []
}

variable "table_expiration_days" {
  description = "Default table expiration. The BigQuery sandbox enforces 60 days; the weekly deploy refreshes it."
  type        = number
  default     = 60
}
