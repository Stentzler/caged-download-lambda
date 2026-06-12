import importlib
import sys
from types import ModuleType


class FakeLambdaContext:
    function_name = "download-test"
    function_version = "$LATEST"
    invoked_function_arn = (
        "arn:aws:lambda:us-east-1:123456789012:function:download-test"
    )
    memory_limit_in_mb = 128
    aws_request_id = "test-request-id"
    log_group_name = "/aws/lambda/download-test"
    log_stream_name = "2026/01/01/[$LATEST]abcdef"


def load_handler_module(monkeypatch) -> ModuleType:
    monkeypatch.setenv("S3_BUCKET_NAME", "caged-raw-data")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("POWERTOOLS_SERVICE_NAME", "download-test")
    monkeypatch.setenv("POWERTOOLS_LOG_LEVEL", "INFO")
    monkeypatch.setenv("POWERTOOLS_LOG_EVENT", "false")
    sys.modules.pop("handler", None)

    return importlib.import_module("handler")


def test_handler_returns_service_result(monkeypatch) -> None:
    handler_module = load_handler_module(monkeypatch)
    expected = {
        "status": "downloaded",
        "filename": "file.7z",
        "size_bytes": 100,
    }

    class FakeService:
        def execute(self, event):
            assert event == {"filename": "file.7z"}
            return expected

    class FakeLogger:
        def __init__(self) -> None:
            self.info_calls = []

        def info(self, message, **context) -> None:
            self.info_calls.append((message, context))

    monkeypatch.setattr(handler_module, "service", FakeService())
    fake_logger = FakeLogger()
    monkeypatch.setattr(handler_module, "logger", fake_logger)

    response = handler_module.handler({"filename": "file.7z"}, FakeLambdaContext())

    assert response is expected
    assert fake_logger.info_calls[-1] == (
        "Finished CAGED file download",
        {
            "archive_filename": "file.7z",
            "transfer_status": "downloaded",
            "size_bytes": 100,
        },
    )


def test_handler_propagates_service_error(monkeypatch) -> None:
    handler_module = load_handler_module(monkeypatch)

    class FailingService:
        def execute(self, event):
            raise RuntimeError("download failed")

    class FakeLogger:
        def __init__(self) -> None:
            self.exception_calls = []

        def info(self, message, **context) -> None:
            pass

        def exception(self, message, **context) -> None:
            self.exception_calls.append((message, context))

    monkeypatch.setattr(handler_module, "service", FailingService())
    fake_logger = FakeLogger()
    monkeypatch.setattr(handler_module, "logger", fake_logger)

    try:
        handler_module.handler({}, FakeLambdaContext())
    except RuntimeError as error:
        assert str(error) == "download failed"
    else:
        raise AssertionError("Expected handler to propagate the service error")

    assert fake_logger.exception_calls == [("Failed to download CAGED file", {})]
