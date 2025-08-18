"""
Email sending tool for SimaCode.

This tool provides secure email sending capabilities with comprehensive
safety checks, SMTP configuration management, and permission validation.
"""

import asyncio
import email.utils
import mimetypes
import os
import re
import time
from datetime import datetime, timedelta
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Any, AsyncGenerator, Dict, List, Optional, Type, Union

try:
    import aiosmtplib
    from email_validator import validate_email, EmailNotValidError
    SMTP_AVAILABLE = True
except ImportError:
    aiosmtplib = None
    validate_email = None
    EmailNotValidError = None
    SMTP_AVAILABLE = False

try:
    import bleach
    HTML_SANITIZER_AVAILABLE = True
except ImportError:
    bleach = None
    HTML_SANITIZER_AVAILABLE = False

from pydantic import BaseModel, Field, validator
from .base import Tool, ToolInput, ToolResult, ToolResultType, ToolRegistry
from ..permissions import PermissionManager, PathValidator
from ..config import Config


class EmailSendInput(ToolInput):
    """Input model for EmailSend tool."""
    
    # Required email fields
    to: Union[str, List[str]] = Field(
        ..., 
        description="Recipient email address(es)"
    )
    subject: str = Field(
        ..., 
        description="Email subject line",
        max_length=500
    )
    body: str = Field(
        ..., 
        description="Email body content"
    )
    
    # Optional email fields
    cc: Optional[Union[str, List[str]]] = Field(
        None, 
        description="CC email address(es)"
    )
    bcc: Optional[Union[str, List[str]]] = Field(
        None, 
        description="BCC email address(es)"
    )
    reply_to: Optional[str] = Field(
        None, 
        description="Reply-to email address"
    )
    
    # Email format options
    content_type: str = Field(
        "text",
        pattern="^(text|html)$",
        description="Email content type: 'text' or 'html'"
    )
    encoding: str = Field(
        "utf-8",
        description="Character encoding for email content"
    )
    
    # Attachments
    attachments: Optional[List[str]] = Field(
        None,
        description="List of file paths to attach"
    )
    
    # Email options
    priority: str = Field(
        "normal",
        pattern="^(low|normal|high)$",
        description="Email priority level"
    )
    send_delay: Optional[int] = Field(
        None,
        description="Delay sending by N seconds",
        ge=0,
        le=86400  # Max 24 hours delay
    )
    
    # Override sender info (optional)
    from_name: Optional[str] = Field(
        None,
        description="Override default sender name"
    )
    from_email: Optional[str] = Field(
        None,
        description="Override default sender email"
    )
    
    @validator('to', 'cc', 'bcc', pre=True)
    def normalize_email_list(cls, v):
        """Normalize email addresses to list format."""
        if v is None:
            return None
        if isinstance(v, str):
            # Split on comma or semicolon and strip whitespace
            emails = [email.strip() for email in re.split(r'[,;]', v) if email.strip()]
            return emails if emails else None
        elif isinstance(v, list):
            return [email.strip() for email in v if email and email.strip()]
        return v
    
    @validator('subject')
    def validate_subject(cls, v):
        """Validate email subject."""
        if not v or not v.strip():
            raise ValueError("Email subject cannot be empty")
        # Remove any potential header injection
        v = re.sub(r'[\r\n]', ' ', v.strip())
        return v
    
    @validator('body')
    def validate_body(cls, v):
        """Validate email body."""
        if v is None:
            return ""
        return v
    
    @validator('attachments', pre=True)
    def validate_attachments(cls, v):
        """Validate attachment file paths."""
        if v is None:
            return None
        if isinstance(v, str):
            return [v.strip()] if v.strip() else None
        elif isinstance(v, list):
            return [path.strip() for path in v if path and path.strip()]
        return v


