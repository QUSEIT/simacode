#!/usr/bin/env python3
"""
Email SMTP Send MCP Server (stdio)

A stdio-based MCP server that provides SMTP email sending functionality.
It communicates with SimaCode via stdio protocol and provides secure email
sending capabilities with attachment support and comprehensive validation.

Features:
- stdio-based MCP server
- SMTP email server connection with SSL/TLS
- Secure email sending with validation
- Attachment handling with size and type restrictions
- Configuration via .simacode/config.yaml (primary) and .env.mcp (fallback)
- Rate limiting and security controls

Configuration:
This tool reads configuration from SimaCode's config system. Example config.yaml:

email:
  smtp:
    server: smtp.gmail.com
    port: 587
    use_tls: true
    use_ssl: false
    timeout: 60
    username: your-email@gmail.com  # Or set EMAIL_USERNAME env var
    password: your-app-password     # Or set EMAIL_PASSWORD env var
  defaults:
    from_name: "Your Name"
    from_email: your-email@gmail.com
  security:
    max_recipients: 50
    max_attachment_size: 26214400  # 25MB
    max_body_size: 1048576         # 1MB
    allowed_attachment_types: [".pdf", ".doc", ".jpg", ...]
  rate_limiting:
    max_emails_per_hour: 100
    max_emails_per_day: 1000

Environment variables (fallback):
- EMAIL_SMTP_SERVER
- EMAIL_USERNAME  
- EMAIL_PASSWORD
- EMAIL_FROM_NAME
- EMAIL_FROM_EMAIL
"""

import asyncio
import email.utils
import json
import logging
import mimetypes
import os
import re
import sys
import base64
from datetime import datetime, timedelta
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Any, Dict, List, Optional, AsyncGenerator
from dataclasses import dataclass

# Email libraries with fallbacks
try:
    import aiosmtplib
    from email_validator import validate_email, EmailNotValidError
    SMTP_AVAILABLE = True
except ImportError:
    aiosmtplib = None
    validate_email = None
    EmailNotValidError = None
    SMTP_AVAILABLE = False

# HTML sanitizer with fallback
try:
    import bleach
    HTML_SANITIZER_AVAILABLE = True
except ImportError:
    bleach = None
    HTML_SANITIZER_AVAILABLE = False

# Environment configuration support
try:
    from dotenv import load_dotenv
    DOTENV_AVAILABLE = True
    print("Info: python-dotenv is available for .env.mcp loading", file=sys.stderr)
except ImportError:
    DOTENV_AVAILABLE = False
    print("Warning: python-dotenv not available. .env.mcp will not be loaded.", file=sys.stderr)
    print("Install with: pip install python-dotenv", file=sys.stderr)

# Add parent directory to path for MCP imports
sys.path.insert(0, str(Path(__file__).parent.parent))

# MCP Protocol imports (using our existing MCP implementation)
from src.simacode.mcp.protocol import MCPMessage, MCPMethods, MCPErrorCodes
from src.simacode.config import Config

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@dataclass
class SMTPConfig:
    """Configuration for SMTP email connection."""
    server: str = ""
    port: int = 587
    username: str = ""
    password: str = ""
    use_ssl: bool = False
    use_tls: bool = True
    timeout: int = 60
    
    # Default sender info
    from_name: str = ""
    from_email: str = ""
    
    # Security settings
    max_recipients: int = 100
    max_body_size: int = 1024 * 1024 * 10  # 10MB
    max_attachment_size: int = 1024 * 1024 * 25  # 25MB per file
    allowed_attachment_types: List[str] = None
    
    # Rate limiting
    max_emails_per_hour: int = 50
    max_emails_per_day: int = 200
    
    def __post_init__(self):
        """Set default values after initialization."""
        if self.allowed_attachment_types is None:
            self.allowed_attachment_types = [
                '.pdf', '.doc', '.docx', '.txt', '.csv', '.xlsx', '.xls',
                '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff',
                '.zip', '.rar', '.7z',
                '.mp3', '.mp4', '.avi', '.mov',
                '.json', '.xml', '.html'
            ]
    
    @classmethod
    def from_simacode_config(cls, config: Config) -> 'SMTPConfig':
        """Create SMTPConfig from SimaCode Config object."""
        email_config = config.email
        smtp_config = email_config.smtp
        
        # Get username and password from environment variables with fallbacks
        username = smtp_config.username or os.getenv('EMAIL_USERNAME') or os.getenv('SIMACODE_SMTP_USER', '')
        password = smtp_config.password or os.getenv('EMAIL_PASSWORD') or os.getenv('SIMACODE_SMTP_PASS', '')
        
        return cls(
            server=smtp_config.server or os.getenv('EMAIL_SMTP_SERVER', ''),
            port=smtp_config.port,
            username=username,
            password=password,
            use_ssl=smtp_config.use_ssl,
            use_tls=smtp_config.use_tls,
            timeout=smtp_config.timeout,
            from_name=email_config.defaults.from_name,
            from_email=email_config.defaults.from_email,
            max_recipients=email_config.security.max_recipients,
            max_body_size=email_config.security.max_body_size,
            max_attachment_size=email_config.security.max_attachment_size,
            allowed_attachment_types=email_config.security.allowed_attachment_types,
            max_emails_per_hour=email_config.rate_limiting.max_emails_per_hour,
            max_emails_per_day=email_config.rate_limiting.max_emails_per_day
        )


