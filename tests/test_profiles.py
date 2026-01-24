"""Tests for profile management functionality"""
import pytest
import os
import json
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock
import tempfile
import shutil

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from cja_sdr_generator import (
    get_cja_home,
    get_profiles_dir,
    get_profile_path,
    validate_profile_name,
    load_profile_config_json,
    load_profile_dotenv,
    load_profile_credentials,
    resolve_active_profile,
    list_profiles,
    show_profile,
    mask_sensitive_value,
    ProfileError,
    ProfileNotFoundError,
    ProfileConfigError,
)


class TestGetCjaHome:
    """Test CJA home directory resolution"""

    def test_default_home(self):
        """Test default ~/.cja path when CJA_HOME not set"""
        with patch.dict(os.environ, {}, clear=True):
            # Clear CJA_HOME if it exists
            os.environ.pop('CJA_HOME', None)
            home = get_cja_home()
            assert home == Path.home() / '.cja'

    def test_custom_home_from_env(self):
        """Test custom path from CJA_HOME environment variable"""
        with patch.dict(os.environ, {'CJA_HOME': '/custom/path'}, clear=False):
            home = get_cja_home()
            assert home == Path('/custom/path')

    def test_home_with_tilde_expansion(self):
        """Test that ~ is expanded in CJA_HOME"""
        with patch.dict(os.environ, {'CJA_HOME': '~/my-cja'}, clear=False):
            home = get_cja_home()
            assert str(home).startswith(str(Path.home()))


class TestGetProfilesDir:
    """Test profiles directory resolution"""

    def test_profiles_dir(self):
        """Test profiles directory is under CJA home"""
        with patch('cja_sdr_generator.get_cja_home', return_value=Path('/home/test/.cja')):
            profiles = get_profiles_dir()
            assert profiles == Path('/home/test/.cja/orgs')


class TestGetProfilePath:
    """Test profile path resolution"""

    def test_profile_path(self):
        """Test profile path includes profile name"""
        with patch('cja_sdr_generator.get_profiles_dir', return_value=Path('/home/test/.cja/orgs')):
            path = get_profile_path('client-a')
            assert path == Path('/home/test/.cja/orgs/client-a')


class TestValidateProfileName:
    """Test profile name validation"""

    def test_valid_simple_name(self):
        """Test valid simple profile name"""
        is_valid, error = validate_profile_name('client')
        assert is_valid is True
        assert error is None

    def test_valid_name_with_dashes(self):
        """Test valid name with dashes"""
        is_valid, error = validate_profile_name('client-a')
        assert is_valid is True
        assert error is None

    def test_valid_name_with_underscores(self):
        """Test valid name with underscores"""
        is_valid, error = validate_profile_name('client_a')
        assert is_valid is True
        assert error is None

    def test_valid_name_with_numbers(self):
        """Test valid name with numbers"""
        is_valid, error = validate_profile_name('client1')
        assert is_valid is True
        assert error is None

    def test_empty_name_invalid(self):
        """Test empty name is invalid"""
        is_valid, error = validate_profile_name('')
        assert is_valid is False
        assert 'empty' in error.lower()

    def test_name_starting_with_dash_invalid(self):
        """Test name starting with dash is invalid"""
        is_valid, error = validate_profile_name('-client')
        assert is_valid is False
        assert 'invalid' in error.lower()

    def test_name_with_spaces_invalid(self):
        """Test name with spaces is invalid"""
        is_valid, error = validate_profile_name('client a')
        assert is_valid is False
        assert 'invalid' in error.lower()

    def test_name_with_special_chars_invalid(self):
        """Test name with special characters is invalid"""
        is_valid, error = validate_profile_name('client@org')
        assert is_valid is False
        assert 'invalid' in error.lower()

    def test_name_too_long_invalid(self):
        """Test name longer than 64 chars is invalid"""
        long_name = 'a' * 65
        is_valid, error = validate_profile_name(long_name)
        assert is_valid is False
        assert 'too long' in error.lower()


