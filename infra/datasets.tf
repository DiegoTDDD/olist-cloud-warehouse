# Four datasets, one per layer, so access can be granted per layer: the loader writes raw, the
# transformer reads raw and writes staging and marts, analysts read marts only.
locals {
  datasets = {
    raw = {
      description = "The Olist CSV files as loaded, one table per file. Written only by the loader."
      layer       = "raw"
    }
    staging = {
      description = "dbt views that rename, cast and clean the raw tables. No storage."
      layer       = "staging"
    }
    marts = {
      description = "dbt tables with enforced contracts: the star schema and the decision marts analysts query."
      layer       = "marts"
    }
    ops = {
      description = "Pipeline metadata: load audit, dbt run results, query cost and storage ledger."
      layer       = "ops"
    }
  }
  expiration_ms = var.table_expiration_days * 24 * 60 * 60 * 1000
}

resource "google_bigquery_dataset" "layer" {
  # checkov:skip=CKV_GCP_81:Customer-managed keys need Cloud KMS, which needs billing; the sandbox has none. Data is encrypted at rest with Google-managed keys (docs/adr/0001).
  for_each = local.datasets

  dataset_id                  = each.key
  friendly_name               = each.key
  description                 = each.value.description
  location                    = var.region
  default_table_expiration_ms = local.expiration_ms
  delete_contents_on_destroy  = false

  labels = {
    layer = each.value.layer
  }

  depends_on = [google_project_service.this]
}