@dataclass
class EmailSendResult:
    """Result from email send operation."""
    success: bool
    message: str = ""
    error: Optional[str] = None
    execution_time: float = 0.0
    metadata: Optional[Dict[str, Any]] = None


class SMTPEmailClient:
    """
    SMTP email client for secure email sending.
    """
    
    def __init__(self, config: SMTPConfig):
        """
        Initialize SMTP email client.
        
        Args:
            config: SMTP configuration containing server details
        """
        self.config = config
        self.email_regex = re.compile(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$')
        
        # Rate limiting tracking
        self._email_count_hourly = {}
        self._email_count_daily = {}
        self._last_cleanup = datetime.now()
        
        logger.info(f"[SMTP_CONFIG] SMTP Client initialized with:")
        logger.info(f"[SMTP_CONFIG]   Server: {self.config.server}")
        logger.info(f"[SMTP_CONFIG]   Port: {self.config.port}")
        logger.info(f"[SMTP_CONFIG]   Username: {self.config.username}")
        logger.info(f"[SMTP_CONFIG]   Password: {'*' * len(self.config.password) if self.config.password else 'NOT SET'}")
        logger.info(f"[SMTP_CONFIG]   Use SSL: {self.config.use_ssl}")
        logger.info(f"[SMTP_CONFIG]   Use TLS: {self.config.use_tls}")
        logger.info(f"[SMTP_CONFIG]   Timeout: {self.config.timeout}s")
    
    def _cleanup_rate_limiting(self):
        """Clean up old rate limiting entries."""
        now = datetime.now()
        if now - self._last_cleanup > timedelta(hours=1):
            # Clean hourly counters older than 1 hour
            cutoff_hour = now - timedelta(hours=1)
            self._email_count_hourly = {
                hour: count for hour, count in self._email_count_hourly.items()
                if hour > cutoff_hour
            }
            
            # Clean daily counters older than 1 day
            cutoff_day = now.date() - timedelta(days=1)
            self._email_count_daily = {
                day: count for day, count in self._email_count_daily.items()
                if day > cutoff_day
            }
            
            self._last_cleanup = now
    
    def _check_rate_limits(self) -> tuple[bool, str]:
        """Check if rate limits are exceeded."""
        self._cleanup_rate_limiting()
        
        now = datetime.now()
        current_hour = now.replace(minute=0, second=0, microsecond=0)
        current_day = now.date()
        
        # Check hourly limit
        hourly_count = self._email_count_hourly.get(current_hour, 0)
        if hourly_count >= self.config.max_emails_per_hour:
            return False, f"Hourly rate limit exceeded ({self.config.max_emails_per_hour} emails/hour)"
        
        # Check daily limit
        daily_count = self._email_count_daily.get(current_day, 0)
        if daily_count >= self.config.max_emails_per_day:
            return False, f"Daily rate limit exceeded ({self.config.max_emails_per_day} emails/day)"
        
        return True, ""
    
    def _increment_rate_counters(self):
        """Increment rate limiting counters."""
        now = datetime.now()
        current_hour = now.replace(minute=0, second=0, microsecond=0)
        current_day = now.date()
        
        self._email_count_hourly[current_hour] = self._email_count_hourly.get(current_hour, 0) + 1
        self._email_count_daily[current_day] = self._email_count_daily.get(current_day, 0) + 1
    
    def _validate_email_address(self, email_addr: str) -> tuple[bool, str]:
        """Validate email address format."""
        if not email_addr or not email_addr.strip():
            return False, "Empty email address"
        
        email_addr = email_addr.strip()
        
        # Basic format validation
        if not self.email_regex.match(email_addr):
            return False, f"Invalid email format: {email_addr}"
        
        # Use email_validator if available for more thorough validation
        if validate_email:
            try:
                valid = validate_email(email_addr)
                email_addr = valid.email
            except EmailNotValidError as e:
                return False, f"Invalid email: {str(e)}"
        
        return True, email_addr
    
    def _normalize_email_list(self, emails: Any) -> List[str]:
        """Normalize email input to list format."""
        if emails is None:
            return []
        if isinstance(emails, str):
            # Split on comma or semicolon and strip whitespace
            email_list = [email.strip() for email in re.split(r'[,;]', emails) if email.strip()]
            return email_list
        elif isinstance(emails, list):
            return [email.strip() for email in emails if email and email.strip()]
        return []
    
    def _sanitize_html_content(self, html_content: str) -> str:
        """Sanitize HTML content to prevent XSS attacks."""
        if not HTML_SANITIZER_AVAILABLE:
            # If bleach is not available, strip all HTML tags
            return re.sub(r'<[^>]+>', '', html_content)
        
        # Allow safe HTML tags
        allowed_tags = [
            'p', 'br', 'strong', 'b', 'em', 'i', 'u', 'ul', 'ol', 'li',
            'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'a', 'img', 'table',
            'tr', 'td', 'th', 'thead', 'tbody', 'div', 'span'
        ]
        
        allowed_attributes = {
            'a': ['href', 'title'],
            'img': ['src', 'alt', 'width', 'height'],
            'table': ['border', 'cellpadding', 'cellspacing'],
            'td': ['colspan', 'rowspan'],
            'th': ['colspan', 'rowspan']
        }
        
        return bleach.clean(
            html_content,
            tags=allowed_tags,
            attributes=allowed_attributes,
            strip=True
        )
    
    async def validate_attachments(self, attachments: List[str]) -> tuple[bool, str, int]:
        """Validate attachment files."""
        if not attachments:
            return True, "", 0
        
        total_size = 0
        
        for attachment_path in attachments:
            # Check if file exists
            if not os.path.exists(attachment_path):
                return False, f"Attachment file not found: {attachment_path}", 0
            
            # Check if it's a file
            if not os.path.isfile(attachment_path):
                return False, f"Attachment path is not a file: {attachment_path}", 0
            
            # Check file size
            file_size = os.path.getsize(attachment_path)
            total_size += file_size
            
            if file_size > self.config.max_attachment_size:
                return False, f"Attachment too large: {attachment_path} ({file_size} bytes > {self.config.max_attachment_size} bytes)", 0
            
            # Check file extension
            _, ext = os.path.splitext(attachment_path.lower())
            if ext not in self.config.allowed_attachment_types:
                return False, f"Attachment type not allowed: {attachment_path} (extension: {ext})", 0
        
        return True, "", total_size
    
    async def create_email_message(
        self,
        to: List[str],
        subject: str,
        body: str,
        content_type: str = "text",
        cc: Optional[List[str]] = None,
        bcc: Optional[List[str]] = None,
        reply_to: Optional[str] = None,
        attachments: Optional[List[str]] = None,
        priority: str = "normal",
        from_name: Optional[str] = None,
        from_email: Optional[str] = None
    ) -> tuple[Optional[MIMEMultipart], str]:
        """Create email message with all content and attachments."""
        
        # Determine sender info
        sender_email = from_email or self.config.from_email or self.config.username
        sender_name = from_name or self.config.from_name
        
        if not sender_email:
            return None, "No sender email configured"
        
        # Validate subject
        if not subject or not subject.strip():
            return None, "Email subject cannot be empty"
        
        # Clean subject (remove potential header injection)
        subject = re.sub(r'[\r\n]', ' ', subject.strip())
        
        # Process body content
        body_content = body or ""
        
        if content_type == "html":
            body_content = self._sanitize_html_content(body_content)
        
        # Check body size
        if len(body_content.encode('utf-8')) > self.config.max_body_size:
            return None, f"Email body too large ({len(body_content)} characters > {self.config.max_body_size} bytes)"
        
        # Create message - use different structure based on whether we have attachments
        has_attachments = attachments and len(attachments) > 0
        
        if has_attachments:
            # Use multipart for attachments
            msg = MIMEMultipart('mixed')
            
            # Set headers
            msg['Subject'] = subject
            msg['From'] = email.utils.formataddr((sender_name, sender_email))
            msg['To'] = ', '.join(to)
            
            if cc:
                msg['Cc'] = ', '.join(cc)
            
            if reply_to:
                msg['Reply-To'] = reply_to
            
            # Set priority
            if priority == "high":
                msg['X-Priority'] = '1'
                msg['X-MSMail-Priority'] = 'High'
            elif priority == "low":
                msg['X-Priority'] = '5'
                msg['X-MSMail-Priority'] = 'Low'
            
            # Add timestamp
            msg['Date'] = email.utils.formatdate(localtime=True)
            
            # Attach body as first part
            mime_subtype = "html" if content_type == "html" else "plain"
            body_part = MIMEText(body_content, mime_subtype, 'utf-8')
            msg.attach(body_part)
        else:
            # For simple emails, use MIMEText directly
            mime_subtype = "html" if content_type == "html" else "plain"
            msg = MIMEText(body_content, mime_subtype, 'utf-8')
            
            # Set headers for simple message
            msg['Subject'] = subject
            msg['From'] = email.utils.formataddr((sender_name, sender_email))
            msg['To'] = ', '.join(to)
            
            if cc:
                msg['Cc'] = ', '.join(cc)
            
            if reply_to:
                msg['Reply-To'] = reply_to
            
            # Set priority
            if priority == "high":
                msg['X-Priority'] = '1'
                msg['X-MSMail-Priority'] = 'High'
            elif priority == "low":
                msg['X-Priority'] = '5'
                msg['X-MSMail-Priority'] = 'Low'
            
            # Add timestamp
            msg['Date'] = email.utils.formatdate(localtime=True)
        
        # Add attachments if any
        if attachments:
            for attachment_path in attachments:
                try:
                    with open(attachment_path, 'rb') as f:
                        attachment_data = f.read()
                    
                    # Guess content type
                    content_type_mime, _ = mimetypes.guess_type(attachment_path)
                    if content_type_mime is None:
                        content_type_mime = 'application/octet-stream'
                    
                    main_type, sub_type = content_type_mime.split('/', 1)
                    
                    attachment = MIMEApplication(
                        attachment_data,
                        _subtype=sub_type
                    )
                    attachment.add_header(
                        'Content-Disposition',
                        'attachment',
                        filename=os.path.basename(attachment_path)
                    )
                    
                    msg.attach(attachment)
                    
                except Exception as e:
                    return None, f"Failed to attach file {attachment_path}: {str(e)}"
        
        return msg, "Email message created successfully"
    
    async def send_email(
        self,
        to: List[str],
        subject: str,
        body: str,
        content_type: str = "text",
        cc: Optional[List[str]] = None,
        bcc: Optional[List[str]] = None,
        reply_to: Optional[str] = None,
        attachments: Optional[List[str]] = None,
        priority: str = "normal",
        from_name: Optional[str] = None,
        from_email: Optional[str] = None,
        send_delay: int = 0
    ) -> EmailSendResult:
        """Send email message."""
        start_time = datetime.now()
        
        try:
            # Check if SMTP libraries are available
            if not SMTP_AVAILABLE:
                return EmailSendResult(
                    success=False,
                    error="Email sending not available. Please install required packages: pip install aiosmtplib email-validator"
                )
            
            # Check rate limits
            rate_ok, rate_msg = self._check_rate_limits()
            if not rate_ok:
                return EmailSendResult(
                    success=False,
                    error=rate_msg
                )
            
            # Normalize and validate recipients
            to_list = self._normalize_email_list(to)
            cc_list = self._normalize_email_list(cc) if cc else []
            bcc_list = self._normalize_email_list(bcc) if bcc else []
            
            all_recipients = to_list + cc_list + bcc_list
            
            if not all_recipients:
                return EmailSendResult(
                    success=False,
                    error="No valid recipients specified"
                )
            
            if len(all_recipients) > self.config.max_recipients:
                return EmailSendResult(
                    success=False,
                    error=f"Too many recipients ({len(all_recipients)} > {self.config.max_recipients})"
                )
            
            # Validate each recipient
            for recipient in all_recipients:
                is_valid, result = self._validate_email_address(recipient)
                if not is_valid:
                    return EmailSendResult(
                        success=False,
                        error=f"Invalid recipient: {result}"
                    )
            
            # Validate attachments
            if attachments:
                valid_attachments, attachment_error, total_size = await self.validate_attachments(attachments)
                if not valid_attachments:
                    return EmailSendResult(
                        success=False,
                        error=attachment_error
                    )
            
            # Create email message
            email_message, create_error = await self.create_email_message(
                to=to_list,
                subject=subject,
                body=body,
                content_type=content_type,
                cc=cc_list if cc_list else None,
                bcc=bcc_list if bcc_list else None,
                reply_to=reply_to,
                attachments=attachments,
                priority=priority,
                from_name=from_name,
                from_email=from_email
            )
            
            if email_message is None:
                return EmailSendResult(
                    success=False,
                    error=create_error
                )
            
            # Handle send delay
            if send_delay > 0:
                await asyncio.sleep(send_delay)
            
            # Send email via SMTP
            try:
                async with aiosmtplib.SMTP(
                    hostname=self.config.server,
                    port=self.config.port,
                    timeout=self.config.timeout,
                    use_tls=self.config.use_ssl,  # Direct SSL
                    start_tls=self.config.use_tls  # STARTTLS
                ) as smtp:
                    
                    await smtp.login(self.config.username, self.config.password)
                    
                    await smtp.send_message(
                        email_message,
                        recipients=all_recipients
                    )
                    
                    # Increment rate counters
                    self._increment_rate_counters()
                    
                    execution_time = (datetime.now() - start_time).total_seconds()
                    
                    return EmailSendResult(
                        success=True,
                        message=f"Email sent successfully to {len(all_recipients)} recipient(s)",
                        execution_time=execution_time,
                        metadata={
                            "subject": subject,
                            "recipient_count": len(all_recipients),
                            "attachment_count": len(attachments) if attachments else 0,
                            "content_type": content_type
                        }
                    )
                    
            except aiosmtplib.SMTPAuthenticationError:
                return EmailSendResult(
                    success=False,
                    error="SMTP authentication failed. Please check username and password."
                )
            except aiosmtplib.SMTPConnectError:
                return EmailSendResult(
                    success=False,
                    error=f"Failed to connect to SMTP server {self.config.server}:{self.config.port}"
                )
            except aiosmtplib.SMTPException as e:
                return EmailSendResult(
                    success=False,
                    error=f"SMTP error: {str(e)}"
                )
            except Exception as e:
                return EmailSendResult(
                    success=False,
                    error=f"Unexpected error sending email: {str(e)}"
                )
                
        except Exception as e:
            execution_time = (datetime.now() - start_time).total_seconds()
            return EmailSendResult(
                success=False,
                error=f"Email sending failed: {str(e)}",
                execution_time=execution_time
            )


class EmailSMTPMCPServer:
    """
    stdio-based MCP server for SMTP email sending.
    
    This server provides MCP protocol compliance over stdio and integrates
    with SMTP email servers for secure email sending.
    """
    
    def __init__(self, smtp_config: Optional[SMTPConfig] = None):
        """
        Initialize Email SMTP MCP server.
        
        Args:
            smtp_config: Email SMTP configuration
        """
        # Initialize email client with configuration
        self.smtp_config = smtp_config or SMTPConfig()
        self.email_client = SMTPEmailClient(self.smtp_config)
        
        # MCP server info
        self.server_info = {
            "name": "email-smtp-send-mcp-server",
            "version": "1.0.0",
            "description": "Email SMTP Send MCP Server for Secure Email Sending"
        }
        
        # Available tools
        self.tools = {
            "send_email": {
                "name": "send_email",
                "description": "Send email securely with attachment support and comprehensive validation",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "to": {
                            "type": ["string", "array"],
                            "items": {"type": "string"},
                            "description": "Recipient email address(es) - can be string or array"
                        },
                        "subject": {
                            "type": "string",
                            "description": "Email subject line",
                            "maxLength": 500
                        },
                        "body": {
                            "type": "string",
                            "description": "Email body content"
                        },
                        "content_type": {
                            "type": "string",
                            "enum": ["text", "html"],
                            "description": "Email content type: 'text' or 'html'",
                            "default": "text"
                        },
                        "cc": {
                            "type": ["string", "array"],
                            "items": {"type": "string"},
                            "description": "CC email address(es) - optional"
                        },
                        "bcc": {
                            "type": ["string", "array"],
                            "items": {"type": "string"},
                            "description": "BCC email address(es) - optional"
                        },
                        "reply_to": {
                            "type": "string",
                            "description": "Reply-to email address - optional"
                        },
                        "attachments": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "List of file paths to attach - optional"
                        },
                        "priority": {
                            "type": "string",
                            "enum": ["low", "normal", "high"],
                            "description": "Email priority level",
                            "default": "normal"
                        },
                        "send_delay": {
                            "type": "integer",
                            "minimum": 0,
                            "maximum": 86400,
                            "description": "Delay sending by N seconds (max 24 hours) - optional"
                        },
                        "from_name": {
                            "type": "string",
                            "description": "Override default sender name - optional"
                        },
                        "from_email": {
                            "type": "string",
                            "description": "Override default sender email - optional"
                        }
                    },
                    "required": ["to", "subject", "body"]
                }
            }
        }
        
        logger.info(f"Email SMTP MCP Server initialized for stdio")
    
    async def _process_mcp_message(self, message: MCPMessage) -> Optional[MCPMessage]:
        """Process an MCP message and return response."""
        
        if message.method == "notifications/initialized":
            logger.info("Received initialized notification")
            return None
        
        if message.method == MCPMethods.INITIALIZE:
            return MCPMessage(
                id=message.id,
                result={
                    "serverInfo": self.server_info,
                    "capabilities": {
                        "tools": {"listChanged": False},
                        "resources": {"subscribe": False, "listChanged": False}
                    }
                }
            )
            
        elif message.method == MCPMethods.TOOLS_LIST:
            tools_list = list(self.tools.values())
            return MCPMessage(
                id=message.id,
                result={"tools": tools_list}
            )
            
        elif message.method == MCPMethods.TOOLS_CALL:
            return await self._execute_tool(message)
            
        elif message.method == MCPMethods.PING:
            return MCPMessage(
                id=message.id,
                result={"pong": True}
            )
            
        elif message.method == MCPMethods.RESOURCES_LIST:
            return MCPMessage(
                id=message.id,
                result={"resources": []}
            )
            
        elif message.method == MCPMethods.PROMPTS_LIST:
            return MCPMessage(
                id=message.id,
                result={"prompts": []}
            )
            
        else:
            return MCPMessage(
                id=message.id,
                error={
                    "code": MCPErrorCodes.METHOD_NOT_FOUND,
                    "message": f"Method '{message.method}' not found"
                }
            )
    
    async def _execute_tool(self, message: MCPMessage) -> MCPMessage:
        """Execute a tool and return the result."""
        tool_start = datetime.now()
        try:
            params = message.params or {}
            tool_name = params.get("name")
            arguments = params.get("arguments", {})
            
            logger.info(f"[TOOL_EXEC] Starting tool execution: {tool_name}")
            logger.debug(f"[TOOL_EXEC] Tool arguments: {arguments}")
            
            if tool_name not in self.tools:
                logger.error(f"[TOOL_EXEC] Tool '{tool_name}' not found")
                return MCPMessage(
                    id=message.id,
                    error={
                        "code": MCPErrorCodes.TOOL_NOT_FOUND,
                        "message": f"Tool '{tool_name}' not found"
                    }
                )
            
            start_time = asyncio.get_event_loop().time()
            logger.debug(f"[TOOL_EXEC] Dispatching to tool handler: {tool_name}")
            
            if tool_name == "send_email":
                result = await self._send_email(arguments)
            else:
                raise ValueError(f"Unknown tool: {tool_name}")
            
            execution_time = asyncio.get_event_loop().time() - start_time
            total_time = (datetime.now() - tool_start).total_seconds()
            
            logger.info(f"[TOOL_EXEC] Tool '{tool_name}' completed in {total_time:.2f}s")
            
            # Create response
            response_content = {
                "success": result.success,
                "message": result.message if result.success else result.error,
                "execution_time": result.execution_time,
                "timestamp": datetime.now().isoformat()
            }
            
            if result.metadata:
                response_content["metadata"] = result.metadata
            
            # Serialize JSON
            try:
                json_text = json.dumps(response_content, indent=2, ensure_ascii=False)
            except UnicodeEncodeError:
                json_text = json.dumps(response_content, indent=2, ensure_ascii=True)
            
            return MCPMessage(
                id=message.id,
                result={
                    "content": [
                        {
                            "type": "text",
                            "text": json_text
                        }
                    ],
                    "isError": not result.success,
                    "metadata": {
                        "execution_time": execution_time,
                        "tool": tool_name,
                        "response_size_bytes": len(json_text.encode('utf-8'))
                    }
                }
            )
            
        except Exception as e:
            total_time = (datetime.now() - tool_start).total_seconds()
            logger.error(f"[TOOL_EXEC] Tool execution error after {total_time:.2f}s: {str(e)}")
            
            return MCPMessage(
                id=message.id,
                error={
                    "code": MCPErrorCodes.INTERNAL_ERROR,
                    "message": str(e)
                }
            )
    
    async def _send_email(self, arguments: Dict[str, Any]) -> EmailSendResult:
        """Send email with given arguments."""
        try:
            # Extract arguments with defaults
            to = arguments.get("to")
            subject = arguments.get("subject")
            body = arguments.get("body")
            content_type = arguments.get("content_type", "text")
            cc = arguments.get("cc")
            bcc = arguments.get("bcc")
            reply_to = arguments.get("reply_to")
            attachments = arguments.get("attachments")
            priority = arguments.get("priority", "normal")
            send_delay = arguments.get("send_delay", 0)
            from_name = arguments.get("from_name")
            from_email = arguments.get("from_email")
            
            # Validate required fields
            if not to:
                return EmailSendResult(
                    success=False,
                    error="'to' field is required"
                )
            
            if not subject:
                return EmailSendResult(
                    success=False,
                    error="'subject' field is required"
                )
            
            if body is None:
                return EmailSendResult(
                    success=False,
                    error="'body' field is required"
                )
            
            # Convert single string to list for 'to' field
            if isinstance(to, str):
                to = [to]
            
            # Send email
            return await self.email_client.send_email(
                to=to,
                subject=subject,
                body=body,
                content_type=content_type,
                cc=cc,
                bcc=bcc,
                reply_to=reply_to,
                attachments=attachments,
                priority=priority,
                from_name=from_name,
                from_email=from_email,
                send_delay=send_delay
            )
            
        except Exception as e:
            return EmailSendResult(
                success=False,
                error=f"Failed to send email: {str(e)}"
            )
    
    async def run_stdio(self):
        """Run the MCP server using stdio."""
        logger.info("Starting Email SMTP MCP Server with stdio")
        
        # Log detailed SMTP configuration status
        logger.info("[SERVER_CONFIG] Email SMTP MCP Server configuration:")
        logger.info(f"[SERVER_CONFIG]   Server: {self.smtp_config.server}")
        logger.info(f"[SERVER_CONFIG]   Port: {self.smtp_config.port}")
        logger.info(f"[SERVER_CONFIG]   Username: {self.smtp_config.username}")
        logger.info(f"[SERVER_CONFIG]   Password: {'SET' if self.smtp_config.password else 'NOT SET'}")
        logger.info(f"[SERVER_CONFIG]   Use SSL: {self.smtp_config.use_ssl}")
        logger.info(f"[SERVER_CONFIG]   Use TLS: {self.smtp_config.use_tls}")
        logger.info(f"[SERVER_CONFIG]   Timeout: {self.smtp_config.timeout}s")
        
        if self.smtp_config.server and self.smtp_config.username:
            logger.info(f"[SERVER_CONFIG] SMTP fully configured: {self.smtp_config.server}:{self.smtp_config.port} ({self.smtp_config.username})")
        else:
            logger.warning("[SERVER_CONFIG] SMTP configuration incomplete - functionality will be limited")
        
        try:
            while True:
                try:
                    # Read from stdin
                    line = await asyncio.to_thread(sys.stdin.readline)
                    if not line:
                        break
                    
                    line = line.strip()
                    if not line:
                        continue
                    
                    # Parse JSON request
                    request_data = json.loads(line)
                    mcp_message = MCPMessage.from_dict(request_data)
                    
                    # Process message
                    response = await self._process_mcp_message(mcp_message)
                    
                    # Send response to stdout if there is one
                    if response is not None:
                        try:
                            json_response = response.to_json()
                            print(json_response, flush=True)
                        except UnicodeEncodeError:
                            # Fallback: create a simple error response
                            error_response = MCPMessage(
                                id=mcp_message.id,
                                error={
                                    "code": MCPErrorCodes.INTERNAL_ERROR,
                                    "message": "Encoding error in response"
                                }
                            )
                            print(error_response.to_json(), flush=True)
                    
                except json.JSONDecodeError as e:
                    logger.error(f"Invalid JSON received: {e}")
                    continue
                except Exception as e:
                    logger.error(f"Error processing message: {e}")
                    # Try to send error response if we have a request ID
                    try:
                        if 'request_data' in locals() and 'id' in request_data:
                            error_response = MCPMessage(
                                id=request_data["id"],
                                error={
                                    "code": MCPErrorCodes.INTERNAL_ERROR,
                                    "message": str(e)
                                }
                            )
                            print(error_response.to_json(), flush=True)
                    except:
                        pass
                    continue
        
        except KeyboardInterrupt:
            logger.info("Received interrupt signal")
        except Exception as e:
            logger.error(f"Stdio server error: {e}")
        finally:
            logger.info("Email SMTP MCP Server stopped")


