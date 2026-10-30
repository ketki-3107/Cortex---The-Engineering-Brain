import os
from dotenv import load_dotenv

load_dotenv()

GITLAB_URL = os.getenv("GITLAB_URL", "https://gitlab.com")
GITLAB_TOKEN = os.getenv("GITLAB_TOKEN")

_GITLAB_PROJECT_ID_RAW = os.getenv("GITLAB_PROJECT_ID")
GITLAB_PROJECT_ID = int(_GITLAB_PROJECT_ID_RAW) if _GITLAB_PROJECT_ID_RAW else None

_CORTEX_ORG_PROJECT_ID_RAW = os.getenv("CORTEX_ORG_PROJECT_ID")
CORTEX_ORG_PROJECT_ID = int(_CORTEX_ORG_PROJECT_ID_RAW) if _CORTEX_ORG_PROJECT_ID_RAW else GITLAB_PROJECT_ID

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
ANTHROPIC_BASE_URL = os.getenv("ANTHROPIC_BASE_URL")  # For Siemens or custom endpoints
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "")
PORT = int(os.getenv("PORT", 8000))

CLAUDE_PROVIDER = os.getenv("CLAUDE_PROVIDER", "anthropic").strip().lower()
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-5")

BEDROCK_MODEL_ID = os.getenv("BEDROCK_MODEL_ID", "")
AWS_REGION = os.getenv("AWS_REGION", os.getenv("AWS_DEFAULT_REGION", ""))
AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID", "")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY", "")
AWS_SESSION_TOKEN = os.getenv("AWS_SESSION_TOKEN", "")

CLAUDE_MAX_TOKENS = 2000
CLAUDE_TEMPERATURE = 0.0

CORTEX_INDEX_SLUG = "CORTEX-INDEX"
MEMORY_SLUG_PREFIX = "CORTEX-MEMORY-"
CORTEX_SPEC_SLUG_PREFIX = "CORTEX-SPEC-"
CORTEX_ORG_INDEX_SLUG = "CORTEX-ORG-INDEX"
ORG_MEMORY_SLUG_PREFIX = "CORTEX-ORG-MEMORY-"

if not GITLAB_TOKEN:
    raise ValueError("GITLAB_TOKEN is not set in .env")
if not GITLAB_PROJECT_ID:
    raise ValueError("GITLAB_PROJECT_ID is not set in .env")

if CLAUDE_PROVIDER not in {"anthropic", "bedrock"}:
    raise ValueError("CLAUDE_PROVIDER must be either 'anthropic' or 'bedrock'")

if CLAUDE_PROVIDER == "anthropic":
    if not ANTHROPIC_API_KEY:
        raise ValueError("ANTHROPIC_API_KEY is not set in .env")

if CLAUDE_PROVIDER == "bedrock":
    if not BEDROCK_MODEL_ID:
        raise ValueError("BEDROCK_MODEL_ID is not set in .env")
    if not AWS_REGION:
        raise ValueError("AWS_REGION (or AWS_DEFAULT_REGION) is not set in .env")