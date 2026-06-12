# CAGED Download Lambda

AWS Lambda that downloads one Novo CAGED archive from the public FTP server,
stores it temporarily in `/tmp`, and uploads it to Amazon S3.
After a successful upload, it records the file in the DynamoDB downloaded-file
registry.

The Lambda is designed to run inside a Step Functions `Map` state. Each
invocation receives one item from the availability check's `new_files` array.

## Event

```json
{
  "filename": "CAGEDMOV202604.7z",
  "ftp_url": "ftp://ftp.mtps.gov.br/pdet/microdados/NOVO%20CAGED/2026/202604/CAGEDMOV202604.7z",
  "reference_month": "202604",
  "reference_year": "2026",
  "s3_key": "raw/caged/year=2026/month=04/file_type=movement/CAGEDMOV202604.7z"
}
```

## Response

```json
{
  "status": "downloaded",
  "filename": "CAGEDMOV202604.7z",
  "reference_month": "202604",
  "reference_year": "2026",
  "s3_bucket": "caged-raw-data",
  "s3_key": "raw/caged/year=2026/month=04/file_type=movement/CAGEDMOV202604.7z",
  "size_bytes": 123456
}
```

Download or upload errors are raised to the caller so Step Functions can apply
its retry and catch policies. Temporary files are removed after both successful
and failed transfers.

Before downloading, the Lambda performs a strongly consistent registry read.
Files already marked `downloaded` or `skipped` are returned with
`status: "skipped"` without contacting FTP or S3. Successful uploads update:

```text
tree.<reference_year>.<reference_month>.<filename>
```

with:

- `status: "downloaded"` for the ingestion lifecycle.
- `processing_status: "pending"` for downstream processing.
- `process_tag` formatted as `year_month_filename`.
- `s3_url` and a UTC `updated_at` timestamp.

Downstream workers should transition `processing_status` from `pending` to
`processing`, then to `succeeded` or `failed`. Detailed attempts and pipeline
history belong in the separate processing table keyed by `process_tag`.

## Environment Variables

```env
S3_BUCKET_NAME=
FTP_TIMEOUT_SECONDS=30
FTP_DOWNLOAD_BLOCK_SIZE=65536
REGISTRY_TABLE_NAME=downloaded_files_registry
REGISTRY_ID=ftp_tree
DYNAMODB_ENDPOINT_URL=
AWS_ENDPOINT_URL_DYNAMODB=
DYNAMODB_MAX_POOL_CONNECTIONS=10
S3_ENDPOINT_URL=
AWS_ENDPOINT_URL_S3=
S3_MAX_POOL_CONNECTIONS=10
POWERTOOLS_SERVICE_NAME=download
POWERTOOLS_LOG_LEVEL=INFO
POWERTOOLS_LOG_EVENT=false
```

`S3_BUCKET_NAME`, `REGISTRY_TABLE_NAME`, and `REGISTRY_ID` identify the storage
destinations. S3 and DynamoDB endpoint overrides are intended for local
development and should remain unset in AWS.

The Lambda execution role requires `s3:PutObject` for the destination prefix
and `dynamodb:GetItem` plus `dynamodb:UpdateItem` for the registry table.

## Development

```bash
uv sync --all-groups
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

The download repository must reference a released `serverless-toolkit` version
that includes `serverless_toolkit.aws.s3` before deployment.
