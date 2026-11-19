import pytest
from app.core.observability.pii_sanitizer import PIISanitizer

def test_sanitize_id_card():
    raw = "参保人身份证号为 110101199003072345，核查属实"
    result = PIISanitizer.sanitize(raw)
    assert "110101199003072345" not in result
    assert "110101**********2345" in result


def test_sanitize_id_card_with_x():
    raw = "参保人身份证号为 11010119900307234X，核查属实"
    result = PIISanitizer.sanitize(raw)
    assert "11010119900307234X" not in result
    assert "110101**********234X" in result


def test_sanitize_phone():
    raw = "联系方式: 13800138000"
    result = PIISanitizer.sanitize(raw)
    assert "13800138000" not in result
    assert "138****8000" in result


def test_sanitize_card_number():
    raw = "社保卡卡号: 6222021234567890123"
    result = PIISanitizer.sanitize(raw)
    assert "6222021234567890123" not in result
    assert "622202******0123" in result


def test_sanitize_nested_dict():
    payload = {
        "user": {"name": "张三", "id_card": "420101198501011234"},
        "secrets": {"api_key": "sk-super-secret-key", "token": "abc12345"},
        "metrics": {"violation_amount": 1280.50}
    }
    sanitized = PIISanitizer.sanitize(payload)
    assert sanitized["user"]["name"] == "张三"
    assert "420101198501011234" not in sanitized["user"]["id_card"]
    assert sanitized["secrets"]["api_key"] == "[REDACTED]"
    assert sanitized["secrets"]["token"] == "[REDACTED]"
    assert sanitized["metrics"]["violation_amount"] == 1280.50


def test_sanitize_list_and_primitives():
    payload = [
        "联系方式: 13912345678",
        {"secret_key": "raw_secret"},
        12345,
        None,
        True
    ]
    sanitized = PIISanitizer.sanitize(payload)
    assert sanitized[0] == "联系方式: 139****5678"
    assert sanitized[1]["secret_key"] == "[REDACTED]"
    assert sanitized[2] == 12345
    assert sanitized[3] is None
    assert sanitized[4] is True
