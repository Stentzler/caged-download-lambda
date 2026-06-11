import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
SRC_DIR = PROJECT_ROOT / "src"

sys.path.insert(0, str(SRC_DIR))

from lambda_name.handler import lambda_handler


class LocalLambdaContext:
    function_name = "local-boilerplate-lambda"
    function_version = "$LATEST"
    invoked_function_arn = (
        "arn:aws:lambda:local:000000000000:function:local-boilerplate-lambda"
    )
    memory_limit_in_mb = 128
    aws_request_id = "local-request-id"
    log_group_name = "/aws/lambda/local-boilerplate-lambda"
    log_stream_name = "local"


def main() -> None:
    event_path = PROJECT_ROOT / "events" / "event.json"
    event_text = event_path.read_text() if event_path.exists() else ""
    event = json.loads(event_text) if event_text.strip() else {}

    response = lambda_handler(event, LocalLambdaContext())

    print(response)


if __name__ == "__main__":
    main()
