"""
Authentication module for Robinhood login with MFA support
"""
import asyncio
import secrets
import hashlib
import json
import logging
from typing import Optional, Dict
from datetime import datetime, timedelta
import robin_stocks.robinhood as rh
from fastapi import HTTPException
import pickle
import base64

logger = logging.getLogger(__name__)


class AuthManager:
    """Manages Robinhood authentication and sessions"""

    def __init__(self):
        self.sessions: Dict[str, Dict] = {}  # session_token -> session_data
        self.mfa_challenges: Dict[str, Dict] = {}  # challenge_id -> challenge_data
        self.mfa_login_attempted: Dict[str, bool] = {}  # challenge_id -> whether we've tried login

    def create_session_token(self) -> str:
        """Generate a secure session token"""
        return secrets.token_urlsafe(32)

    def create_challenge_id(self) -> str:
        """Generate a challenge ID for MFA flow"""
        return secrets.token_urlsafe(16)

    async def login(self, username: str, password: str) -> Dict:
        """
        Attempt to login to Robinhood.
        Returns either:
        - {"success": True, "token": "session_token"} on success
        - {"requires_mfa": True, "challenge_id": "..."} if MFA needed

        NOTE: We assume MFA is always required for better UX.
        The actual login attempt happens during MFA polling.
        """
        try:
            # Create challenge ID immediately without attempting login
            # This ensures the MFA spinner shows right away
            challenge_id = self.create_challenge_id()

            # Store challenge data for polling
            self.mfa_challenges[challenge_id] = {
                'username': username,
                'password': password,
                'created_at': datetime.utcnow(),
                'expires_at': datetime.utcnow() + timedelta(minutes=5)
            }

            logger.info(f"Login request received for {username}, created challenge {challenge_id}")

            # Always return requires_mfa to show spinner immediately
            # The first MFA poll will attempt the actual login
            return {
                'requires_mfa': True,
                'challenge_id': challenge_id
            }

        except Exception as e:
            raise HTTPException(status_code=401, detail=f"Login failed: {str(e)}")

    def _robinhood_login(self, username: str, password: str) -> Dict:
        """
        Blocking call to Robinhood login.
        Must be run in thread pool via asyncio.to_thread()
        """
        try:
            # Attempt login
            login_result = rh.login(
                username=username,
                password=password,
                store_session=False  # Don't persist to disk
            )

            # Check if login was successful
            if login_result:
                # Get device token from pickle if available
                device_token = None
                try:
                    # Try to get the authentication token
                    device_token = rh.authentication.get_authentication_token()
                except:
                    pass

                return {
                    'success': True,
                    'device_token': device_token
                }

            # If we get here, check if MFA is required
            # Robinhood library handles MFA internally, but we need to detect it
            return {'requires_mfa': True}

        except Exception as e:
            error_str = str(e).lower()

            # Check if it's an MFA challenge
            if 'challenge' in error_str or 'mfa' in error_str or 'verification' in error_str:
                return {'requires_mfa': True}

            # Other error
            raise Exception(f"Login error: {str(e)}")

    async def complete_mfa(self, challenge_id: str) -> Dict:
        """
        Complete MFA login after user approves in Robinhood app.
        Polls Robinhood to check if MFA was approved.
        """
        # Get challenge data
        if challenge_id not in self.mfa_challenges:
            raise HTTPException(status_code=404, detail="Challenge not found or expired")

        challenge = self.mfa_challenges[challenge_id]

        # Check if expired
        if datetime.utcnow() > challenge['expires_at']:
            del self.mfa_challenges[challenge_id]
            raise HTTPException(status_code=408, detail="MFA challenge expired")

        try:
            # Only attempt login once to avoid triggering multiple MFA challenges
            should_attempt_login = challenge_id not in self.mfa_login_attempted

            if should_attempt_login:
                logger.info(f"First MFA check - attempting login for challenge {challenge_id}")
                self.mfa_login_attempted[challenge_id] = True

            # Poll Robinhood to check if MFA was approved
            # This is a blocking operation, so run in thread pool
            result = await asyncio.to_thread(
                self._check_mfa_approval,
                challenge['username'],
                challenge['password'],
                should_attempt_login
            )

            logger.debug(f"MFA check result: {result}")

            if result.get('success'):
                # MFA approved - create session
                session_token = self.create_session_token()

                self.sessions[session_token] = {
                    'username': challenge['username'],
                    'device_token': result.get('device_token'),
                    'created_at': datetime.utcnow(),
                    'expires_at': datetime.utcnow() + timedelta(hours=24),
                    'logged_in': True
                }

                # Clean up challenge (safe deletion to avoid race condition)
                self.mfa_challenges.pop(challenge_id, None)
                self.mfa_login_attempted.pop(challenge_id, None)

                logger.info(f"MFA success! Created session token: {session_token[:10]}...")

                return {
                    'success': True,
                    'token': session_token
                }
            else:
                # MFA not yet approved
                return {
                    'pending': True,
                    'message': 'Waiting for MFA approval'
                }

        except HTTPException:
            # Re-raise HTTPExceptions as-is
            raise
        except Exception as e:
            # Log unexpected errors but don't crash
            logger.error(f"Unexpected error in complete_mfa: {str(e)}")
            logger.exception("Full traceback:")
            # Return pending instead of erroring
            return {
                'pending': True,
                'message': 'Still checking MFA status'
            }

    def _check_mfa_approval(self, username: str, password: str, should_attempt_login: bool) -> Dict:
        """
        Check if MFA was approved.
        This is a blocking call.

        Args:
            username: Robinhood username
            password: Robinhood password
            should_attempt_login: If False, only check existing session without triggering new login
        """
        try:
            # First, check if we're already logged in by trying to get account info
            try:
                # If we can get profile info, we're logged in
                profile = rh.profiles.load_account_profile()
                if profile and isinstance(profile, dict):
                    logger.info("Already logged in, session is active")
                    current_token = None
                    try:
                        current_token = rh.authentication.get_authentication_token()
                    except:
                        pass
                    return {
                        'success': True,
                        'device_token': current_token
                    }
            except Exception as check_error:
                logger.debug(f"Not logged in yet: {str(check_error)[:100]}")

            # Only attempt login on first poll to avoid triggering multiple MFA challenges
            if not should_attempt_login:
                logger.debug("Skipping login attempt (already initiated), checking if approved...")
                # Still check if we can get profile even without new login attempt
                try:
                    profile = rh.profiles.load_account_profile()
                    if profile:
                        logger.info("MFA approved! Session is now active.")
                        return {
                            'success': True,
                            'device_token': rh.authentication.get_authentication_token()
                        }
                except:
                    pass
                return {'pending': True}

            # First poll - attempt login which will trigger MFA challenge
            logger.info("First poll - attempting login to initiate MFA...")
            login_result = rh.login(
                username=username,
                password=password,
                store_session=False
            )

            # Check if we successfully logged in
            try:
                profile = rh.profiles.load_account_profile()
                if profile:
                    device_token = None
                    try:
                        device_token = rh.authentication.get_authentication_token()
                    except:
                        pass

                    logger.info("Login successful! MFA was approved.")
                    return {
                        'success': True,
                        'device_token': device_token
                    }
            except:
                pass

            return {'pending': True}

        except Exception as e:
            error_str = str(e).lower()

            # Still waiting for MFA
            if 'challenge' in error_str or 'mfa' in error_str or 'verification' in error_str:
                logger.info("MFA challenge initiated, waiting for approval...")
                return {'pending': True}

            # Log the error but return pending instead of raising
            logger.warning(f"MFA check error (returning pending): {str(e)}")
            return {'pending': True}

    def get_session(self, token: str) -> Optional[Dict]:
        """Get session data by token"""
        session = self.sessions.get(token)

        if not session:
            return None

        # Check if expired
        if datetime.utcnow() > session['expires_at']:
            del self.sessions[token]
            return None

        return session

    def logout(self, token: str) -> bool:
        """Logout and invalidate session"""
        if token in self.sessions:
            # Logout from Robinhood
            try:
                rh.logout()
            except:
                pass

            del self.sessions[token]
            return True
        return False

    def is_authenticated(self, token: Optional[str]) -> bool:
        """Check if session token is valid"""
        if not token:
            return False

        session = self.get_session(token)
        return session is not None and session.get('logged_in', False)

    async def restore_session(self, token: str) -> bool:
        """
        Restore Robinhood login from session.
        Call this before making any Robinhood API calls.
        """
        session = self.get_session(token)

        if not session:
            return False

        try:
            # Re-login with stored credentials
            # In production, you'd use the device token to avoid re-login
            # For now, we rely on the session being valid
            session['logged_in'] = True
            return True

        except Exception as e:
            logger.error(f"Failed to restore session: {e}")
            return False


# Global auth manager instance
auth_manager = AuthManager()
