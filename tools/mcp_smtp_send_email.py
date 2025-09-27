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

# Email libraries
import aiosmtplib
from email_validator import validate_email, EmailNotValidError

# HTML sanitizer
import bleach


# Add parent directory to path for MCP imports
sys.path.insert(0, str(Path(__file__).parent.parent))

# MCP Protocol imports (using our existing MCP implementation)
from src.simacode.mcp.protocol import MCPMessage, MCPMethods, MCPErrorCodes
from src.simacode.config import Config

# Import utilities
from src.simacode.utils.mcp_logger import mcp_file_log, mcp_debug, mcp_info, mcp_warning, mcp_error
from src.simacode.utils.config_loader import load_simacode_config

# Configure logging to stderr to avoid interfering with stdio protocol
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stderr
)
# logger = logging.getLogger(__name__)  # 已替换为 mcp_logger


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

        # Get from_name and from_email with environment variable fallbacks
        from_name = email_config.defaults.from_name or os.getenv('EMAIL_FROM_NAME', '')
        from_email = email_config.defaults.from_email or os.getenv('EMAIL_FROM_EMAIL', '')

        # Configuration loaded successfully

        return cls(
            server=smtp_config.server or os.getenv('EMAIL_SMTP_SERVER', ''),
            port=smtp_config.port,
            username=username,
            password=password,
            use_ssl=smtp_config.use_ssl,
            use_tls=smtp_config.use_tls,
            timeout=smtp_config.timeout,
            from_name=from_name,
            from_email=from_email,
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
        
        mcp_info(f"SMTP client initialized: {self.config.server}:{self.config.port} ({self.config.username})", tool_name="smtp_email")
        
    
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
        
        # Use email_validator for more thorough validation
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

        # Sender email determined

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
            smtp_config: Email SMTP configuration. If None, will load from .simacode/config.yaml
        """
        if smtp_config is None:
            # Auto-load configuration from .simacode/config.yaml
            from src.simacode.utils.config_loader import load_simacode_config
            from pathlib import Path

            # Try to find the config file path
            config_path = Path(".simacode/config.yaml")
            if not config_path.exists():
                config_path = None

            simacode_config = load_simacode_config(config_path=config_path)
            smtp_config = SMTPConfig.from_simacode_config(simacode_config)

        # Initialize email client with configuration
        self.smtp_config = smtp_config
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
                            "type": "string",
                            "description": "Recipient email address(es) - comma-separated if multiple"
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
                            "type": "string",
                            "description": "CC email address(es) - comma-separated if multiple, optional"
                        },
                        "bcc": {
                            "type": "string",
                            "description": "BCC email address(es) - comma-separated if multiple, optional"
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
        
        mcp_info("Email SMTP MCP server ready", tool_name="smtp_email")
    
    async def _process_mcp_message(self, message: MCPMessage) -> Optional[MCPMessage]:
        """Process an MCP message and return response."""

        # MCP 通知消息: notifications/initialized (Client -> Server)
        # 用途: 客户端通知服务器初始化完成
        # 响应: 无需响应 (Notification 类型)
        if message.method == "notifications/initialized":
            mcp_info("Received initialized notification", tool_name="smtp_email")
            return None
        
        # MCP 请求消息: initialize (Client -> Server)
        # 用途: 客户端请求初始化连接，协商协议版本和能力
        # 响应: 返回服务器信息和能力列表
        if message.method == MCPMethods.INITIALIZE:
            # 构建 MCP 响应消息: initialize response (Server -> Client)
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
            
        # MCP 请求消息: tools/list (Client -> Server)
        # 用途: 客户端请求服务器提供的所有可用工具列表
        # 响应: 返回工具列表，包含名称、描述和输入schema
        elif message.method == MCPMethods.TOOLS_LIST:
            tools_list = list(self.tools.values())
            # 构建 MCP 响应消息: tools/list response (Server -> Client)
            return MCPMessage(
                id=message.id,
                result={"tools": tools_list}
            )
            
        # MCP 请求消息: tools/call (Client -> Server)
        # 用途: 客户端请求执行指定的工具
        # 响应: 返回工具执行结果
        elif message.method == MCPMethods.TOOLS_CALL:
            return await self._execute_tool(message)
            
        # MCP 请求消息: ping (Client -> Server)
        # 用途: 客户端检测服务器是否存活
        # 响应: 返回 pong 确认消息
        elif message.method == MCPMethods.PING:
            # 构建 MCP 响应消息: ping response (Server -> Client)
            return MCPMessage(
                id=message.id,
                result={"pong": True}
            )
            
        # MCP 请求消息: resources/list (Client -> Server)
        # 用途: 客户端请求服务器提供的资源列表 (文件、数据等)
        # 响应: SMTP 工具不提供资源，返回空列表
        elif message.method == MCPMethods.RESOURCES_LIST:
            # 构建 MCP 响应消息: resources/list response (Server -> Client)
            return MCPMessage(
                id=message.id,
                result={"resources": []}
            )
            
        # MCP 请求消息: prompts/list (Client -> Server)
        # 用途: 客户端请求服务器提供的提示词模板列表
        # 响应: SMTP 工具不提供提示词模板，返回空列表
        elif message.method == MCPMethods.PROMPTS_LIST:
            # 构建 MCP 响应消息: prompts/list response (Server -> Client)
            return MCPMessage(
                id=message.id,
                result={"prompts": []}
            )
            
        else:
            # MCP 错误响应: 未知方法 (Server -> Client)
            # 当客户端请求的方法不被服务器支持时返回
            # 构建 MCP 错误响应消息: error response (Server -> Client)
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
            
            
            
            if tool_name not in self.tools:
                mcp_error(f"Tool '{tool_name}' not found", tool_name="smtp_email")
                return MCPMessage(
                    id=message.id,
                    error={
                        "code": MCPErrorCodes.TOOL_NOT_FOUND,
                        "message": f"Tool '{tool_name}' not found"
                    }
                )
            
            start_time = asyncio.get_event_loop().time()
            
            if tool_name == "send_email":
                result = await self._send_email(arguments)
            else:
                raise ValueError(f"Unknown tool: {tool_name}")
            
            execution_time = asyncio.get_event_loop().time() - start_time
            total_time = (datetime.now() - tool_start).total_seconds()
            
            
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
            mcp_error(f"Tool execution failed: {str(e)}", tool_name="smtp_email")
            
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
            content_type = arguments.get("content_type", "text") or "text"
            cc = arguments.get("cc")
            bcc = arguments.get("bcc")
            reply_to = arguments.get("reply_to")
            attachments = arguments.get("attachments")
            priority = arguments.get("priority", "normal") or "normal"
            send_delay = arguments.get("send_delay", 0) or 0
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
            
            # Convert string to list for email fields (support comma-separated)
            def parse_email_list(value):
                """Parse email string or list into a list of emails."""
                if not value:
                    return None
                if isinstance(value, str):
                    # Split by comma and strip whitespace
                    return [email.strip() for email in value.split(',') if email.strip()]
                if isinstance(value, list):
                    return value
                return None
            
            to = parse_email_list(to)
            cc = parse_email_list(cc) 
            bcc = parse_email_list(bcc)
            
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
        mcp_info("Starting Email SMTP MCP Server with stdio", tool_name="smtp_email")
        
        if self.smtp_config.server and self.smtp_config.username:
            mcp_info(f"SMTP configured: {self.smtp_config.server}:{self.smtp_config.port} ({self.smtp_config.username})", tool_name="smtp_email")
        else:
            mcp_warning("SMTP configuration incomplete - functionality will be limited", tool_name="smtp_email")
        
        try:
            while True:
                try:
                    # MCP Stdio 协议: 从 stdin 读取 JSON-RPC 消息 (Client -> Server)
                    # 格式: 每行一个完整的 JSON 对象，使用换行符分隔
                    line = await asyncio.to_thread(sys.stdin.readline)

                    # EOF 检测: 空行表示客户端关闭了连接
                    if not line:
                        break

                    # 忽略空白行
                    line = line.strip()
                    if not line:
                        continue

                    # 解析 MCP JSON-RPC 消息
                    # 消息格式: {"jsonrpc": "2.0", "id": "...", "method": "...", "params": {...}}
                    request_data = json.loads(line)
                    mcp_message = MCPMessage.from_dict(request_data)

                    # 处理 MCP 消息并生成响应
                    response = await self._process_mcp_message(mcp_message)

                    # MCP Stdio 协议: 通过 stdout 发送响应消息 (Server -> Client)
                    # 仅在有响应时发送 (某些通知消息不需要响应)
                    if response is not None:
                        try:
                            json_response = response.to_json()
                            # 发送 JSON-RPC 响应，每行一个完整的 JSON 对象
                            # flush=True 确保消息立即发送，不在缓冲区中等待
                            print(json_response, flush=True)
                        except UnicodeEncodeError:
                            # MCP 错误处理: 编码错误回退方案
                            # 当响应消息包含无法编码的字符时，创建简单错误响应
                            error_response = MCPMessage(
                                id=mcp_message.id,
                                error={
                                    "code": MCPErrorCodes.INTERNAL_ERROR,
                                    "message": "Encoding error in response"
                                }
                            )
                            print(error_response.to_json(), flush=True)
                    
                except json.JSONDecodeError as e:
                    # MCP 协议错误: 无效的 JSON 消息格式
                    mcp_error(f"Invalid JSON received: {e}", tool_name="smtp_email")
                    continue
                except Exception as e:
                    # MCP 协议错误: 消息处理异常
                    mcp_error(f"Error processing message: {e}", tool_name="smtp_email")
                    # 尝试发送错误响应 (如果有请求 ID)
                    try:
                        if 'request_data' in locals() and 'id' in request_data:
                            # MCP 错误响应: 内部错误 (Server -> Client)
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
            mcp_info("Received interrupt signal", tool_name="smtp_email")
        except Exception as e:
            mcp_error(f"Stdio server error: {e}", tool_name="smtp_email")
        finally:
            mcp_info("Email SMTP MCP Server stopped", tool_name="smtp_email")




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
        mcp_debug("Debug logging enabled", tool_name="smtp_email")
    
    # Load SimaCode configuration
    mcp_info("Loading configuration...", tool_name="smtp_email")
    try:
        simacode_config = load_simacode_config(config_path=args.config, tool_name="smtp_email")
        
        # Create SMTP configuration from SimaCode config
        smtp_config = SMTPConfig.from_simacode_config(simacode_config)
        
        mcp_info(f"SMTP config: {smtp_config.server}:{smtp_config.port} ({smtp_config.username})", tool_name="smtp_email")
        
        # Validate critical SMTP configuration
        missing_config = []
        if not smtp_config.server:
            missing_config.append('SMTP server')
        if not smtp_config.username:
            missing_config.append('SMTP username')
        if not smtp_config.password:
            missing_config.append('SMTP password')
        
        if missing_config:
            mcp_error(f"Missing SMTP config: {', '.join(missing_config)}", tool_name="smtp_email")
            mcp_error("Check .simacode/config.yaml or set EMAIL_SMTP_SERVER, EMAIL_USERNAME, EMAIL_PASSWORD", tool_name="smtp_email")
        else:
            mcp_info("SMTP configuration complete", tool_name="smtp_email")
        
    except Exception as e:
        mcp_error(f"Configuration load failed: {e}", tool_name="smtp_email")
        mcp_info("Using minimal fallback configuration", tool_name="smtp_email")
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