class TestLoadProfileConfigJson:
    """Test loading credentials from config.json"""

    def test_load_valid_config(self, tmp_path):
        """Test loading valid config.json"""
        config = {
            'org_id': 'test@AdobeOrg',
            'client_id': 'test_client_id',
            'secret': 'test_secret',
            'scopes': 'openid'
        }
        config_file = tmp_path / 'config.json'
        config_file.write_text(json.dumps(config))

        result = load_profile_config_json(tmp_path)
        assert result is not None
        assert result['org_id'] == 'test@AdobeOrg'
        assert result['client_id'] == 'test_client_id'

    def test_load_nonexistent_config(self, tmp_path):
        """Test loading nonexistent config.json returns None"""
        result = load_profile_config_json(tmp_path)
        assert result is None

    def test_load_invalid_json(self, tmp_path):
        """Test loading invalid JSON returns None"""
        config_file = tmp_path / 'config.json'
        config_file.write_text('not valid json')

        result = load_profile_config_json(tmp_path)
        assert result is None

    def test_strips_whitespace(self, tmp_path):
        """Test that values are stripped of whitespace"""
        config = {'org_id': '  test@AdobeOrg  '}
        config_file = tmp_path / 'config.json'
        config_file.write_text(json.dumps(config))

        result = load_profile_config_json(tmp_path)
        assert result['org_id'] == 'test@AdobeOrg'


class TestLoadProfileDotenv:
    """Test loading credentials from .env file"""

    def test_load_valid_env(self, tmp_path):
        """Test loading valid .env file"""
        env_content = """
ORG_ID=test@AdobeOrg
CLIENT_ID=test_client_id
SECRET=test_secret
SCOPES=openid
"""
        env_file = tmp_path / '.env'
        env_file.write_text(env_content)

        result = load_profile_dotenv(tmp_path)
        assert result is not None
        assert result['org_id'] == 'test@AdobeOrg'
        assert result['client_id'] == 'test_client_id'

    def test_load_nonexistent_env(self, tmp_path):
        """Test loading nonexistent .env returns None"""
        result = load_profile_dotenv(tmp_path)
        assert result is None

    def test_ignores_comments(self, tmp_path):
        """Test that comments are ignored"""
        env_content = """
# This is a comment
ORG_ID=test@AdobeOrg
# CLIENT_ID=commented_out
"""
        env_file = tmp_path / '.env'
        env_file.write_text(env_content)

        result = load_profile_dotenv(tmp_path)
        assert result['org_id'] == 'test@AdobeOrg'
        assert 'client_id' not in result

    def test_strips_quotes(self, tmp_path):
        """Test that quotes are stripped from values"""
        env_content = """
ORG_ID="test@AdobeOrg"
CLIENT_ID='test_client_id'
"""
        env_file = tmp_path / '.env'
        env_file.write_text(env_content)

        result = load_profile_dotenv(tmp_path)
        assert result['org_id'] == 'test@AdobeOrg'
        assert result['client_id'] == 'test_client_id'


