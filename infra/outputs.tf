output "workload_identity_provider" {
  description = "Value for the WIF_PROVIDER repository variable."
  value       = google_iam_workload_identity_pool_provider.github.name
}

output "deployer_service_account" {
  description = "Value for the DEPLOYER_SA repository variable."
  value       = google_service_account.deployer.email
}

output "pr_builder_service_account" {
  description = "Value for the PR_BUILDER_SA repository variable."
  value       = google_service_account.pr_builder.email
}

output "datasets" {
  value = { for k, d in google_bigquery_dataset.layer : k => d.id }
}
