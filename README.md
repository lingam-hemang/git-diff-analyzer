# Git Diff Analyzer

An AI-powered CLI tool that analyzes git commits and generates:

- **PDF documentation** — plain-English summary of what changed and why, schema/data change details, and recommendations.
- **Snowflake DML/DDL scripts** — numbered, transaction-safe SQL scripts to accommodate database implications of code changes.

Supports two AI backends: **AWS Bedrock** (Claude) and **local Ollama** models.

---

## Table of Contents

- [Project Structure](#project-structure)
- [Installation](#installation)
- [Configuration](#configuration)
- [CLI Usage](#cli-usage)
- [Web UI](#web-ui)
- [AWS Lambda Deployment](#aws-lambda-deployment)
- [Output](#output)
- [Running Tests](#running-tests)
- [Repository & Contribution](#repository--contribution)

---

## Project Structure

```
├── pyproject.toml
├── config.example.yaml          # Copy this to ~/.git-diff-analyzer.yaml
├── src/git_diff_analyzer/
│   ├── cli.py                   # Typer CLI entry point
│   ├── config.py                # YAML config loader
│   ├── models.py                # Pydantic data models
│   ├── git_integration.py       # Git diff extraction (gitpython)
│   ├── analysis.py              # AI orchestration pipeline
│   ├── lambda_handler.py        # AWS Lambda entry point
│   ├── utils.py                 # Logging setup
│   ├── ai/
│   │   ├── base.py              # Abstract AIProvider interface
│   │   ├── bedrock_provider.py  # AWS Bedrock (Claude via boto3)
│   │   ├── ollama_provider.py   # Local LLM (Ollama REST API)
│   │   └── prompts.py           # Jinja2 prompt templates
│   └── generators/
│       ├── pdf_generator.py     # PDF report (fpdf2)
│       ├── dml_generator.py     # Snowflake SQL scripts
│       └── s3_uploader.py       # S3 upload helper (boto3)
├── tests/                       # pytest test suite
└── output/
    ├── docs/                    # Generated PDFs
    └── dml/                     # Generated SQL scripts
```

---

## Installation

### Prerequisites

- Python 3.9+
- A git repository to analyze
- One of:
  - AWS account with Bedrock access (for Claude models)
  - [Ollama](https://ollama.com) running locally (for local models)

### Install from source

```bash
# Clone the repository
git clone https://github.com/YOUR_ORG/YOUR_REPO_NAME.git
cd YOUR_REPO_NAME

# Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate        # macOS/Linux
# .venv\Scripts\activate         # Windows

# Install the package
pip install -e ".[dev]"

# Verify installation
git-diff-analyzer --help
```

> **Replace** `YOUR_ORG/YOUR_REPO_NAME` with your actual GitHub repository path.

---

## Configuration

### 1. Create your config file

```bash
git-diff-analyzer config init
```

This writes a starter config to `~/.git-diff-analyzer.yaml`. Open it and fill in your values:

```bash
# macOS/Linux
open ~/.git-diff-analyzer.yaml
```

Or copy the example manually:

```bash
cp config.example.yaml ~/.git-diff-analyzer.yaml
```

### 2. Config file reference

```yaml
bedrock:
  region: us-east-1                                      # AWS region
  model_id: anthropic.claude-3-5-sonnet-20241022-v2:0   # Bedrock model ID
  max_tokens: 4096
  temperature: 0.1
  # profile: my-aws-profile   # Uncomment to use a named AWS CLI profile

ollama:
  base_url: http://localhost:11434   # Ollama server URL
  model: llama3.1:8b                 # Any model pulled in Ollama
  timeout: 120                       # Request timeout in seconds
  max_tokens: 4096
  temperature: 0.1

output:
  base_dir: output
  docs_dir: output/docs   # Where PDFs are written
  dml_dir: output/dml     # Where SQL scripts are written
  create_dirs: true

snowflake:
  database: MY_DATABASE    # Target Snowflake database name
  schema_name: PUBLIC      # Target schema
  warehouse: COMPUTE_WH    # Warehouse for generated scripts
  # role: SYSADMIN         # Uncomment to set a default role
  use_transactions: true   # Wraps every script in BEGIN / ROLLBACK

analysis:
  max_diff_size: 50000      # Max total characters sent to AI per request
  max_file_diff_size: 8000  # Per-file character cap before truncation
  default_provider: ollama  # "bedrock" or "ollama"
  verbose: false

deployment:
  mode: local               # "local" (CLI) or "aws" (Lambda + S3 upload)

aws_lambda:
  trigger_source: github    # "github", "codecommit", or "both"
  # github_webhook_secret: whsec_...    # Required for signature verification
  # codecommit_repo_arn: arn:aws:...    # For CodeCommit event rules

s3:
  bucket: my-analysis-bucket   # S3 bucket for output uploads (aws mode)
  prefix: git-diff-analyzer/   # Key prefix within the bucket
  # region: us-east-1
```

### 3. AWS Bedrock setup

Ensure your AWS credentials are configured:

```bash
# Using AWS CLI profiles
aws configure --profile my-aws-profile

# Or set environment variables
export AWS_ACCESS_KEY_ID=your_key
export AWS_SECRET_ACCESS_KEY=your_secret
export AWS_DEFAULT_REGION=us-east-1
```

Make sure the IAM user/role has `bedrock:InvokeModel` permission on the model ARN.

### 4. Ollama setup

```bash
# Install Ollama: https://ollama.com

# Pull a model
ollama pull llama3.1:8b

# Start the server (runs on port 11434 by default)
ollama serve
```

### 5. Config precedence

The tool loads config in this order (highest wins):

1. `--config` flag on the CLI
2. `.git-diff-analyzer.yaml` in the current working directory
3. `~/.git-diff-analyzer.yaml` (home directory)
4. Built-in defaults

---

## CLI Usage

### Analyze a single commit

```bash
# Analyze HEAD commit of the current repo
git-diff-analyzer analyze

# Analyze a specific commit by SHA or tag
git-diff-analyzer analyze --commit abc1234
git-diff-analyzer analyze --commit v1.2.0

# Analyze a repo in another directory
git-diff-analyzer analyze --commit HEAD --repo /path/to/your/repo
```

### Analyze a commit range

```bash
# Changes from tag v1.0.0 up to HEAD
git-diff-analyzer analyze --from v1.0.0 --to HEAD --repo /path/to/repo

# Changes between two branches
git-diff-analyzer analyze --from main --to feature/my-feature

# Changes between two commit SHAs
git-diff-analyzer analyze --from abc1234 --to def5678
```

### Choose AI provider

```bash
# Use Ollama (local) — overrides default_provider in config
git-diff-analyzer analyze --commit HEAD --provider ollama

# Use AWS Bedrock
git-diff-analyzer analyze --commit HEAD --provider bedrock
```

### Control output format

```bash
# Generate both PDF and SQL scripts (default)
git-diff-analyzer analyze --commit HEAD --format all

# PDF report only
git-diff-analyzer analyze --commit HEAD --format pdf

# SQL scripts only
git-diff-analyzer analyze --commit HEAD --format dml
```

### Verbose logging

```bash
git-diff-analyzer analyze --commit HEAD --verbose
```

### Config management

```bash
# Show the currently active config (merged from all sources)
git-diff-analyzer config show

# Create a starter config at ~/.git-diff-analyzer.yaml
git-diff-analyzer config init

# Write config to a custom location
git-diff-analyzer config init --dest ./my-config.yaml

# Overwrite an existing config
git-diff-analyzer config init --force
```

---

## AWS Lambda Deployment

The tool can run as a serverless Lambda function triggered by GitHub webhooks or AWS CodeCommit events. Set `deployment.mode: aws` in your config to enable S3 output uploads automatically.

### GitHub Webhook Setup

1. In your GitHub repository, go to **Settings → Webhooks → Add webhook**.
2. Set the **Payload URL** to your Lambda function URL (via Function URL or API Gateway).
3. Set **Content type** to `application/json`.
4. Set a **Secret** and add it to your config as `aws_lambda.github_webhook_secret`.
5. Choose **Just the push event** (or send me everything and the handler will ignore non-push events).

### CodeCommit Event Rule Setup

1. In the AWS Console, go to **Amazon EventBridge → Rules → Create rule**.
2. Set the **Event source** to `AWS services` → `CodeCommit`.
3. Add an event pattern for `referenceCreated` and `referenceUpdated` on the target repository.
4. Add your Lambda function as the target.
5. Optionally set `aws_lambda.codecommit_repo_arn` in config to restrict processing to one repo.

### Deployment with AWS SAM

```bash
# Build and deploy via AWS SAM (create template.yaml pointing to src/)
sam build
sam deploy --guided

# Environment variables for Lambda
GDA_CONFIG=/var/task/config.yaml   # Path to bundled config inside the Lambda package
```

### Deployment with Terraform / CDK

Point to `src/git_diff_analyzer/lambda_handler.handler` as the handler.
Ensure the Lambda execution role has:
- `s3:PutObject` on your output bucket
- `codecommit:GetCommit`, `codecommit:GetDifferences` if using CodeCommit trigger
- `bedrock:InvokeModel` if using AWS Bedrock as AI provider

---

## Output

### PDF report (`output/docs/`)

Each analysis writes a PDF named `analysis_<commit_hash>.pdf` containing:

| Section | Contents |
|---------|----------|
| Commit Details | Hash, author, date, message, AI model used |
| Summary | Plain-English description of what changed |
| Impact Assessment | Technical and business impact |
| Affected Objects | Database objects (tables, views, procedures) and code objects (files, classes, functions, endpoints) touched by the commit |
| Schema Changes | DDL statements (ALTER TABLE, CREATE TABLE, etc.) |
| Data Changes | DML statements (INSERT, UPDATE, DELETE, MERGE) |
| Recommendations | Prioritised action items |

### SQL scripts (`output/dml/<commit_hash>/`)

Scripts are numbered so DDL always runs before DML:

```
output/dml/abc123def456/
├── 000_run_all.sql          # Master index — lists all scripts in order
├── 001_ddl_add_column_user.sql
├── 002_dml_update_user.sql
└── ...
```

Each script is wrapped in `BEGIN TRANSACTION; ... ROLLBACK;` by default. Review and replace `ROLLBACK` with `COMMIT` when you are satisfied with the changes.

---

## Running Tests

```bash
# Run all tests
pytest -v

# Run with coverage report
pytest --cov=git_diff_analyzer --cov-report=html

# Run a specific test file
pytest tests/test_git_integration.py -v
pytest tests/test_pdf_generator.py -v
```

---

## Repository & Contribution

| Item | Value |
|------|-------|
| GitHub repository | `https://github.com/YOUR_ORG/YOUR_REPO_NAME` |
| Issue tracker | `https://github.com/YOUR_ORG/YOUR_REPO_NAME/issues` |
| Pull requests | `https://github.com/YOUR_ORG/YOUR_REPO_NAME/pulls` |

> **Update the placeholders above** (`YOUR_ORG`, `YOUR_REPO_NAME`) once you have pushed this project to GitHub.

### Development setup

```bash
git clone https://github.com/YOUR_ORG/YOUR_REPO_NAME.git
cd YOUR_REPO_NAME
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

### Adding a new AI provider

1. Create `src/git_diff_analyzer/ai/my_provider.py` implementing `AIProvider` from `ai/base.py`.
2. Register it in `ai/__init__.py` `get_provider()`.
3. Add a config section to `config.py` and `config.example.yaml`.
4. Add tests in `tests/test_ai_providers.py`.

---

## Troubleshooting

**`Cannot connect to Ollama`**
Ensure Ollama is running: `ollama serve`. Check `base_url` in config matches the running server.

**`Bedrock call failed: AccessDenied`**
Verify your AWS credentials and that the IAM policy includes `bedrock:InvokeModel` for the model ARN you configured.

**`Not a git repository`**
Pass the correct path with `--repo /absolute/path/to/repo`, or run the command from inside the repository.

**Large diffs produce poor AI output**
Reduce `max_diff_size` and `max_file_diff_size` in config, or analyze individual commits instead of large ranges.

---

## Web UI

A Django-based web interface for browsing analysis results, triggering new analyses, and downloading generated PDF reports and SQL scripts.

### Setup

```bash
# Install Django (if not already installed)
pip install "django>=5.0"

# Run database migrations
python manage.py migrate

# Create a superuser (optional, for /admin access)
python manage.py createsuperuser

# Start the development server
python manage.py runserver
```

Then open <http://127.0.0.1:8000/> in your browser.

> `manage.py` automatically adds `src/` to the Python path, so no `PYTHONPATH=src` prefix is needed.

### Usage

| Page | URL | Description |
|------|-----|-------------|
| Analysis list | `/` | Browse all analyses with search and pagination |
| Analysis detail | `/<uuid>/` | Full report: summary, schema/data changes, recommendations, scripts |
| New analysis | `/new/` | Run a new analysis via web form (calls AI synchronously) |
| Download PDF | `/<uuid>/download/pdf/` | Download the PDF report |
| Download script | `/<uuid>/download/script/<uuid>/` | Download a single SQL file |
| Download all scripts | `/<uuid>/download/all-scripts/` | Download all SQL scripts as ZIP |
| JSON export | `/<uuid>/json/` | Full analysis data as JSON |
| Admin | `/admin/` | Django admin for managing analyses and scripts |

### Import from CLI

Use the `import_analysis` management command to import results from existing CLI runs:

```bash
# Run full pipeline and import into the web DB
python manage.py import_analysis --repo /path/to/repo --commit HEAD --provider ollama

# Import a previously serialised AnalysisResult JSON
python manage.py import_analysis --json /path/to/result.json

# Analyse a commit range
python manage.py import_analysis --repo /path/to/repo --from-ref main~5 --to-ref HEAD
```