class TestLoadProfileCredentials:
    """Test loading and merging profile credentials"""

    def test_load_from_config_json_only(self, tmp_path):
        """Test loading from config.json when no .env exists"""
        # Create profile directory
        profile_dir = tmp_path / 'orgs' / 'test-profile'
        profile_dir.mkdir(parents=True)

        config = {
            'org_id': 'test@AdobeOrg',
            'client_id': 'test_client_id',
            'secret': 'test_secret',
            'scopes': 'openid'
        }
        (profile_dir / 'config.json').write_text(json.dumps(config))

        logger = MagicMock()
        with patch('cja_sdr_generator.get_profile_path', return_value=profile_dir):
            result = load_profile_credentials('test-profile', logger)

        assert result['org_id'] == 'test@AdobeOrg'
        assert result['client_id'] == 'test_client_id'

    def test_env_overrides_json(self, tmp_path):
        """Test that .env values override config.json"""
        # Create profile directory
        profile_dir = tmp_path / 'orgs' / 'test-profile'
        profile_dir.mkdir(parents=True)

        # config.json with one value
        config = {'org_id': 'json@AdobeOrg', 'client_id': 'json_client'}
        (profile_dir / 'config.json').write_text(json.dumps(config))

        # .env with different org_id
        (profile_dir / '.env').write_text('ORG_ID=env@AdobeOrg')

        logger = MagicMock()
        with patch('cja_sdr_generator.get_profile_path', return_value=profile_dir):
            result = load_profile_credentials('test-profile', logger)

        # .env should override config.json
        assert result['org_id'] == 'env@AdobeOrg'
        # client_id from config.json should still be present
        assert result['client_id'] == 'json_client'

    def test_profile_not_found_raises_error(self, tmp_path):
        """Test that missing profile raises ProfileNotFoundError"""
        logger = MagicMock()
        nonexistent_path = tmp_path / 'orgs' / 'nonexistent'

        with patch('cja_sdr_generator.get_profile_path', return_value=nonexistent_path):
            with pytest.raises(ProfileNotFoundError):
                load_profile_credentials('nonexistent', logger)

    def test_empty_profile_raises_error(self, tmp_path):
        """Test that profile with no config raises ProfileConfigError"""
        # Create empty profile directory
        profile_dir = tmp_path / 'orgs' / 'empty-profile'
        profile_dir.mkdir(parents=True)

        logger = MagicMock()
        with patch('cja_sdr_generator.get_profile_path', return_value=profile_dir):
            with pytest.raises(ProfileConfigError):
                load_profile_credentials('empty-profile', logger)

    def test_invalid_profile_name_raises_error(self):
        """Test that invalid profile name raises ProfileConfigError"""
        logger = MagicMock()
        with pytest.raises(ProfileConfigError):
            load_profile_credentials('invalid name', logger)


class TestResolveActiveProfile:
    """Test profile resolution priority"""

    def test_cli_profile_takes_precedence(self):
        """Test that CLI profile overrides environment variable"""
        with patch.dict(os.environ, {'CJA_PROFILE': 'env-profile'}):
            result = resolve_active_profile('cli-profile')
            assert result == 'cli-profile'

    def test_env_profile_used_when_no_cli(self):
        """Test that environment variable is used when no CLI profile"""
        with patch.dict(os.environ, {'CJA_PROFILE': 'env-profile'}):
            result = resolve_active_profile(None)
            assert result == 'env-profile'

    def test_returns_none_when_no_profile(self):
        """Test that None is returned when no profile specified"""
        # Clear CJA_PROFILE from environment
        env = os.environ.copy()
        env.pop('CJA_PROFILE', None)
        with patch.dict(os.environ, env, clear=True):
            result = resolve_active_profile(None)
            assert result is None


class TestMaskSensitiveValue:
    """Test sensitive value masking"""

    def test_mask_normal_value(self):
        """Test masking a normal length value"""
        result = mask_sensitive_value('abcdefghij', show_chars=2)
        assert result == 'ab******ij'

    def test_mask_short_value(self):
        """Test masking a value shorter than show_chars*2"""
        result = mask_sensitive_value('abc', show_chars=2)
        assert result == '***'

    def test_mask_empty_value(self):
        """Test masking empty value"""
        result = mask_sensitive_value('')
        assert result == '(empty)'

    def test_mask_default_chars(self):
        """Test default show_chars value (4)"""
        result = mask_sensitive_value('1234567890abcdef')
        assert result.startswith('1234')
        assert result.endswith('cdef')


