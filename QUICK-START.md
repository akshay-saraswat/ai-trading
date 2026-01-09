# Quick Start Guide - Web-Based Authentication

## Overview

Your AI Trading Bot now uses web-based authentication instead of AWS Secrets Manager credentials. Users enter their Robinhood credentials directly through a login screen.

## What Changed

✅ **Added:**
- Login screen with username/password form
- MFA support with automatic polling
- Session management (24-hour expiry)
- Logout button in app header
- 4 new authentication API endpoints

❌ **Removed:**
- AWS Secrets Manager setup requirement
- CloudFormation credential parameters
- Environment variables for credentials

## Local Development

### 1. Install Dependencies

```bash
# Backend
cd backend
pip install -r requirements.txt

# Frontend
cd frontend
npm install
```

### 2. Start Backend

```bash
cd backend
python3 main.py
```

Server starts on `http://localhost:8000`

### 3. Start Frontend

```bash
cd frontend
npm start
```

App opens at `http://localhost:3000`

### 4. Test Login Flow

1. Navigate to `http://localhost:3000`
2. You'll see the login screen
3. Enter your Robinhood credentials
4. If MFA is enabled:
   - Spinner appears with instructions
   - Approve login in Robinhood app
   - Auto-redirects to chat page (~3-10 seconds)
5. If no MFA:
   - Immediate redirect to chat page

### 5. Test Session Persistence

- Reload the page → should stay logged in
- Open new tab → should stay logged in
- Click logout → should return to login screen

## AWS ECS Deployment

### Deploy to AWS

```bash
# Make script executable
chmod +x deploy-cloudformation.sh

# Deploy infrastructure + application
./deploy-cloudformation.sh
```

This command:
1. Creates VPC, ALB, ECS cluster, IAM roles
2. Builds Docker image for AMD64
3. Pushes to ECR
4. Deploys to ECS with zero-downtime

### Access Your Application

After deployment completes:
```bash
cd cloudformation
./manage-stack.sh outputs
```

Copy the ALB URL and open in browser. You'll see the login screen.

## Configuration

**Trading Settings** - Configure via **Settings page** (⚙️ tab) in the web interface:
- `MAX_POSITION_SIZE` - Maximum $ per trade (default: $1000)
- `SKIP_MARKET_SCHEDULE_CHECK` - Trade outside market hours for testing (default: false)

**Deployment Settings** - Optional environment variable for ECS:
```bash
export DESIRED_TASK_COUNT="1"                 # Number of ECS tasks (0-10)
```

### Session Expiry

Default: 24 hours

To change, edit [backend/auth.py](backend/auth.py):
```python
'expires_at': datetime.utcnow() + timedelta(hours=48)  # 48 hours
```

## API Endpoints

### POST /api/auth/login
Login with Robinhood credentials.

**Request:**
```json
{
  "username": "user@example.com",
  "password": "password"
}
```

**Response (Success):**
```json
{
  "success": true,
  "token": "session_token_here"
}
```

**Response (MFA Required):**
```json
{
  "requires_mfa": true,
  "challenge_id": "challenge_abc123"
}
```

### POST /api/auth/mfa/check
Poll for MFA approval (frontend calls every 3 seconds).

**Request:**
```json
{
  "challenge_id": "challenge_abc123"
}
```

**Response (Pending):**
```json
{
  "pending": true,
  "message": "Waiting for MFA approval"
}
```

**Response (Approved):**
```json
{
  "success": true,
  "token": "session_token_here"
}
```

### GET /api/auth/session
Check if session is valid.

**Headers:**
```
Authorization: Bearer {token}
```

**Response:**
```json
{
  "authenticated": true,
  "username": "user@example.com",
  "expires_at": "2024-01-09T12:00:00"
}
```

### POST /api/auth/logout
Logout and invalidate session.

**Headers:**
```
Authorization: Bearer {token}
```

**Response:**
```json
{
  "success": true
}
```

## Troubleshooting

### Login button disabled
**Cause:** Username or password field empty
**Fix:** Enter both fields

### "Login failed" error
**Causes:**
- Incorrect credentials
- Robinhood account locked
- Network error

**Fix:**
- Double-check credentials
- Login to Robinhood app to verify account works
- Check network connectivity

### MFA stuck on "Waiting for approval"
**Causes:**
- Haven't approved in Robinhood app yet
- MFA timeout (5 minutes)
- Network interruption

**Fix:**
- Open Robinhood app and approve
- Wait up to 10 seconds for polling
- If timeout, click "Cancel" and try again

### Session expires immediately after login
**Cause:** Clock sync issue or server restart

**Fix:**
- Check server time is correct
- Server restart clears in-memory sessions (expected)
- For production: Use Redis/DynamoDB for persistent sessions

## Testing Checklist

- [ ] Login with valid credentials (no MFA)
- [ ] Login with MFA enabled
- [ ] Session persists across page reloads
- [ ] Session persists across browser tabs
- [ ] Logout button clears session
- [ ] Expired token redirects to login
- [ ] Invalid credentials show error
- [ ] MFA timeout shows error
- [ ] All API endpoints return expected responses
- [ ] ECS deployment succeeds without credentials

## Security Notes

### ✅ Secure Features
- HTTPS transmission (when deployed)
- No plaintext storage
- 24-hour session expiry
- Secure random tokens
- MFA preserved
- Backend validation

### ⚠️ Production Enhancements
- Use Redis/DynamoDB for persistent sessions
- Add rate limiting on login endpoint
- Use httpOnly cookies instead of localStorage
- Add CSRF protection
- Implement proper error logging

## Documentation

- [AUTH-IMPLEMENTATION.md](AUTH-IMPLEMENTATION.md) - Complete implementation details
- [DEPLOYMENT.md](DEPLOYMENT.md) - AWS deployment guide
- [cloudformation/README.md](cloudformation/README.md) - CloudFormation reference

## Support

For issues or questions:
1. Check [AUTH-IMPLEMENTATION.md](AUTH-IMPLEMENTATION.md) troubleshooting section
2. Review CloudWatch logs: `cd cloudformation && ./manage-stack.sh logs`
3. Check stack events: `cd cloudformation && ./manage-stack.sh events`

---

**Ready to deploy! 🚀**

No AWS Secrets Manager setup required. Just deploy and login through the web interface.
