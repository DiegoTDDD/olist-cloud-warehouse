# GitHub Actions authenticates with its own short-lived OIDC token; there is no service account
# key anywhere. The provider only accepts tokens from one repository of one owner, and each
# service account trusts exactly one token subject. GitHub's subject names the owner and the
# repository with their immutable numeric ids, owner@id/repo@id (verified from a real token:
# see docs/adr/0002), so a re-created account or repository with the same name cannot match:
#   deployer   <- repo:<owner>@<id>/<repo>@<id>:ref:refs/heads/main  (pushes, schedules, manual runs on main)
#   pr-builder <- repo:<owner>@<id>/<repo>@<id>:pull_request         (pull requests from this repo)
resource "google_iam_workload_identity_pool" "github" {
  workload_identity_pool_id = "github"
  display_name              = "GitHub Actions"
  description               = "OIDC tokens from GitHub Actions in ${var.github_repository}"
  depends_on                = [google_project_service.this]
}

resource "google_iam_workload_identity_pool_provider" "github" {
  # checkov:skip=CKV_GCP_125:The rule's parser predates GitHub's immutable subject format (owner@id/repo@id) and cannot read it; the condition pins the exact subjects, repository and owner id.
  workload_identity_pool_id          = google_iam_workload_identity_pool.github.workload_identity_pool_id
  workload_identity_pool_provider_id = "github-oidc"
  display_name                       = "GitHub OIDC"

  attribute_mapping = {
    "google.subject"                = "assertion.sub"
    "attribute.repository"          = "assertion.repository"
    "attribute.repository_owner_id" = "assertion.repository_owner_id"
    "attribute.ref"                 = "assertion.ref"
    "attribute.event_name"          = "assertion.event_name"
  }

  # Defence in depth: the provider itself only accepts the two token subjects the service
  # accounts trust, from this repository of this owner. A token from any other repository,
  # branch, tag or environment is rejected before it can be exchanged.
  attribute_condition = "(assertion.sub == '${local.subject_prefix}:ref:refs/heads/main' || assertion.sub == '${local.subject_prefix}:pull_request') && assertion.repository == '${var.github_repository}' && assertion.repository_owner_id == '${var.github_repository_owner_id}' && assertion.repository_id == '${var.github_repository_id}'"

  oidc {
    issuer_uri = "https://token.actions.githubusercontent.com"
  }
}

locals {
  pool           = google_iam_workload_identity_pool.github.name # projects/<number>/locations/global/workloadIdentityPools/github
  owner          = split("/", var.github_repository)[0]
  repo           = split("/", var.github_repository)[1]
  subject_prefix = "repo:${local.owner}@${var.github_repository_owner_id}/${local.repo}@${var.github_repository_id}"
}

resource "google_service_account_iam_member" "deployer_from_main" {
  service_account_id = google_service_account.deployer.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "principal://iam.googleapis.com/${local.pool}/subject/${local.subject_prefix}:ref:refs/heads/main"
}

resource "google_service_account_iam_member" "pr_builder_from_pull_requests" {
  service_account_id = google_service_account.pr_builder.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "principal://iam.googleapis.com/${local.pool}/subject/${local.subject_prefix}:pull_request"
}

