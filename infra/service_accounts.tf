# Two identities for CI, both keyless (see wif.tf):
# - deployer: the main branch. Loads raw, builds staging and marts, writes ops.
# - pr-builder: pull requests. Reads raw and builds into throwaway ci_pr_* datasets it creates
#   itself; it cannot write to any production dataset.
resource "google_service_account" "deployer" {
  account_id   = "olist-deployer"
  display_name = "Olist warehouse deployer (main branch CI)"
  depends_on   = [google_project_service.this]
}

resource "google_service_account" "pr_builder" {
  account_id   = "olist-pr-builder"
  display_name = "Olist warehouse pull request builds (CI)"
  depends_on   = [google_project_service.this]
}

# Project level: run query and load jobs. pr-builder also needs to create its own datasets,
# which bigquery.user allows; it becomes owner of what it creates and nothing else.
resource "google_project_iam_member" "deployer_jobs" {
  project = var.project_id
  role    = "roles/bigquery.jobUser"
  member  = google_service_account.deployer.member
}

# Read-only metadata across the project: the cost report reads table sizes from
# INFORMATION_SCHEMA.TABLE_STORAGE, which is a project-level view.
resource "google_project_iam_member" "deployer_metadata" {
  project = var.project_id
  role    = "roles/bigquery.metadataViewer"
  member  = google_service_account.deployer.member
}

resource "google_project_iam_member" "pr_builder_user" {
  project = var.project_id
  role    = "roles/bigquery.user"
  member  = google_service_account.pr_builder.member
}

# Dataset level: least privilege per layer.
resource "google_bigquery_dataset_iam_member" "deployer_editor" {
  for_each = google_bigquery_dataset.layer

  dataset_id = each.value.dataset_id
  role       = "roles/bigquery.dataEditor"
  member     = google_service_account.deployer.member
}

resource "google_bigquery_dataset_iam_member" "pr_builder_reads_raw" {
  dataset_id = google_bigquery_dataset.layer["raw"].dataset_id
  role       = "roles/bigquery.dataViewer"
  member     = google_service_account.pr_builder.member
}

resource "google_bigquery_dataset_iam_member" "analysts_read_marts" {
  for_each = toset(var.analyst_members)

  dataset_id = google_bigquery_dataset.layer["marts"].dataset_id
  role       = "roles/bigquery.dataViewer"
  member     = each.value
}