class EmailSendTool(Tool):
    """
    Tool for sending emails safely.
    
    This tool provides secure email sending with SMTP configuration from
    config files, permission checking, and comprehensive validation.
    """
    
    def __init__(self, config: Optional[Config] = None, permission_manager: Optional[PermissionManager] = None):
        """Initialize EmailSend tool."""
        super().__init__(
            name="email_send",
            description="Send emails securely with attachment support and permission controls",
            version="1.0.0"
        )
        
        # Load configuration
        if config is None:
            self.config = Config.load()
        else:
            self.config = config
            
        self.permission_manager = permission_manager or PermissionManager(self.config)
        self.path_validator = PathValidator(self.permission_manager.get_allowed_paths())
        
        # Rate limiting tracking
        self._email_count_hourly = {}
        self._email_count_daily = {}
        self._last_cleanup = datetime.now()
        
        # Email validation regex
        self.email_regex = re.compile(
            r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        )
    
    def get_input_schema(self) -> Type[ToolInput]:
        """Return the input schema for this tool."""
        return EmailSendInput
    
    async def validate_input(self, input_data: Dict[str, Any]) -> EmailSendInput:
        """Validate and parse tool input data."""
        return EmailSendInput(**input_data)
    
    async def check_permissions(self, input_data: EmailSendInput) -> bool:
        """Check if the tool has permission to send email with given input."""
        # Check SMTP configuration
        if not self.config.email.smtp.server:
            return False
        
        if not self.config.email.smtp.username or not self.config.email.smtp.password:
            return False
        
        # Check attachment permissions
        if input_data.attachments:
            for attachment_path in input_data.attachments:
                # Check file permission
                permission_result = self.permission_manager.check_file_permission(
                    attachment_path, "read"
                )
                if not permission_result.granted:
                    return False
                
                # Validate path safety
                is_safe, _ = self.path_validator.validate_path(
                    attachment_path, "read"
                )
                if not is_safe:
                    return False
        
        return True
    
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
        if hourly_count >= self.config.email.rate_limiting.max_emails_per_hour:
            return False, f"Hourly rate limit exceeded ({self.config.email.rate_limiting.max_emails_per_hour} emails/hour)"
        
        # Check daily limit
        daily_count = self._email_count_daily.get(current_day, 0)
        if daily_count >= self.config.email.rate_limiting.max_emails_per_day:
            return False, f"Daily rate limit exceeded ({self.config.email.rate_limiting.max_emails_per_day} emails/day)"
        
        return True, ""
    
    def _increment_rate_counters(self):
        """Increment rate limiting counters."""
        now = datetime.now()
        current_hour = now.replace(minute=0, second=0, microsecond=0)
        current_day = now.date()
        
        self._email_count_hourly[current_hour] = self._email_count_hourly.get(current_hour, 0) + 1
        self._email_count_daily[current_day] = self._email_count_daily.get(current_day, 0) + 1
    
    def _validate_email_address(self, email_addr: str) -> tuple[bool, str]:
        """Validate email address format and domain restrictions."""
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
        
        # Extract domain
        domain = email_addr.split('@')[1].lower()
        
        # Check against blocked domains
        if domain in self.config.email.security.blocked_domains:
            return False, f"Domain {domain} is blocked"
        
        # Check against allowed domains (if specified)
        if (self.config.email.security.allowed_domains and 
            domain not in self.config.email.security.allowed_domains):
            return False, f"Domain {domain} is not in allowed domains list"
        
        return True, email_addr
    
    def _validate_all_recipients(self, input_data: EmailSendInput) -> tuple[bool, str, int]:
        """Validate all recipient email addresses."""
        all_recipients = []
        
        # Collect all recipients
        if input_data.to:
            all_recipients.extend(input_data.to)
        if input_data.cc:
            all_recipients.extend(input_data.cc)
        if input_data.bcc:
            all_recipients.extend(input_data.bcc)
        
        # Check recipient count limit
        if len(all_recipients) > self.config.email.security.max_recipients:
            return False, f"Too many recipients ({len(all_recipients)} > {self.config.email.security.max_recipients})", 0
        
        # Validate each recipient
        for recipient in all_recipients:
            is_valid, result = self._validate_email_address(recipient)
            if not is_valid:
                return False, result, 0
        
        return True, "", len(all_recipients)
    
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
    
    async def _validate_attachments(self, attachments: List[str], execution_id: str) -> AsyncGenerator[ToolResult, None]:
        """Validate attachment files."""
        total_size = 0
        
        for attachment_path in attachments:
            # Check if file exists
            if not os.path.exists(attachment_path):
                yield ToolResult(
                    type=ToolResultType.ERROR,
                    content=f"Attachment file not found: {attachment_path}",
                    execution_id=execution_id
                )
                return
            
            # Check if it's a file
            if not os.path.isfile(attachment_path):
                yield ToolResult(
                    type=ToolResultType.ERROR,
                    content=f"Attachment path is not a file: {attachment_path}",
                    execution_id=execution_id
                )
                return
            
            # Check file size
            file_size = os.path.getsize(attachment_path)
            total_size += file_size
            
            if file_size > self.config.email.security.max_attachment_size:
                yield ToolResult(
                    type=ToolResultType.ERROR,
                    content=f"Attachment too large: {attachment_path} ({file_size} bytes > {self.config.email.security.max_attachment_size} bytes)",
                    execution_id=execution_id
                )
                return
            
            # Check file extension
            _, ext = os.path.splitext(attachment_path.lower())
            if ext not in self.config.email.security.allowed_attachment_types:
                yield ToolResult(
                    type=ToolResultType.ERROR,
                    content=f"Attachment type not allowed: {attachment_path} (extension: {ext})",
                    execution_id=execution_id
                )
                return
            
            yield ToolResult(
                type=ToolResultType.INFO,
                content=f"Validated attachment: {os.path.basename(attachment_path)} ({file_size} bytes)",
                execution_id=execution_id,
                metadata={"file_path": attachment_path, "file_size": file_size}
            )
    
    async def _create_email_message(self, input_data: EmailSendInput, execution_id: str) -> AsyncGenerator[tuple[MIMEMultipart, ToolResult], None]:
        """Create email message with all content and attachments."""
        # Determine sender info
        from_email = input_data.from_email or self.config.email.defaults.from_email or self.config.email.smtp.username
        from_name = input_data.from_name or self.config.email.defaults.from_name
        
        if not from_email:
            yield None, ToolResult(
                type=ToolResultType.ERROR,
                content="No sender email configured",
                execution_id=execution_id
            )
            return
        
        # Create message
        msg = MIMEMultipart('mixed')
        msg['Subject'] = input_data.subject
        msg['From'] = email.utils.formataddr((from_name, from_email))
        msg['To'] = ', '.join(input_data.to)
        
        if input_data.cc:
            msg['Cc'] = ', '.join(input_data.cc)
        
        if input_data.reply_to:
            msg['Reply-To'] = input_data.reply_to
        
        # Set priority
        if input_data.priority == "high":
            msg['X-Priority'] = '1'
            msg['X-MSMail-Priority'] = 'High'
        elif input_data.priority == "low":
            msg['X-Priority'] = '5'
            msg['X-MSMail-Priority'] = 'Low'
        
        # Add timestamp
        msg['Date'] = email.utils.formatdate(localtime=True)
        
        # Create body
        body_content = input_data.body
        if input_data.content_type == "html":
            body_content = self._sanitize_html_content(body_content)
        
        # Check body size
        if len(body_content.encode(input_data.encoding)) > self.config.email.security.max_body_size:
            yield None, ToolResult(
                type=ToolResultType.ERROR,
                content=f"Email body too large ({len(body_content)} characters > {self.config.email.security.max_body_size} bytes)",
                execution_id=execution_id
            )
            return
        
        # Attach body
        body_part = MIMEText(body_content, input_data.content_type, input_data.encoding)
        msg.attach(body_part)
        
        yield None, ToolResult(
            type=ToolResultType.INFO,
            content=f"Created email message: {input_data.subject}",
            execution_id=execution_id,
            metadata={
                "from": from_email,
                "to_count": len(input_data.to),
                "body_size": len(body_content)
            }
        )
        
        # Add attachments
        if input_data.attachments:
            async for result in self._validate_attachments(input_data.attachments, execution_id):
                if result.type == ToolResultType.ERROR:
                    yield None, result
                    return
                yield None, result
            
            for attachment_path in input_data.attachments:
                try:
                    with open(attachment_path, 'rb') as f:
                        attachment_data = f.read()
                    
                    # Guess content type
                    content_type, _ = mimetypes.guess_type(attachment_path)
                    if content_type is None:
                        content_type = 'application/octet-stream'
                    
                    main_type, sub_type = content_type.split('/', 1)
                    
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
                    
                    yield None, ToolResult(
                        type=ToolResultType.INFO,
                        content=f"Attached file: {os.path.basename(attachment_path)}",
                        execution_id=execution_id
                    )
                    
                except Exception as e:
                    yield None, ToolResult(
                        type=ToolResultType.ERROR,
                        content=f"Failed to attach file {attachment_path}: {str(e)}",
                        execution_id=execution_id
                    )
                    return
        
        yield msg, ToolResult(
            type=ToolResultType.SUCCESS,
            content="Email message created successfully",
            execution_id=execution_id
        )
    
    async def execute(self, input_data: EmailSendInput) -> AsyncGenerator[ToolResult, None]:
        """Execute email sending operation."""
        execution_id = input_data.execution_id
        
        try:
            # Check if SMTP libraries are available
            if not SMTP_AVAILABLE:
                yield ToolResult(
                    type=ToolResultType.ERROR,
                    content="Email sending not available. Please install required packages: pip install aiosmtplib email-validator",
                    execution_id=execution_id
                )
                return
            
            yield ToolResult(
                type=ToolResultType.INFO,
                content="Starting email sending process",
                execution_id=execution_id
            )
            
            # Check rate limits
            rate_ok, rate_msg = self._check_rate_limits()
            if not rate_ok:
                yield ToolResult(
                    type=ToolResultType.ERROR,
                    content=rate_msg,
                    execution_id=execution_id
                )
                return
            
            # Validate recipients
            recipients_ok, recipients_msg, recipient_count = self._validate_all_recipients(input_data)
            if not recipients_ok:
                yield ToolResult(
                    type=ToolResultType.ERROR,
                    content=recipients_msg,
                    execution_id=execution_id
                )
                return
            
            yield ToolResult(
                type=ToolResultType.INFO,
                content=f"Validated {recipient_count} recipient(s)",
                execution_id=execution_id
            )
            
            # Create email message
            email_message = None
            async for msg, result in self._create_email_message(input_data, execution_id):
                if result.type == ToolResultType.ERROR:
                    yield result
                    return
                yield result
                if msg is not None:
                    email_message = msg
            
            if email_message is None:
                yield ToolResult(
                    type=ToolResultType.ERROR,
                    content="Failed to create email message",
                    execution_id=execution_id
                )
                return
            
            # Handle send delay
            if input_data.send_delay and input_data.send_delay > 0:
                yield ToolResult(
                    type=ToolResultType.INFO,
                    content=f"Waiting {input_data.send_delay} seconds before sending...",
                    execution_id=execution_id
                )
                await asyncio.sleep(input_data.send_delay)
            
            # Send email
            yield ToolResult(
                type=ToolResultType.PROGRESS,
                content="Connecting to SMTP server...",
                execution_id=execution_id
            )
            
            smtp_config = self.config.email.smtp
            
            try:
                async with aiosmtplib.SMTP(
                    hostname=smtp_config.server,
                    port=smtp_config.port,
                    timeout=smtp_config.timeout,
                    use_tls=smtp_config.use_ssl,  # Direct SSL
                    start_tls=smtp_config.use_tls  # STARTTLS
                ) as smtp:
                    
                    yield ToolResult(
                        type=ToolResultType.PROGRESS,
                        content="Authenticating with SMTP server...",
                        execution_id=execution_id
                    )
                    
                    await smtp.login(smtp_config.username, smtp_config.password)
                    
                    yield ToolResult(
                        type=ToolResultType.PROGRESS,
                        content="Sending email...",
                        execution_id=execution_id
                    )
                    
                    # Collect all recipient addresses
                    all_recipients = input_data.to[:]
                    if input_data.cc:
                        all_recipients.extend(input_data.cc)
                    if input_data.bcc:
                        all_recipients.extend(input_data.bcc)
                    
                    await smtp.send_message(
                        email_message,
                        recipients=all_recipients
                    )
                    
                    # Increment rate counters
                    self._increment_rate_counters()
                    
                    yield ToolResult(
                        type=ToolResultType.SUCCESS,
                        content=f"Email sent successfully to {len(all_recipients)} recipient(s)",
                        execution_id=execution_id,
                        metadata={
                            "subject": input_data.subject,
                            "recipient_count": len(all_recipients),
                            "attachment_count": len(input_data.attachments) if input_data.attachments else 0,
                            "content_type": input_data.content_type
                        }
                    )
                    
            except aiosmtplib.SMTPAuthenticationError:
                yield ToolResult(
                    type=ToolResultType.ERROR,
                    content="SMTP authentication failed. Please check username and password.",
                    execution_id=execution_id
                )
            except aiosmtplib.SMTPConnectError:
                yield ToolResult(
                    type=ToolResultType.ERROR,
                    content=f"Failed to connect to SMTP server {smtp_config.server}:{smtp_config.port}",
                    execution_id=execution_id
                )
            except aiosmtplib.SMTPException as e:
                yield ToolResult(
                    type=ToolResultType.ERROR,
                    content=f"SMTP error: {str(e)}",
                    execution_id=execution_id
                )
            except Exception as e:
                yield ToolResult(
                    type=ToolResultType.ERROR,
                    content=f"Unexpected error sending email: {str(e)}",
                    execution_id=execution_id,
                    metadata={"error_type": type(e).__name__}
                )
                
        except Exception as e:
            yield ToolResult(
                type=ToolResultType.ERROR,
                content=f"Email sending failed: {str(e)}",
                execution_id=execution_id,
                metadata={"error_type": type(e).__name__}
            )


# Register the tool
email_send_tool = EmailSendTool()
ToolRegistry.register(email_send_tool)