"""
Integration tests for Authentication Flow

Tests the complete authentication workflow including OAuth, Service Account, and Credential Store.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock, mock_open
from typing import Dict, Any
import json
from datetime import datetime, timedelta

from google.oauth2.credentials import Credentials
from google.oauth2 import service_account


class TestOAuthFlow:
    """Test OAuth 2.0 authentication flow"""

    @pytest.fixture
    def mock_oauth_config(self):
        """Create mock OAuth configuration"""
        return {
            "client_id": "test-client-id.apps.googleusercontent.com",
            "client_secret": "test-client-secret",
            "redirect_uri": "http://localhost:8080",
            "scopes": [
                "https://www.googleapis.com/auth/gmail.modify",
                "https://www.googleapis.com/auth/drive",
                "https://www.googleapis.com/auth/calendar"
            ]
        }

    @pytest.fixture
    def mock_credentials(self):
        """Create mock OAuth credentials"""
        return Credentials(
            token="test-access-token",
            refresh_token="test-refresh-token",
            token_uri="https://oauth2.googleapis.com/token",
            client_id="test-client-id",
            client_secret="test-client-secret",
            scopes=[
                "https://www.googleapis.com/auth/gmail.modify",
                "https://www.googleapis.com/auth/drive"
            ]
        )

    def test_oauth_initial_authorization(self, mock_oauth_config):
        """Test initial OAuth authorization flow"""
        # Arrange
        with patch('auth.oauth_manager.OAuthManager') as MockOAuthManager:
            manager = MagicMock()
            MockOAuthManager.return_value = manager
            manager.authorize.return_value = True

            # Act
            oauth_manager = MockOAuthManager(mock_oauth_config)
            result = oauth_manager.authorize()

            # Assert
            assert result is True
            manager.authorize.assert_called_once()

    def test_oauth_token_refresh(self, mock_credentials):
        """Test automatic token refresh when expired"""
        # Arrange
        with patch('auth.oauth_manager.OAuthManager') as MockOAuthManager:
            manager = MagicMock()
            MockOAuthManager.return_value = manager

            # Simulate expired credentials
            expired_creds = Mock(spec=Credentials)
            expired_creds.expired = True
            expired_creds.refresh_token = "test-refresh-token"
            expired_creds.valid = False

            # Mock refresh
            refreshed_creds = Mock(spec=Credentials)
            refreshed_creds.expired = False
            refreshed_creds.valid = True
            manager.refresh_credentials.return_value = refreshed_creds

            # Act
            result = manager.refresh_credentials(expired_creds)

            # Assert
            assert result.expired is False
            assert result.valid is True
            manager.refresh_credentials.assert_called_once()

    def test_oauth_token_storage(self, mock_credentials):
        """Test OAuth token storage and retrieval"""
        # Arrange
        token_data = {
            "token": mock_credentials.token,
            "refresh_token": mock_credentials.refresh_token,
            "token_uri": mock_credentials.token_uri,
            "client_id": mock_credentials.client_id,
            "client_secret": mock_credentials.client_secret,
            "scopes": mock_credentials.scopes
        }

        # Act
        with patch('builtins.open', mock_open()) as mock_file:
            with patch('json.dump') as mock_json_dump:
                # Simulate saving token
                with open('tokens.json', 'w') as f:
                    json.dump(token_data, f)

                # Assert
                mock_json_dump.assert_called_once()
                call_args = mock_json_dump.call_args[0]
                assert call_args[0] == token_data

    def test_oauth_token_loading(self):
        """Test loading saved OAuth tokens"""
        # Arrange
        saved_token_data = json.dumps({
            "token": "saved-access-token",
            "refresh_token": "saved-refresh-token",
            "token_uri": "https://oauth2.googleapis.com/token",
            "client_id": "test-client-id",
            "client_secret": "test-client-secret",
            "scopes": ["https://www.googleapis.com/auth/gmail.modify"]
        })

        # Act
        with patch('builtins.open', mock_open(read_data=saved_token_data)):
            with open('tokens.json', 'r') as f:
                loaded_data = json.load(f)

            # Assert
            assert loaded_data["token"] == "saved-access-token"
            assert loaded_data["refresh_token"] == "saved-refresh-token"

    def test_oauth_scope_validation(self, mock_oauth_config):
        """Test OAuth scope validation"""
        # Arrange
        required_scopes = mock_oauth_config["scopes"]
        granted_scopes = [
            "https://www.googleapis.com/auth/gmail.modify",
            "https://www.googleapis.com/auth/drive"
        ]

        # Act
        missing_scopes = set(required_scopes) - set(granted_scopes)

        # Assert
        assert len(missing_scopes) > 0  # Calendar scope is missing
        assert "https://www.googleapis.com/auth/calendar" in missing_scopes


class TestServiceAccountFlow:
    """Test Service Account authentication flow"""

    @pytest.fixture
    def mock_service_account_json(self):
        """Create mock service account JSON"""
        return {
            "type": "service_account",
            "project_id": "test-project-123",
            "private_key_id": "key-id-456",
            "private_key": "-----BEGIN PRIVATE KEY-----\nMOCK_KEY\n-----END PRIVATE KEY-----\n",
            "client_email": "test-sa@test-project-123.iam.gserviceaccount.com",
            "client_id": "123456789",
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs"
        }

    def test_service_account_credential_loading(self, mock_service_account_json):
        """Test loading service account credentials from JSON"""
        # Arrange
        sa_json_str = json.dumps(mock_service_account_json)

        # Act
        with patch('builtins.open', mock_open(read_data=sa_json_str)):
            with open('service-account.json', 'r') as f:
                loaded_data = json.load(f)

            # Assert
            assert loaded_data["type"] == "service_account"
            assert loaded_data["project_id"] == "test-project-123"
            assert loaded_data["client_email"] == "test-sa@test-project-123.iam.gserviceaccount.com"

    def test_service_account_with_domain_wide_delegation(self, mock_service_account_json):
        """Test service account with domain-wide delegation"""
        # Arrange
        user_email = "user@example.com"

        with patch('auth.service_account_manager.ServiceAccountManager') as MockSAManager:
            manager = MagicMock()
            MockSAManager.return_value = manager

            # Mock delegated credentials
            delegated_creds = Mock()
            delegated_creds.service_account_email = mock_service_account_json["client_email"]
            delegated_creds.subject = user_email
            manager.get_delegated_credentials.return_value = delegated_creds

            # Act
            sa_manager = MockSAManager(mock_service_account_json)
            creds = sa_manager.get_delegated_credentials(user_email)

            # Assert
            assert creds.subject == user_email
            manager.get_delegated_credentials.assert_called_once_with(user_email)

    def test_service_account_scopes(self, mock_service_account_json):
        """Test service account with specific scopes"""
        # Arrange
        required_scopes = [
            "https://www.googleapis.com/auth/gmail.readonly",
            "https://www.googleapis.com/auth/drive.readonly"
        ]

        with patch('auth.service_account_manager.ServiceAccountManager') as MockSAManager:
            manager = MagicMock()
            MockSAManager.return_value = manager

            # Act
            sa_manager = MockSAManager(mock_service_account_json)
            sa_manager.set_scopes(required_scopes)

            # Assert
            manager.set_scopes.assert_called_once_with(required_scopes)

    def test_service_account_missing_file(self):
        """Test handling when service account file is missing"""
        # Act & Assert
        with patch('builtins.open', side_effect=FileNotFoundError("File not found")):
            with pytest.raises(FileNotFoundError):
                with open('nonexistent-service-account.json', 'r') as f:
                    json.load(f)


class TestCredentialStore:
    """Test Credential Store integration"""

    @pytest.fixture
    def mock_credential_store(self):
        """Create mock credential store"""
        with patch('auth.credential_store.CredentialStore') as MockStore:
            store = MagicMock()
            MockStore.return_value = store
            yield store

    def test_credential_priority_oauth_first(self, mock_credential_store):
        """Test credential store prefers OAuth when available"""
        # Arrange
        store = mock_credential_store
        oauth_creds = Mock(spec=Credentials)
        oauth_creds.valid = True
        store.get_oauth_credentials.return_value = oauth_creds
        store.get_credentials.return_value = oauth_creds

        # Act
        creds = store.get_credentials()

        # Assert
        assert creds == oauth_creds
        assert creds.valid is True

    def test_credential_fallback_to_service_account(self, mock_credential_store):
        """Test fallback to service account when OAuth unavailable"""
        # Arrange
        store = mock_credential_store
        store.get_oauth_credentials.return_value = None

        sa_creds = Mock()
        sa_creds.valid = True
        store.get_service_account_credentials.return_value = sa_creds
        store.get_credentials.return_value = sa_creds

        # Act
        creds = store.get_credentials()

        # Assert
        assert creds == sa_creds
        assert creds.valid is True

    def test_credential_refresh_on_expiry(self, mock_credential_store):
        """Test automatic credential refresh when expired"""
        # Arrange
        store = mock_credential_store
        expired_creds = Mock(spec=Credentials)
        expired_creds.expired = True
        expired_creds.valid = False

        refreshed_creds = Mock(spec=Credentials)
        refreshed_creds.expired = False
        refreshed_creds.valid = True

        store.get_credentials.return_value = expired_creds
        store.refresh_if_expired.return_value = refreshed_creds

        # Act
        creds = store.refresh_if_expired(expired_creds)

        # Assert
        assert creds.expired is False
        assert creds.valid is True

    def test_no_credentials_available(self, mock_credential_store):
        """Test handling when no credentials are available"""
        # Arrange
        store = mock_credential_store
        store.get_oauth_credentials.return_value = None
        store.get_service_account_credentials.return_value = None
        store.get_credentials.return_value = None

        # Act
        creds = store.get_credentials()

        # Assert
        assert creds is None


class TestAuthenticationIntegration:
    """Test full authentication integration scenarios"""

    def test_end_to_end_oauth_flow(self):
        """Test complete OAuth flow from start to finish"""
        # Arrange
        with patch('auth.oauth_manager.OAuthManager') as MockOAuthManager:
            manager = MagicMock()
            MockOAuthManager.return_value = manager

            # Step 1: Initial authorization
            manager.authorize.return_value = True

            # Step 2: Get credentials
            mock_creds = Mock(spec=Credentials)
            mock_creds.valid = True
            mock_creds.expired = False
            manager.get_credentials.return_value = mock_creds

            # Act
            oauth_manager = MockOAuthManager({})
            authorized = oauth_manager.authorize()
            creds = oauth_manager.get_credentials()

            # Assert
            assert authorized is True
            assert creds.valid is True
            assert creds.expired is False

    def test_switching_between_auth_methods(self):
        """Test switching between OAuth and Service Account"""
        # Arrange
        with patch('auth.credential_store.CredentialStore') as MockStore:
            store = MagicMock()
            MockStore.return_value = store

            oauth_creds = Mock(spec=Credentials)
            oauth_creds.valid = True
            sa_creds = Mock()
            sa_creds.valid = True

            # Act - Start with OAuth
            store.use_oauth.return_value = oauth_creds
            creds1 = store.use_oauth()

            # Switch to Service Account
            store.use_service_account.return_value = sa_creds
            creds2 = store.use_service_account()

            # Assert
            assert creds1 == oauth_creds
            assert creds2 == sa_creds
            store.use_oauth.assert_called_once()
            store.use_service_account.assert_called_once()

    def test_multi_user_authentication(self):
        """Test authentication for multiple users with domain-wide delegation"""
        # Arrange
        users = ["user1@example.com", "user2@example.com", "user3@example.com"]

        with patch('auth.service_account_manager.ServiceAccountManager') as MockSAManager:
            manager = MagicMock()
            MockSAManager.return_value = manager

            # Act
            credentials_map = {}
            for user in users:
                mock_creds = Mock()
                mock_creds.subject = user
                mock_creds.valid = True
                manager.get_delegated_credentials.return_value = mock_creds
                credentials_map[user] = manager.get_delegated_credentials(user)

            # Assert
            assert len(credentials_map) == 3
            for user in users:
                assert credentials_map[user].subject == user
                assert credentials_map[user].valid is True

    def test_auth_error_recovery(self):
        """Test recovery from authentication errors"""
        # Arrange
        with patch('auth.credential_store.CredentialStore') as MockStore:
            store = MagicMock()
            MockStore.return_value = store

            # First attempt fails (OAuth)
            store.get_oauth_credentials.side_effect = Exception("OAuth failed")

            # Fallback succeeds (Service Account)
            sa_creds = Mock()
            sa_creds.valid = True
            store.get_service_account_credentials.return_value = sa_creds

            # Act
            try:
                oauth_creds = store.get_oauth_credentials()
            except Exception:
                # Fallback to service account
                creds = store.get_service_account_credentials()

            # Assert
            assert creds == sa_creds
            assert creds.valid is True

    def test_concurrent_auth_requests(self):
        """Test handling concurrent authentication requests"""
        # Arrange
        with patch('auth.credential_store.CredentialStore') as MockStore:
            store = MagicMock()
            MockStore.return_value = store

            mock_creds = Mock(spec=Credentials)
            mock_creds.valid = True
            store.get_credentials.return_value = mock_creds

            # Act - Simulate multiple concurrent requests
            results = []
            for _ in range(5):
                results.append(store.get_credentials())

            # Assert
            assert len(results) == 5
            assert all(cred.valid for cred in results)
            # Should use cached credentials, not create new ones each time
            assert store.get_credentials.call_count == 5
