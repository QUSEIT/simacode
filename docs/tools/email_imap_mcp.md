# Email IMAP MCP Tool (HTTP/WebSocket)

A HTTP-based Model Context Protocol (MCP) tool for checking and retrieving emails using the IMAP protocol. This tool enables SimaCode to connect to email servers via HTTP/WebSocket transport, check for new emails, and retrieve email content including attachments.

## Features

- **HTTP/WebSocket Transport**: Modern web-based MCP protocol communication
- **IMAP Connection**: Secure connection to IMAP email servers with SSL/TLS support
- **Email Checking**: Search and filter emails with IMAP criteria
- **Email Retrieval**: Get full email content including headers, body, and attachments
- **Folder Management**: List and navigate email folders/mailboxes
- **Attachment Support**: Retrieve email attachments with base64 encoding
- **Multiple Providers**: Support for Gmail, Outlook, Yahoo, iCloud, and other IMAP servers
- **Health Monitoring**: Built-in health check endpoint for server status
- **Auto-reconnection**: Automatic IMAP connection management and recovery

## Configuration

The tool reads configuration from `.env.mcp` file in the project root. Copy `.env.mcp.sample` to `.env.mcp` and configure your email settings:

```bash
# Email IMAP Configuration
EMAIL_IMAP_SERVER=imap.gmail.com
EMAIL_IMAP_PORT_IMAP=993
EMAIL_USERNAME=your_email@gmail.com
EMAIL_PASSWORD=your_app_password_here
EMAIL_TIMEOUT=30

# Email IMAP MCP Server Configuration
EMAIL_IMAP_MCP_URL=ws://localhost:8081/mcp/ws
EMAIL_IMAP_HOST=0.0.0.0
EMAIL_IMAP_PORT=8081
```

### Supported Email Providers

| Provider | IMAP Server | Port | SSL |
|----------|-------------|------|-----|
| Gmail | imap.gmail.com | 993 | Yes |
| Outlook/Hotmail | outlook.office365.com | 993 | Yes |
| Yahoo | imap.mail.yahoo.com | 993 | Yes |
| iCloud | imap.mail.me.com | 993 | Yes |

### Gmail Setup

For Gmail, you need to use an App Password instead of your regular password:

1. Enable 2-Factor Authentication in your Google Account
2. Go to [App Passwords](https://myaccount.google.com/apppasswords)
3. Generate a new App Password for "Mail"
4. Use this App Password as `EMAIL_PASSWORD` in your configuration

## Usage

### Running the MCP Server

```bash
# Using environment configuration
python tools/mcp_email_imap_http_server.py

# Using command line arguments
python tools/mcp_email_imap_http_server.py \
    --host 0.0.0.0 \
    --port 8081 \
    --server imap.gmail.com \
    --imap-port 993 \
    --username your_email@gmail.com \
    --password your_app_password
```

The server will start on the configured host and port (default: `0.0.0.0:8081`) and provide:
- Health check endpoint: `http://localhost:8081/health`
- HTTP MCP endpoint: `http://localhost:8081/mcp` 
- WebSocket MCP endpoint: `ws://localhost:8081/mcp/ws`

### Available Tools

#### 1. list_folders

List available email folders/mailboxes.

**Parameters**: None

**Example Response**:
```json
{
  "folders": ["INBOX", "Sent", "Drafts", "Spam", "Trash"],
  "count": 5,
  "timestamp": "2024-01-15T10:30:00"
}
```

#### 2. check_emails

Check for emails in a folder with optional filtering.

**Parameters**:
- `folder` (string, optional): Email folder to check (default: "INBOX")
- `criteria` (string, optional): IMAP search criteria (default: "ALL")
- `limit` (integer, optional): Maximum number of emails to return (default: 10)

**IMAP Search Criteria Examples**:
- `"ALL"`: All emails
- `"UNSEEN"`: Unread emails
- `"FROM sender@example.com"`: Emails from specific sender
- `"SUBJECT 'Meeting'"`: Emails with "Meeting" in subject
- `"SINCE 01-Jan-2024"`: Emails since specific date

**Example Response**:
```json
{
  "folder": "INBOX",
  "folder_info": {
    "folder": "INBOX",
    "message_count": 150,
    "selected": true
  },
  "search_criteria": "UNSEEN",
  "emails": [
    {
      "uid": "1234",
      "subject": "Important Meeting Tomorrow",
      "sender": "boss@company.com",
      "date": "Mon, 15 Jan 2024 10:30:00 +0000",
      "size": 2048,
      "flags": ["\\Seen"],
      "has_attachments": false
    }
  ],
  "count": 1,
  "timestamp": "2024-01-15T10:30:00"
}
```

#### 3. get_email

Retrieve specific email by UID.

**Parameters**:
- `uid` (string, required): Email UID to retrieve
- `folder` (string, optional): Email folder containing the message (default: "INBOX")
- `include_attachments` (boolean, optional): Include attachment content in base64 format (default: false)

**Example Response**:
```json
{
  "uid": "1234",
  "subject": "Important Meeting Tomorrow",
  "sender": "Boss <boss@company.com>",
  "recipient": "me@company.com",
  "date": "Mon, 15 Jan 2024 10:30:00 +0000",
  "body_text": "Hi,\n\nDon't forget about the meeting tomorrow at 2 PM.\n\nBest regards,\nBoss",
  "body_html": "<p>Hi,</p><p>Don't forget about the meeting tomorrow at 2 PM.</p><p>Best regards,<br>Boss</p>",
  "headers": {
    "Message-ID": "<abc123@company.com>",
    "Content-Type": "multipart/alternative"
  },
  "size": 2048,
  "flags": ["\\Seen"],
  "attachments": [
    {
      "filename": "agenda.pdf",
      "content_type": "application/pdf",
      "size": 51200
    }
  ],
  "timestamp": "2024-01-15T10:30:00"
}
```

#### 4. get_recent_emails

Get recent emails with full content.

**Parameters**:
- `folder` (string, optional): Email folder to check (default: "INBOX")
- `days` (integer, optional): Number of days to look back for recent emails (default: 7)
- `limit` (integer, optional): Maximum number of emails to return (default: 5)
- `include_attachments` (boolean, optional): Include attachment content in base64 format (default: false)

**Example Response**:
```json
{
  "folder": "INBOX",
  "folder_info": {
    "folder": "INBOX",
    "message_count": 150,
    "selected": true
  },
  "days_back": 7,
  "search_criteria": "SINCE 08-Jan-2024",
  "emails": [
    {
      "uid": "1234",
      "subject": "Important Meeting Tomorrow",
      "sender": "boss@company.com",
      "recipient": "me@company.com",
      "date": "Mon, 15 Jan 2024 10:30:00 +0000",
      "body_text": "Meeting details...",
      "body_html": "<p>Meeting details...</p>",
      "size": 2048,
      "flags": ["\\Seen"],
      "attachments": []
    }
  ],
  "count": 1,
  "timestamp": "2024-01-15T10:30:00"
}
```

## Testing

Run the test script to verify your configuration:

```bash
python tests/test_email_imap_http_mcp.py
```

The test script will:
1. Test standalone server functionality
2. Test HTTP health check endpoint
3. Test WebSocket MCP protocol communication
4. Test all available tools (list_folders, check_emails, etc.)
5. Verify IMAP connection and authentication

Note: For integration tests, the server must be running in another terminal.

## Integration with SimaCode

The email IMAP MCP tool integrates with SimaCode's MCP system. You can register it in your MCP configuration:

```yaml
# config/mcp_servers.yaml
servers:
  email_imap:
    name: email_imap
    enabled: true  # Enable for email automation features
    type: websocket
    url: ws://localhost:8081/mcp/ws
    environment:
      EMAIL_IMAP_SERVER: imap.gmail.com
      EMAIL_IMAP_PORT_IMAP: "993"
      EMAIL_USERNAME: your_email@gmail.com
      EMAIL_PASSWORD: your_app_password
```

**Important**: The server must be started manually before SimaCode can connect:
```bash
python tools/mcp_email_imap_http_server.py
```

## Security Considerations

- **App Passwords**: Always use App Passwords instead of regular passwords for Gmail and other providers that support them
- **Environment Variables**: Store sensitive credentials in environment variables or `.env.mcp` file, never in code
- **SSL/TLS**: The tool uses SSL/TLS by default for secure connections
- **Timeout**: Configure appropriate timeouts to prevent hanging connections
- **Attachments**: Be cautious when retrieving large attachments as they are base64 encoded and can consume significant memory

## Troubleshooting

### Common Issues

1. **Authentication Failed**
   - For Gmail: Ensure you're using an App Password, not your regular password
   - Verify 2FA is enabled for your Google Account
   - Check that IMAP is enabled in your email settings

2. **Connection Timeout**
   - Check your firewall settings
   - Verify the IMAP server address and port
   - Increase the timeout value if needed

3. **SSL Certificate Errors**
   - Ensure you're using the correct port (usually 993 for SSL)
   - Try disabling SSL temporarily for testing (not recommended for production)

4. **Folder Access Issues**
   - Some email providers have different folder names
   - Use the `list_folders` tool to see available folders

### Debug Mode

Enable debug logging by setting the log level:

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

## Example Usage in SimaCode

```python
# Check for unread emails
result = await mcp_client.call_tool("check_emails", {
    "folder": "INBOX",
    "criteria": "UNSEEN",
    "limit": 5
})

# Get recent emails from the last 3 days
result = await mcp_client.call_tool("get_recent_emails", {
    "days": 3,
    "limit": 10,
    "include_attachments": False
})

# Retrieve specific email with attachments
result = await mcp_client.call_tool("get_email", {
    "uid": "1234",
    "include_attachments": True
})
```

This tool enables SimaCode to efficiently handle email-related automation tasks, from checking for important emails to processing email content and attachments.