class TestListProfiles:
    """Test profile listing functionality"""

    def test_list_no_profiles_dir(self, tmp_path, capsys):
        """Test listing when profiles directory doesn't exist"""
        with patch('cja_sdr_generator.get_profiles_dir', return_value=tmp_path / 'nonexistent'):
            result = list_profiles()
            assert result is True
            captured = capsys.readouterr()
            assert 'No profiles directory' in captured.out

    def test_list_empty_profiles_dir(self, tmp_path, capsys):
        """Test listing when profiles directory is empty"""
        profiles_dir = tmp_path / 'orgs'
        profiles_dir.mkdir()

        with patch('cja_sdr_generator.get_profiles_dir', return_value=profiles_dir):
            result = list_profiles()
            assert result is True
            captured = capsys.readouterr()
            assert 'No profiles found' in captured.out

    def test_list_profiles_table_format(self, tmp_path, capsys):
        """Test listing profiles in table format"""
        profiles_dir = tmp_path / 'orgs'
        profiles_dir.mkdir()

        # Create a profile
        profile = profiles_dir / 'client-a'
        profile.mkdir()
        (profile / 'config.json').write_text('{"org_id": "test@AdobeOrg"}')

        with patch('cja_sdr_generator.get_profiles_dir', return_value=profiles_dir):
            result = list_profiles(output_format='table')
            assert result is True
            captured = capsys.readouterr()
            assert 'client-a' in captured.out

    def test_list_profiles_json_format(self, tmp_path, capsys):
        """Test listing profiles in JSON format"""
        profiles_dir = tmp_path / 'orgs'
        profiles_dir.mkdir()

        # Create a profile
        profile = profiles_dir / 'client-a'
        profile.mkdir()
        (profile / 'config.json').write_text('{"org_id": "test@AdobeOrg"}')

        with patch('cja_sdr_generator.get_profiles_dir', return_value=profiles_dir):
            result = list_profiles(output_format='json')
            assert result is True
            captured = capsys.readouterr()
            output = json.loads(captured.out)
            assert output['count'] == 1
            assert output['profiles'][0]['name'] == 'client-a'


class TestShowProfile:
    """Test profile display functionality"""

    def test_show_existing_profile(self, tmp_path, capsys):
        """Test showing an existing profile"""
        # Create profile directory
        profile_dir = tmp_path / 'orgs' / 'test-profile'
        profile_dir.mkdir(parents=True)

        config = {
            'org_id': 'test@AdobeOrg',
            'client_id': 'test_client_id_12345678',
            'secret': 'test_secret_12345678',
            'scopes': 'openid'
        }
        (profile_dir / 'config.json').write_text(json.dumps(config))

        with patch('cja_sdr_generator.get_profile_path', return_value=profile_dir):
            result = show_profile('test-profile')
            assert result is True
            captured = capsys.readouterr()
            assert 'test-profile' in captured.out
            assert 'test@AdobeOrg' in captured.out
            # Secret should be masked
            assert 'test_secret_12345678' not in captured.out

    def test_show_nonexistent_profile(self, tmp_path, capsys):
        """Test showing a nonexistent profile"""
        nonexistent_path = tmp_path / 'orgs' / 'nonexistent'

        with patch('cja_sdr_generator.get_profile_path', return_value=nonexistent_path):
            result = show_profile('nonexistent')
            assert result is False
            captured = capsys.readouterr()
            assert 'Error' in captured.out


class TestProfileExceptions:
    """Test profile exception classes"""

    def test_profile_error_with_name(self):
        """Test ProfileError includes profile name"""
        error = ProfileError('Test error', profile_name='test-profile')
        assert error.profile_name == 'test-profile'

    def test_profile_not_found_error(self):
        """Test ProfileNotFoundError is a ProfileError"""
        error = ProfileNotFoundError('Not found', profile_name='missing')
        assert isinstance(error, ProfileError)

    def test_profile_config_error(self):
        """Test ProfileConfigError is a ProfileError"""
        error = ProfileConfigError('Invalid config', profile_name='bad')
        assert isinstance(error, ProfileError)
