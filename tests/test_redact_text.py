from cja_auto_sdr.core.logging import redact_text


def test_redact_text_scrubs_bearer_token():
    result = redact_text("Authorization: Bearer abc123xyz")
    assert "abc123xyz" not in result
    assert "Bearer" in result  # scheme word is preserved; token is replaced


def test_redact_text_scrubs_quoted_secret_key_value():
    result = redact_text('client_secret="hunter2"')
    assert "hunter2" not in result


def test_redact_text_leaves_innocuous_text_alone():
    msg = "Fetched 12 dimensions for dv_abc"
    assert redact_text(msg) == msg


def test_redact_text_is_pure_string_in_string_out():
    assert isinstance(redact_text("anything"), str)
    assert redact_text("") == ""
