locals {
  services = [
    "bigquery.googleapis.com",
    "iam.googleapis.com",
    "iamcredentials.googleapis.com", # short-lived tokens for the service accounts
    "sts.googleapis.com",            # exchanges the GitHub OIDC token
    "cloudresourcemanager.googleapis.com",
  ]
}

resource "google_project_service" "this" {
  for_each = toset(local.services)

  service            = each.value
  disable_on_destroy = false
}
