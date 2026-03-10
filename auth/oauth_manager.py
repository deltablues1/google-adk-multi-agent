"""
OAuth 2.0 Manager za Google Workspace API
Implementira OAuth 2.1 flow s token refresh mehanizmom
"""

import os
import json
from typing import Optional, Dict, Any
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from google.auth.transport.requests import Request
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


class OAuthManager:
    """Upravlja OAuth 2.0 autentifikacijom za Google Workspace API"""

    # OAuth 2.0 scopes za Google Workspace
    SCOPES = [
        # Gmail
        'https://www.googleapis.com/auth/gmail.readonly',
        'https://www.googleapis.com/auth/gmail.send',
        'https://www.googleapis.com/auth/gmail.modify',
        'https://www.googleapis.com/auth/gmail.compose',
        # Drive
        'https://www.googleapis.com/auth/drive',
        'https://www.googleapis.com/auth/drive.file',
        # Docs
        'https://www.googleapis.com/auth/documents',
        # Sheets
        'https://www.googleapis.com/auth/spreadsheets',
        # Calendar
        'https://www.googleapis.com/auth/calendar',
        'https://www.googleapis.com/auth/calendar.events',
        # Contacts
        'https://www.googleapis.com/auth/contacts',
        'https://www.googleapis.com/auth/contacts.readonly',
        # Tasks
        'https://www.googleapis.com/auth/tasks',
        # Firestore (Datastore)
        'https://www.googleapis.com/auth/datastore',
        # Google Ads
        'https://www.googleapis.com/auth/adwords',
        # YouTube
        'https://www.googleapis.com/auth/youtube.upload',
        # Google Cloud Platform (Vertex AI)
        'https://www.googleapis.com/auth/cloud-platform',
    ]

    def __init__(
        self,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
        redirect_uri: Optional[str] = None,
        token_storage_path: Optional[str] = None
    ):
        """
        Inicijalizacija OAuth Manager-a

        Args:
            client_id: OAuth 2.0 Client ID
            client_secret: OAuth 2.0 Client Secret
            redirect_uri: OAuth 2.0 Redirect URI
            token_storage_path: Putanja za pohranu tokena
        """
        self.client_id = client_id or os.getenv('GOOGLE_OAUTH_CLIENT_ID')
        self.client_secret = client_secret or os.getenv('GOOGLE_OAUTH_CLIENT_SECRET')
        self.redirect_uri = redirect_uri or os.getenv('GOOGLE_OAUTH_REDIRECT_URI', 'http://localhost:8080/oauth2callback')

        # Token storage
        self.token_storage_path = token_storage_path or os.path.join(
            Path.home(), '.google_workspace_adk', 'tokens.json'
        )
        os.makedirs(os.path.dirname(self.token_storage_path), exist_ok=True)

        self._credentials: Optional[Credentials] = None

    def get_authorization_url(self) -> str:
        """
        Generira OAuth 2.0 authorization URL

        Returns:
            Authorization URL za korisničku autorizaciju
        """
        client_config = {
            'web': {
                'client_id': self.client_id,
                'client_secret': self.client_secret,
                'redirect_uris': [self.redirect_uri],
                'auth_uri': 'https://accounts.google.com/o/oauth2/auth',
                'token_uri': 'https://oauth2.googleapis.com/token',
            }
        }

        flow = Flow.from_client_config(
            client_config,
            scopes=self.SCOPES,
            redirect_uri=self.redirect_uri
        )

        auth_url, _ = flow.authorization_url(
            access_type='offline',
            include_granted_scopes='true',
            prompt='consent'
        )

        return auth_url

    def exchange_code_for_token(self, authorization_code: str) -> Credentials:
        """
        Zamjenjuje authorization code za access token

        Args:
            authorization_code: Authorization code iz OAuth callback-a

        Returns:
            Google OAuth2 Credentials objekt
        """
        client_config = {
            'web': {
                'client_id': self.client_id,
                'client_secret': self.client_secret,
                'redirect_uris': [self.redirect_uri],
                'auth_uri': 'https://accounts.google.com/o/oauth2/auth',
                'token_uri': 'https://oauth2.googleapis.com/token',
            }
        }

        flow = Flow.from_client_config(
            client_config,
            scopes=self.SCOPES,
            redirect_uri=self.redirect_uri
        )

        flow.fetch_token(code=authorization_code)
        self._credentials = flow.credentials

        # Spremi token
        self._save_token()

        logger.info("Successfully exchanged authorization code for token")
        return self._credentials

    def get_credentials(self) -> Optional[Credentials]:
        """
        Dohvaća važeće OAuth2 credentials
        Automatski osvježava token ako je istekao

        Returns:
            Google OAuth2 Credentials objekt ili None ako nisu dostupni
        """
        if self._credentials and self._credentials.valid:
            return self._credentials

        # Učitaj spremljeni token
        self._load_token()

        if self._credentials:
            # Provjeri je li token istekao i osvježi ga
            if self._credentials.expired and self._credentials.refresh_token:
                try:
                    self._credentials.refresh(Request())
                    self._save_token()
                    logger.info("Successfully refreshed OAuth token")
                except Exception as e:
                    logger.error(f"Failed to refresh token: {e}")
                    self._credentials = None

        return self._credentials

    def _save_token(self) -> None:
        """Sprema OAuth token u datoteku"""
        if not self._credentials:
            return

        token_data = {
            'token': self._credentials.token,
            'refresh_token': self._credentials.refresh_token,
            'token_uri': self._credentials.token_uri,
            'client_id': self._credentials.client_id,
            'client_secret': self._credentials.client_secret,
            'scopes': self._credentials.scopes,
        }

        try:
            with open(self.token_storage_path, 'w') as f:
                json.dump(token_data, f)
            logger.debug(f"Token saved to {self.token_storage_path}")
        except Exception as e:
            logger.error(f"Failed to save token: {e}")

    def _load_token(self) -> None:
        """Učitava OAuth token iz datoteke"""
        if not os.path.exists(self.token_storage_path):
            return

        try:
            with open(self.token_storage_path, 'r') as f:
                token_data = json.load(f)

            self._credentials = Credentials(
                token=token_data.get('token'),
                refresh_token=token_data.get('refresh_token'),
                token_uri=token_data.get('token_uri'),
                client_id=token_data.get('client_id'),
                client_secret=token_data.get('client_secret'),
                scopes=token_data.get('scopes'),
            )
            logger.debug(f"Token loaded from {self.token_storage_path}")
        except Exception as e:
            logger.error(f"Failed to load token: {e}")

    def revoke_token(self) -> bool:
        """
        Opoziva OAuth token

        Returns:
            True ako je token uspješno opozvan
        """
        credentials = self.get_credentials()
        if not credentials:
            return False

        try:
            import requests
            revoke = requests.post(
                'https://oauth2.googleapis.com/revoke',
                params={'token': credentials.token},
                headers={'content-type': 'application/x-www-form-urlencoded'}
            )

            if revoke.status_code == 200:
                # Obriši spremljeni token
                if os.path.exists(self.token_storage_path):
                    os.remove(self.token_storage_path)
                self._credentials = None
                logger.info("Token successfully revoked")
                return True
            else:
                logger.error(f"Failed to revoke token: {revoke.status_code}")
                return False
        except Exception as e:
            logger.error(f"Error revoking token: {e}")
            return False

    def is_authenticated(self) -> bool:
        """
        Provjerava je li korisnik autentificiran

        Returns:
            True ako postoje važeći credentials
        """
        return self.get_credentials() is not None


# Singleton instance
_oauth_manager_instance: Optional[OAuthManager] = None


def get_oauth_manager() -> OAuthManager:
    """
    Dohvaća singleton instancu OAuthManager-a

    Returns:
        OAuthManager instance
    """
    global _oauth_manager_instance
    if _oauth_manager_instance is None:
        _oauth_manager_instance = OAuthManager()
    return _oauth_manager_instance
