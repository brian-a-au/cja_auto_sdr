"""
Tests for enhanced error message functionality

Tests the ErrorMessageHelper class and its integration with the codebase.
"""

import pytest
from cja_sdr_generator import ErrorMessageHelper


class TestErrorMessageHelper:
    """Test the ErrorMessageHelper class"""

    def test_http_401_error_message(self):
        """Test 401 authentication error message"""
        msg = ErrorMessageHelper.get_http_error_message(401, "getDataViews")
        assert "Authentication Failed" in msg
        assert "CLIENT_ID and SECRET" in msg
        assert "@AdobeOrg" in msg
        assert "developer.adobe.com/console" in msg

    def test_http_404_error_message(self):
        """Test 404 not found error message"""
        msg = ErrorMessageHelper.get_http_error_message(404, "getDataView")
        assert "Resource Not Found" in msg
        assert "--list-dataviews" in msg
        assert "double-check for typos" in msg

    def test_http_429_rate_limit_message(self):
        """Test 429 rate limit error message"""
        msg = ErrorMessageHelper.get_http_error_message(429, "API call")
        assert "Rate Limit Exceeded" in msg
        assert "--workers 2" in msg
        assert "--enable-cache" in msg

    def test_http_500_server_error_message(self):
        """Test 500 server error message"""
        msg = ErrorMessageHelper.get_http_error_message(500, "API request")
        assert "Internal Server Error" in msg
        assert "temporary issue" in msg
        assert "--max-retries 5" in msg

    def test_http_503_service_unavailable(self):
        """Test 503 service unavailable message"""
        msg = ErrorMessageHelper.get_http_error_message(503, "API call")
        assert "Service Unavailable" in msg
        assert "status.adobe.com" in msg
        assert "maintenance" in msg

    def test_unknown_http_status_code(self):
        """Test handling of unknown HTTP status codes"""
        msg = ErrorMessageHelper.get_http_error_message(999, "test operation")
        assert "HTTP 999" in msg
        assert "unexpected HTTP error" in msg
        assert "TROUBLESHOOTING.md" in msg

    def test_connection_error_message(self):
        """Test network connection error message"""
        error = ConnectionError("Connection refused")
        msg = ErrorMessageHelper.get_network_error_message(error, "fetchData")
        assert "ConnectionError" in msg
        assert "internet connection" in msg
        assert "adobe.io" in msg

    def test_timeout_error_message(self):
        """Test timeout error message"""
        error = TimeoutError("Operation timed out")
        msg = ErrorMessageHelper.get_network_error_message(error, "getMetrics")
        assert "TimeoutError" in msg
        assert "timed out" in msg
        assert "--retry-max-delay 60" in msg

    def test_config_file_not_found_message(self):
        """Test config file not found error message"""
        msg = ErrorMessageHelper.get_config_error_message("file_not_found")
        assert "Configuration File Not Found" in msg
        assert "--sample-config" in msg
        assert "export ORG_ID" in msg

    def test_invalid_json_config_message(self):
        """Test invalid JSON config error message"""
        msg = ErrorMessageHelper.get_config_error_message(
            "invalid_json",
            details="Line 5, Column 12: Unterminated string"
        )
        assert "Invalid JSON" in msg
        assert "Line 5, Column 12" in msg
        assert "jsonlint.com" in msg
        assert "trailing commas" in msg.lower()

    def test_missing_credentials_message(self):
        """Test missing credentials error message"""
        msg = ErrorMessageHelper.get_config_error_message("missing_credentials")
        assert "Missing Required Credentials" in msg
        assert "org_id" in msg
        assert "client_id" in msg
        assert "secret" in msg
        assert "developer.adobe.com/console" in msg

    def test_invalid_format_message(self):
        """Test invalid credential format message"""
        msg = ErrorMessageHelper.get_config_error_message("invalid_format")
        assert "Invalid Credential Format" in msg
        assert "@AdobeOrg" in msg
        assert "alphanumeric" in msg

    def test_data_view_not_found_message_without_count(self):
        """Test data view not found message without available count"""
        msg = ErrorMessageHelper.get_data_view_error_message("dv_12345")
        assert "Data View Not Found" in msg
        assert "dv_12345" in msg
        assert "--list-dataviews" in msg
        assert "dv_" in msg

    def test_data_view_not_found_message_with_count(self):
        """Test data view not found message with available count"""
        msg = ErrorMessageHelper.get_data_view_error_message("dv_invalid", available_count=5)
        assert "Data View Not Found" in msg
        assert "dv_invalid" in msg
        assert "5 data view(s)" in msg

    def test_data_view_not_found_message_zero_available(self):
        """Test data view not found message when no data views available"""
        msg = ErrorMessageHelper.get_data_view_error_message("dv_test", available_count=0)
        assert "Data View Not Found" in msg
        assert "No data views found" in msg
        assert "CJA access" in msg

    def test_all_messages_include_documentation_links(self):
        """Test that all error messages include documentation links"""
        http_msg = ErrorMessageHelper.get_http_error_message(401)
        network_msg = ErrorMessageHelper.get_network_error_message(ConnectionError())
        config_msg = ErrorMessageHelper.get_config_error_message("file_not_found")
        dv_msg = ErrorMessageHelper.get_data_view_error_message("dv_test")

        # Check that each message type includes some form of help link
        assert "TROUBLESHOOTING.md" in http_msg or "QUICKSTART_GUIDE.md" in http_msg
        assert "TROUBLESHOOTING.md" in network_msg
        assert "QUICKSTART_GUIDE.md" in config_msg or "TROUBLESHOOTING.md" in config_msg
        assert "TROUBLESHOOTING.md" in dv_msg

    def test_error_messages_are_well_formatted(self):
        """Test that error messages are well-formatted and readable"""
        msg = ErrorMessageHelper.get_http_error_message(404, "test")

        # Should have clear sections
        assert "=" in msg  # Section dividers
        assert "Why this happened:" in msg
        assert "How to fix it:" in msg

        # Should have numbered suggestions
        assert "1." in msg
        assert "2." in msg

    def test_error_messages_include_operation_context(self):
        """Test that error messages include the operation that failed"""
        operation_name = "getDataViews (connection test)"
        msg = ErrorMessageHelper.get_http_error_message(401, operation_name)

        assert operation_name in msg

    def test_config_error_with_custom_details(self):
        """Test that config error messages can include custom details"""
        details = "Missing field: client_id"
        msg = ErrorMessageHelper.get_config_error_message("missing_credentials", details=details)

        assert details in msg
        assert "Details:" in msg


class TestErrorMessageIntegration:
    """Test integration of enhanced error messages with existing code"""

    def test_retryable_http_error_integration(self):
        """Test that RetryableHTTPError works with ErrorMessageHelper"""
        from cja_sdr_generator import RetryableHTTPError

        # Create a RetryableHTTPError
        error = RetryableHTTPError(429, "Rate limit exceeded")

        # Verify the error has the right status code
        assert error.status_code == 429

        # Verify we can generate an error message for it
        msg = ErrorMessageHelper.get_http_error_message(error.status_code)
        assert "Rate Limit" in msg

    def test_error_messages_for_all_retryable_status_codes(self):
        """Test that we have error messages for all retryable status codes"""
        from cja_sdr_generator import RETRYABLE_STATUS_CODES

        # Test that we can generate messages for all retryable status codes
        for status_code in RETRYABLE_STATUS_CODES:
            msg = ErrorMessageHelper.get_http_error_message(status_code)
            assert msg
            assert str(status_code) in msg
            assert "How to fix it:" in msg