def load_simacode_config(config_path: Optional[Path] = None) -> Config:
    """Load SimaCode configuration with fallback to environment variables."""
    try:
        # Try to load SimaCode configuration
        config = Config.load(config_path=config_path)
        logger.info("[CONFIG_LOAD] Successfully loaded SimaCode configuration")
        return config
    except Exception as e:
        logger.warning(f"[CONFIG_LOAD] Failed to load SimaCode config: {e}")
        logger.info("[CONFIG_LOAD] Falling back to environment variables and defaults")
        
        # Load environment from .env.mcp as fallback
        env_file = Path(__file__).parent.parent / ".env.mcp"
        if DOTENV_AVAILABLE and env_file.exists():
            logger.info(f"[ENV_LOAD] Loading fallback environment from: {env_file}")
            load_dotenv(env_file, override=True)
        
        # Return default config - we'll populate from environment in SMTPConfig.from_simacode_config
        return Config.load()


async def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Email SMTP Send MCP Server (stdio)")
    parser.add_argument("--config", type=Path, help="Path to SimaCode config file (default: .simacode/config.yaml)")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    
    args = parser.parse_args()
    
    # Set log level
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
        logger.debug("Debug logging enabled")
    
    # Load SimaCode configuration
    logger.info("[CONFIG] Loading SimaCode configuration...")
    try:
        simacode_config = load_simacode_config(config_path=args.config)
        logger.info("[CONFIG] SimaCode configuration loaded successfully")
        
        # Create SMTP configuration from SimaCode config
        smtp_config = SMTPConfig.from_simacode_config(simacode_config)
        
        # Log configuration status
        logger.info("[SMTP_CONFIG] SMTP Configuration loaded from SimaCode:")
        logger.info(f"[SMTP_CONFIG]   Server: {smtp_config.server}")
        logger.info(f"[SMTP_CONFIG]   Port: {smtp_config.port}")
        logger.info(f"[SMTP_CONFIG]   Username: {smtp_config.username}")
        logger.info(f"[SMTP_CONFIG]   Password: {'SET' if smtp_config.password else 'NOT SET'}")
        logger.info(f"[SMTP_CONFIG]   Use SSL: {smtp_config.use_ssl}")
        logger.info(f"[SMTP_CONFIG]   Use TLS: {smtp_config.use_tls}")
        logger.info(f"[SMTP_CONFIG]   From Name: {smtp_config.from_name}")
        logger.info(f"[SMTP_CONFIG]   From Email: {smtp_config.from_email}")
        logger.info(f"[SMTP_CONFIG]   Max Recipients: {smtp_config.max_recipients}")
        logger.info(f"[SMTP_CONFIG]   Rate Limits: {smtp_config.max_emails_per_hour}/hour, {smtp_config.max_emails_per_day}/day")
        
        # Validate critical SMTP configuration
        missing_config = []
        if not smtp_config.server:
            missing_config.append('SMTP server')
        if not smtp_config.username:
            missing_config.append('SMTP username')
        if not smtp_config.password:
            missing_config.append('SMTP password')
        
        if missing_config:
            logger.error(f"[CONFIG] Missing critical SMTP configuration: {', '.join(missing_config)}")
            logger.error(f"[CONFIG] Please check your .simacode/config.yaml file or set environment variables:")
            logger.error(f"[CONFIG]   EMAIL_SMTP_SERVER, EMAIL_USERNAME, EMAIL_PASSWORD")
            logger.info(f"[CONFIG] Example config.yaml entry:")
            logger.info(f"[CONFIG]   email:")
            logger.info(f"[CONFIG]     smtp:")
            logger.info(f"[CONFIG]       server: smtp.gmail.com")
            logger.info(f"[CONFIG]       port: 587")
            logger.info(f"[CONFIG]       username: your-email@gmail.com")
            logger.info(f"[CONFIG]       password: your-app-password")
        else:
            logger.info(f"[CONFIG] All critical SMTP configuration is set")
        
    except Exception as e:
        logger.error(f"[CONFIG] Failed to load configuration: {e}")
        logger.info("[CONFIG] Using minimal fallback configuration")
        smtp_config = SMTPConfig()
    
    # Create and start server
    server = EmailSMTPMCPServer(smtp_config=smtp_config)
    
    # Run stdio server
    await server.run_stdio()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nServer stopped by user.", file=sys.stderr)
    except Exception as e:
        print(f"Server error: {e}", file=sys.stderr)
        sys.exit(1)