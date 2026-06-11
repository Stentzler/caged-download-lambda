import importlib
import io
import json
import sys
from types import ModuleType


class FakeLambdaContext:
    function_name = "check-availability-test"
    function_version = "$LATEST"
    invoked_function_arn = (
        "arn:aws:lambda:us-east-1:123456789012:function:check-availability-test"
    )
    memory_limit_in_mb = 128
    aws_request_id = "test-request-id"
    log_group_name = "/aws/lambda/check-availability-test"
    log_stream_name = "2026/01/01/[$LATEST]abcdef"


def load_handler_module() -> ModuleType:
    sys.modules.pop("lambda_name.handler", None)

    return importlib.import_module("lambda_name.handler")


def test_lambda_handler_returns_availability_result(monkeypatch) -> None:
    monkeypatch.setenv("SOURCE_NAME", "caged")
    monkeypatch.setenv("POWERTOOLS_SERVICE_NAME", "check-availability-test")
    monkeypatch.setenv("POWERTOOLS_LOG_LEVEL", "INFO")
    monkeypatch.setenv("POWERTOOLS_LOG_EVENT", "false")

    handler_module = load_handler_module()

    response = handler_module.lambda_handler({}, FakeLambdaContext())

    assert response == {
        "available": False,
        "source": "caged",
        "message": "No new file found",
    }


def test_lambda_handler_uses_toolkit_logger_with_lambda_context(monkeypatch) -> None:
    monkeypatch.setenv("SOURCE_NAME", "caged")
    monkeypatch.setenv("POWERTOOLS_SERVICE_NAME", "check-availability-test")
    monkeypatch.setenv("POWERTOOLS_LOG_LEVEL", "INFO")
    monkeypatch.setenv("POWERTOOLS_LOG_EVENT", "false")

    handler_module = load_handler_module()

    log_stream = io.StringIO()
    original_stream = handler_module.logger.registered_handler.stream

    try:
        handler_module.logger.registered_handler.setStream(log_stream)

        handler_module.lambda_handler({}, FakeLambdaContext())

        logs = [
            json.loads(line)
            for line in log_stream.getvalue().splitlines()
            if line.strip()
        ]

        assert logs

        first_log = logs[0]

        assert first_log["message"] == "Starting boilerplate check"
        assert first_log["service"] == "check-availability-test"
        assert first_log["function_name"] == "check-availability-test"
        assert first_log["function_request_id"] == "test-request-id"
        assert first_log["function_memory_size"] == 128
        assert first_log["function_arn"] == (
            "arn:aws:lambda:us-east-1:123456789012:function:check-availability-test"
        )
    finally:
        handler_module.logger.registered_handler.setStream(original_stream)