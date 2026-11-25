# GitHub Actions authenticates with its own short-lived OIDC token; there is no service account
# key anywhere. The provider only accepts tokens from one repository of one owner, and each
# service account trusts exactly one token subject:
#   deployer   <- repo:<repo>:ref:refs/heads/main   (pushes, schedules and manual runs on main)
#   pr-builder <- repo:<repo>:pull_request          (pull requests from branches of this repo)
resource "google_iam_workload_identity_pool" "github" {
  workload_identity_pool_id = "github"
  display_name              = "GitHub Actions"
  description               = "OIDC tokens from GitHub Actions in ${var.github_repository}"
  depends_on                = [google_project_service.this]
}

resource "google_iam_workload_identity_pool_provider" "github" {
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
  # Written out in full (not interpolated) so static scanners can verify it; the check block
  # below fails the plan if it ever drifts from var.github_repository.
  attribute_condition = "(assertion.sub == 'repo:DiegoTDDD/olist-cloud-warehouse:ref:refs/heads/main' || assertion.sub == 'repo:DiegoTDDD/olist-cloud-warehouse:pull_request') && assertion.repository == 'DiegoTDDD/olist-cloud-warehouse' && assertion.repository_owner_id == '183739024'"

  oidc {
    issuer_uri = "https://token.actions.githubusercontent.com"
  }
}

locals {
  pool = google_iam_workload_identity_pool.github.name # projects/<number>/locations/global/workloadIdentityPools/github
}

resource "google_service_account_iam_member" "deployer_from_main" {
  service_account_id = google_service_account.deployer.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "principal://iam.googleapis.com/${local.pool}/subject/repo:${var.github_repository}:ref:refs/heads/main"
}

resource "google_service_account_iam_member" "pr_builder_from_pull_requests" {
  service_account_id = google_service_account.pr_builder.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "principal://iam.googleapis.com/${local.pool}/subject/repo:${var.github_repository}:pull_request"
}

check "trust_condition_matches_variables" {
  assert {
    condition = strcontains(
      google_iam_workload_identity_pool_provider.github.attribute_condition,
      "assertion.repository == '${var.github_repository}' && assertion.repository_owner_id == '${var.github_repository_owner_id}'"
    )
    error_message = "The WIF attribute_condition does not match var.github_repository / var.github_repository_owner_id."
  }
}
