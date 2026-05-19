# Engel Partdata Parser (Cloud Run)

Parses Engel CC300 `.partdata` (gzip tar) files from Cloud Storage, stores decoded raw variables in BigQuery, and writes curated setup + profile tables.

## Features
- FastAPI Cloud Run endpoint with Eventarc payload handling.
- Parses `floatvalues.dat`, `integervalues.dat`, `booleanvalues.dat`, `stringvalues.dat` in archive tree.
- Parses `*.properties` metadata.
- Writes to:
  - `partdata_uploads`
  - `partdata_raw_variables`
  - `partdata_curated_setups`
  - `partdata_profiles`
- Idempotency check by SHA256 against previous successful uploads.
- Copies successful files to processed bucket and failed files to failed bucket.

## Local CLI
```bash
python -m app.main --input /path/to/file.partdata --dry-run

python -m app.main \
  --input /path/to/file.partdata \
  --project notpla-machine-data \
  --dataset engel_partdata \
  --write-bigquery
```

## Deploy
```bash
export PROJECT_ID="notpla-machine-data"
export REGION="europe-west2"
export BQ_LOCATION="europe-west2"
export DATASET_ID="engel_partdata"
export RAW_BUCKET="notpla-engel-partdata-raw"
export PROCESSED_BUCKET="notpla-engel-partdata-processed"
export FAILED_BUCKET="notpla-engel-partdata-failed"
export SERVICE_NAME="engel-partdata-parser"
export SERVICE_ACCOUNT_EMAIL="engel-partdata-parser@notpla-machine-data.iam.gserviceaccount.com"
export IMAGE_URI="europe-west2-docker.pkg.dev/notpla-machine-data/engel-partdata/engel-partdata-parser:latest"

gcloud builds submit \
  --project="${PROJECT_ID}" \
  --tag="${IMAGE_URI}"

gcloud run deploy "${SERVICE_NAME}" \
  --project="${PROJECT_ID}" \
  --region="${REGION}" \
  --image="${IMAGE_URI}" \
  --service-account="${SERVICE_ACCOUNT_EMAIL}" \
  --no-allow-unauthenticated \
  --set-env-vars="PROJECT_ID=${PROJECT_ID},DATASET_ID=${DATASET_ID},RAW_BUCKET=${RAW_BUCKET},PROCESSED_BUCKET=${PROCESSED_BUCKET},FAILED_BUCKET=${FAILED_BUCKET},BQ_LOCATION=${BQ_LOCATION},PARSER_VERSION=0.1.0" \
  --memory="1Gi" \
  --cpu="1" \
  --timeout="900"
```

## Eventarc trigger
```bash
gcloud eventarc triggers delete engel-partdata-raw-upload \
  --project="${PROJECT_ID}" \
  --location="${REGION}" \
  --quiet

gcloud eventarc triggers create engel-partdata-raw-upload \
  --project="${PROJECT_ID}" \
  --location="${REGION}" \
  --destination-run-service="${SERVICE_NAME}" \
  --destination-run-region="${REGION}" \
  --event-filters="type=google.cloud.storage.object.v1.finalized" \
  --event-filters="bucket=${RAW_BUCKET}" \
  --service-account="${SERVICE_ACCOUNT_EMAIL}"
```

## Manual test upload
```bash
gcloud storage cp /home/callum/setupfile_KY.partdata \
  "gs://${RAW_BUCKET}/manual-test/setupfile_KY.partdata"
```

## Validate logs and BQ
```bash
gcloud logging read \
'resource.type="cloud_run_revision"
 resource.labels.service_name="engel-partdata-parser"' \
--project="${PROJECT_ID}" \
--freshness=30m \
--limit=100 \
--format="value(timestamp,severity,textPayload,jsonPayload.message)"

bq query \
--project_id="${PROJECT_ID}" \
--location="${BQ_LOCATION}" \
--use_legacy_sql=false "
SELECT *
FROM \`${PROJECT_ID}.${DATASET_ID}.partdata_curated_setups\`
ORDER BY created_at DESC
LIMIT 5;"
```
