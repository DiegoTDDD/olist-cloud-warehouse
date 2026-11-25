#!/usr/bin/env bash
# One-time setup, run by a human in Cloud Shell (already signed in as the project owner):
#   git clone https://github.com/DiegoTDDD/olist-cloud-warehouse && bash olist-cloud-warehouse/scripts/bootstrap.sh
# Creates the datasets, the two CI service accounts and the Workload Identity Federation trust,
# then prints the four values to store as GitHub repository variables. Nothing else ever uses
# the owner's credentials: from here on, CI authenticates as the service accounts, keylessly.
set -euo pipefail
cd "$(dirname "$0")/../infra"
project="$(gcloud config get project 2>/dev/null)"
echo "project: $project"
if ! gcloud auth print-access-token >/dev/null 2>&1; then
  echo "Cloud Shell is not authorized yet: click 'Authorize' in the Cloud Shell prompt, then run again."
  exit 1
fi

# Cloud Shell no longer ships Terraform: install a pinned release into ~/bin, checked against
# HashiCorp's published SHA-256 sums.
tf_version=1.17.2
if ! command -v terraform >/dev/null || ! terraform version | grep -q "v${tf_version}"; then
  tmp="$(mktemp -d)"
  base="https://releases.hashicorp.com/terraform/${tf_version}"
  curl -fsSL -o "$tmp/tf.zip" "$base/terraform_${tf_version}_linux_amd64.zip"
  curl -fsSL -o "$tmp/sums" "$base/terraform_${tf_version}_SHA256SUMS"
  (cd "$tmp" && grep "linux_amd64.zip" sums | sed "s/terraform_${tf_version}_linux_amd64.zip/tf.zip/" | sha256sum --check --strict)
  mkdir -p "$HOME/bin" && unzip -o -q "$tmp/tf.zip" -d "$HOME/bin" && rm -rf "$tmp"
  export PATH="$HOME/bin:$PATH"
fi
terraform version | head -1

# Is Cloud Storage available without billing? If so, keep Terraform state there (ADR 0005).
bucket="gs://${project}-tfstate"
if gcloud storage buckets describe "$bucket" >/dev/null 2>&1 ||
   gcloud storage buckets create "$bucket" --location=southamerica-east1 --uniform-bucket-level-access \
     --public-access-prevention >/dev/null 2>&1; then
  gcloud storage buckets update "$bucket" --versioning >/dev/null 2>&1 || true
  printf 'terraform {\n  backend "gcs" {}\n}\n' > backend_override.tf
  terraform init -input=false -reconfigure -backend-config="bucket=${project}-tfstate" -backend-config="prefix=olist" >/dev/null
  echo "state: $bucket"
else
  rm -f backend_override.tf
  terraform init -input=false >/dev/null
  echo "state: local (Cloud Storage needs billing in this project)"
fi

terraform apply -input=false -auto-approve -var "project_id=$project" > /tmp/apply.log 2>&1 || { tail -40 /tmp/apply.log; exit 1; }
grep -E "^Apply complete" /tmp/apply.log
echo "--- GitHub repository variables ---"
echo "GCP_PROJECT=$project"
echo "WIF_PROVIDER=$(terraform output -raw workload_identity_provider)"
echo "DEPLOYER_SA=$(terraform output -raw deployer_service_account)"
echo "PR_BUILDER_SA=$(terraform output -raw pr_builder_service_account)"
terraform output -json > /tmp/outputs.json
