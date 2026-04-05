"""
Google Drive integration service for accessing files from user profiles.
"""

import io
import asyncio
from typing import Optional, List
from datetime import datetime

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import httpx

from core.config import settings


class GoogleDriveService:
    """Service for interacting with Google Drive API."""

    def __init__(self, access_token: str, refresh_token: Optional[str] = None):
        """
        Initialize Google Drive service with OAuth tokens.
        
        Args:
            access_token: Google OAuth access token
            refresh_token: Google OAuth refresh token (for token refresh)
        """
        self.access_token = access_token
        self.refresh_token = refresh_token
        self._service = None

    @property
    def service(self):
        """Lazy load Google Drive service."""
        if self._service is None:
            credentials = Credentials(
                token=self.access_token,
                refresh_token=self.refresh_token,
                token_uri="https://oauth2.googleapis.com/token",
                client_id=settings.google_drive_client_id,
                client_secret=settings.google_drive_client_secret,
            )
            self._service = build("drive", "v3", credentials=credentials)
        return self._service

    async def list_files_in_folder(
        self,
        folder_id: str,
        file_types: Optional[List[str]] = None,
    ) -> List[dict]:
        """
        List files in a Google Drive folder.
        
        Args:
            folder_id: Google Drive folder ID
            file_types: Optional list of file types to filter (e.g., ['.csv', '.xlsx'])
        
        Returns:
            List of file metadata dicts
        """
        try:
            query = f"'{folder_id}' in parents and trashed=false"
            
            results = self.service.files().list(
                q=query,
                spaces="drive",
                fields="files(id, name, mimeType, modifiedTime, size)",
                pageSize=100,
            ).execute()
            
            files = results.get("files", [])
            
            # Filter by file type if specified
            if file_types:
                files = [
                    f for f in files
                    if any(f["name"].lower().endswith(ft) for ft in file_types)
                ]
            
            return files
        except HttpError as error:
            print(f"An error occurred: {error}")
            return []

    async def download_file(self, file_id: str, file_name: str) -> Optional[bytes]:
        """
        Download a file from Google Drive.
        
        Args:
            file_id: Google Drive file ID
            file_name: File name (for context)
        
        Returns:
            File contents as bytes, or None if error
        """
        try:
            file = self.service.files().get_media(fileId=file_id)
            file_content = io.BytesIO()
            
            from googleapiclient.http import MediaIoBaseDownload
            downloader = MediaIoBaseDownload(file_content, file)
            
            done = False
            while not done:
                status, done = downloader.next_chunk()
            
            return file_content.getvalue()
        except HttpError as error:
            print(f"An error occurred downloading {file_name}: {error}")
            return None

    async def get_folder_metadata(self, folder_id: str) -> Optional[dict]:
        """
        Get metadata about a folder.
        
        Args:
            folder_id: Google Drive folder ID
        
        Returns:
            Folder metadata dict, or None if not found
        """
        try:
            folder = self.service.files().get(
                fileId=folder_id,
                fields="id, name, mimeType, modifiedTime",
            ).execute()
            return folder
        except HttpError as error:
            print(f"An error occurred: {error}")
            return None


class GoogleDriveOAuthFlow:
    """Handle OAuth flow for Google Drive authorization."""

    @staticmethod
    def get_authorization_url(profile_id: str) -> tuple[str, str]:
        """
        Get Google OAuth authorization URL and state.
        
        Args:
            profile_id: Profile ID to associate with this OAuth flow
            
        Returns:
            Tuple of (authorization_url, state)
        """
        scopes = [
            "https://www.googleapis.com/auth/drive.readonly",
        ]
        
        flow = Flow.from_client_config(
            {
                "web": {
                    "client_id": settings.google_drive_client_id,
                    "client_secret": settings.google_drive_client_secret,
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                    "redirect_uris": [settings.google_drive_redirect_uri],
                }
            },
            scopes=scopes,
            redirect_uri=settings.google_drive_redirect_uri,
        )
        
        # Generate a unique state for this OAuth flow and preserve the PKCE verifier
        import secrets
        authorization_url, _ = flow.authorization_url(
            access_type="offline",
            include_granted_scopes="true",
            prompt="consent",
        )
        code_verifier = flow.code_verifier
        state = f"{profile_id}:{code_verifier}:{secrets.token_urlsafe(32)}"
        
        authorization_url, _ = flow.authorization_url(
            access_type="offline",
            include_granted_scopes="true",
            prompt="consent",
            state=state,
        )
        
        return authorization_url, state

    @staticmethod
    async def exchange_code_for_tokens(code: str, state: str) -> dict:
        """
        Exchange authorization code for access and refresh tokens.
        
        Args:
            code: Authorization code from OAuth callback
            state: State parameter for security
        
        Returns:
            Dict with 'access_token' and 'refresh_token'
        """
        scopes = [
            "https://www.googleapis.com/auth/drive.readonly",
        ]
        
        flow = Flow.from_client_config(
            {
                "web": {
                    "client_id": settings.google_drive_client_id,
                    "client_secret": settings.google_drive_client_secret,
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                    "redirect_uris": [settings.google_drive_redirect_uri],
                }
            },
            scopes=scopes,
            state=state,
            redirect_uri=settings.google_drive_redirect_uri,
        )

        try:
            _, code_verifier, _ = state.split(':', 2)
        except ValueError:
            raise ValueError("Invalid OAuth state format")

        flow.code_verifier = code_verifier
        flow.fetch_token(code=code)
        credentials = flow.credentials
        
        return {
            "access_token": credentials.token,
            "refresh_token": credentials.refresh_token,
        }

    @staticmethod
    def refresh_access_token(refresh_token: str) -> Optional[str]:
        """
        Refresh an access token using refresh token.
        
        Args:
            refresh_token: The refresh token
        
        Returns:
            New access token, or None if error
        """
        try:
            credentials = Credentials(
                token=None,
                refresh_token=refresh_token,
                token_uri="https://oauth2.googleapis.com/token",
                client_id=settings.google_drive_client_id,
                client_secret=settings.google_drive_client_secret,
            )
            credentials.refresh(Request())
            return credentials.token
        except Exception as e:
            print(f"Error refreshing token: {e}")
            return None
