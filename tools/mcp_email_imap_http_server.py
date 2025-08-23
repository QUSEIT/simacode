#!/usr/bin/env python3
"""
Email IMAP MCP Server (stdio)

A stdio-based MCP server that provides IMAP email checking and retrieval functionality.
It communicates with SimaCode via stdio protocol and provides email automation
capabilities including checking for new emails, retrieving email content, and handling attachments.

Features:
- stdio-based MCP server
- IMAP email server connection with SSL/TLS
- Email listing, filtering, and retrieval
- Attachment handling with base64 encoding
- Configuration via .env.mcp file
- Health monitoring and auto-reconnection
"""

import asyncio
import email
import email.header
import imaplib
import json
import logging
import os
import sys
import base64
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, AsyncGenerator
from dataclasses import dataclass

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


# Configure logging
logging.basicConfig(
    level=logging.DEBUG,  # Changed to DEBUG for more detailed logging
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@dataclass
class EmailConfig:
    """Configuration for IMAP email connection."""
    server: str = ""
    port: int = 993
    username: str = ""
    password: str = ""
    use_ssl: bool = True
    timeout: int = 60


@dataclass
class EmailMessage:
    """Represents an email message."""
    uid: str
    subject: str
    sender: str
    recipient: str
    date: str
    body_text: str
    body_html: str
    attachments: List[Dict[str, Any]]
    headers: Dict[str, str]
    size: int
    flags: List[str]


@dataclass
class EmailOperationResult:
    """Result from email operation execution."""
    success: bool
    data: Any = None
    error: Optional[str] = None
    execution_time: float = 0.0
    operation: str = ""


class IMAPEmailClient:
    """
    IMAP email client for connecting to email servers and retrieving messages.
    """
    
    def __init__(self, config: EmailConfig):
        """
        Initialize IMAP email client.
        
        Args:
            config: Email configuration containing server details
        """
        self.config = config
        self.connection: Optional[imaplib.IMAP4_SSL] = None
        self.current_folder: str = "INBOX"
        self.last_connect_time: Optional[datetime] = None
        
        # Log IMAP configuration parameters
        logger.info(f"[IMAP_CONFIG] IMAP Client initialized with:")
        logger.info(f"[IMAP_CONFIG]   Server: {self.config.server}")
        logger.info(f"[IMAP_CONFIG]   Port: {self.config.port}")
        logger.info(f"[IMAP_CONFIG]   Username: {self.config.username}")
        logger.info(f"[IMAP_CONFIG]   Password: {'*' * len(self.config.password) if self.config.password else 'NOT SET'}")
        logger.info(f"[IMAP_CONFIG]   Use SSL: {self.config.use_ssl}")
        logger.info(f"[IMAP_CONFIG]   Timeout: {self.config.timeout}s")
        
    async def connect(self) -> bool:
        """
        Connect to IMAP server.
        
        Returns:
            bool: True if connection successful, False otherwise
        """
        start_time = datetime.now()
        try:
            logger.info(f"[CONNECT] Starting connection to IMAP server: {self.config.server}:{self.config.port} (timeout={self.config.timeout}s)")
            
            # Create connection
            connection_start = datetime.now()
            if self.config.use_ssl:
                logger.debug(f"[CONNECT] Creating SSL connection...")
                self.connection = imaplib.IMAP4_SSL(
                    self.config.server, 
                    self.config.port,
                    timeout=self.config.timeout
                )
            else:
                logger.debug(f"[CONNECT] Creating non-SSL connection...")
                self.connection = imaplib.IMAP4(
                    self.config.server,
                    self.config.port,
                    timeout=self.config.timeout
                )
            
            connection_time = (datetime.now() - connection_start).total_seconds()
            logger.debug(f"[CONNECT] Socket connection established in {connection_time:.2f}s")
            
            # Login
            login_start = datetime.now()
            logger.debug(f"[CONNECT] Attempting login for user: {self.config.username}")
            result = self.connection.login(self.config.username, self.config.password)
            login_time = (datetime.now() - login_start).total_seconds()
            logger.debug(f"[CONNECT] Login attempt completed in {login_time:.2f}s")
            
            if result[0] == 'OK':
                self.last_connect_time = datetime.now()
                total_time = (self.last_connect_time - start_time).total_seconds()
                logger.info(f"[CONNECT] Successfully connected and authenticated to IMAP server in {total_time:.2f}s")
                return True
            else:
                logger.error(f"[CONNECT] Failed to authenticate: {result[1]}")
                return False
                
        except Exception as e:
            total_time = (datetime.now() - start_time).total_seconds()
            logger.error(f"[CONNECT] Failed to connect to IMAP server after {total_time:.2f}s: {str(e)}")
            return False
    
    async def disconnect(self):
        """Disconnect from IMAP server."""
        if self.connection:
            try:
                self.connection.close()
                self.connection.logout()
                logger.info("Disconnected from IMAP server")
            except Exception as e:
                logger.error(f"Error disconnecting: {str(e)}")
            finally:
                self.connection = None
                self.last_connect_time = None
    
    async def ensure_connection(self) -> bool:
        """Ensure IMAP connection is established and healthy."""
        logger.debug(f"[ENSURE_CONN] Checking connection health...")
        
        # Check if we have a connection and it's recent
        if self.connection and self.last_connect_time:
            time_since_connect = datetime.now() - self.last_connect_time
            logger.debug(f"[ENSURE_CONN] Time since last connect: {time_since_connect.total_seconds():.1f}s")
            
            if time_since_connect.total_seconds() < 300:  # 5 minutes
                try:
                    # Test connection with NOOP
                    noop_start = datetime.now()
                    logger.debug(f"[ENSURE_CONN] Testing connection with NOOP...")
                    result = self.connection.noop()
                    noop_time = (datetime.now() - noop_start).total_seconds()
                    
                    if result[0] == 'OK':
                        logger.debug(f"[ENSURE_CONN] NOOP successful in {noop_time:.2f}s - connection healthy")
                        return True
                    else:
                        logger.warning(f"[ENSURE_CONN] NOOP failed in {noop_time:.2f}s: {result[1]}")
                except Exception as e:
                    logger.warning(f"[ENSURE_CONN] NOOP exception: {str(e)}")
        else:
            logger.debug(f"[ENSURE_CONN] No existing connection or connection too old")
        
        # Reconnect if needed
        logger.info(f"[ENSURE_CONN] Reconnecting...")
        await self.disconnect()
        return await self.connect()
    
    async def list_folders(self) -> List[str]:
        """
        List available folders/mailboxes.
        
        Returns:
            List of folder names
        """
        if not await self.ensure_connection():
            raise Exception("Failed to connect to IMAP server")
        
        try:
            result, folders = self.connection.list()
            if result != 'OK':
                raise Exception(f"Failed to list folders: {folders}")
            
            folder_names = []
            for folder in folders:
                folder_str = folder.decode('utf-8')
                parts = folder_str.split('"')
                if len(parts) >= 3:
                    folder_names.append(parts[-2])
                    
            return folder_names
            
        except Exception as e:
            logger.error(f"Error listing folders: {str(e)}")
            raise
    
    async def select_folder(self, folder: str = "INBOX") -> Dict[str, Any]:
        """
        Select a folder/mailbox.
        
        Args:
            folder: Folder name to select
            
        Returns:
            Dict with folder information
        """
        select_start = datetime.now()
        logger.debug(f"[SELECT] Selecting folder: {folder}")
        
        if not await self.ensure_connection():
            raise Exception("Failed to connect to IMAP server")
        
        try:
            logger.debug(f"[SELECT] Executing IMAP SELECT command for folder: {folder}")
            result, data = self.connection.select(folder)
            select_time = (datetime.now() - select_start).total_seconds()
            
            if result != 'OK':
                logger.error(f"[SELECT] Failed to select folder '{folder}' in {select_time:.2f}s: {data}")
                raise Exception(f"Failed to select folder '{folder}': {data}")
            
            self.current_folder = folder
            message_count = int(data[0])
            
            logger.info(f"[SELECT] Successfully selected folder '{folder}' with {message_count} messages in {select_time:.2f}s")
            
            return {
                "folder": folder,
                "message_count": message_count,
                "selected": True
            }
            
        except Exception as e:
            select_time = (datetime.now() - select_start).total_seconds()
            logger.error(f"[SELECT] Error selecting folder '{folder}' after {select_time:.2f}s: {str(e)}")
            raise
    
    async def search_emails(
        self, 
        criteria: str = "ALL", 
        limit: int = 10
    ) -> List[str]:
        """
        Search for emails based on criteria.
        
        Args:
            criteria: IMAP search criteria
            limit: Maximum number of emails to return
            
        Returns:
            List of email UIDs
        """
        search_start = datetime.now()
        logger.debug(f"[SEARCH] Starting email search with criteria: '{criteria}', limit: {limit}")
        
        if not await self.ensure_connection():
            raise Exception("Failed to connect to IMAP server")
        
        try:
            logger.debug(f"[SEARCH] Executing IMAP SEARCH command...")
            result, data = self.connection.search(None, criteria)
            search_time = (datetime.now() - search_start).total_seconds()
            
            if result != 'OK':
                logger.error(f"[SEARCH] Search failed in {search_time:.2f}s: {data}")
                raise Exception(f"Search failed: {data}")
            
            uids = data[0].split()
            total_found = len(uids)
            uids = uids[-limit:] if len(uids) > limit else uids
            uids.reverse()
            
            result_uids = [uid.decode('utf-8') for uid in uids]
            
            logger.info(f"[SEARCH] Found {total_found} emails, returning {len(result_uids)} (limited to {limit}) in {search_time:.2f}s")
            logger.debug(f"[SEARCH] Returned UIDs: {result_uids}")
            
            return result_uids
            
        except Exception as e:
            search_time = (datetime.now() - search_start).total_seconds()
            logger.error(f"[SEARCH] Error searching emails after {search_time:.2f}s: {str(e)}")
            raise
    
    def _decode_header(self, header_value: str) -> str:
        """Decode email header value."""
        if not header_value:
            return ""
        
        try:
            decoded_parts = email.header.decode_header(header_value)
            decoded_header = ""
            
            for part, encoding in decoded_parts:
                if isinstance(part, bytes):
                    if encoding:
                        decoded_header += part.decode(encoding)
                    else:
                        decoded_header += part.decode('utf-8', errors='ignore')
                else:
                    decoded_header += part
                    
            return decoded_header
            
        except Exception as e:
            logger.error(f"Error decoding header: {str(e)}")
            return str(header_value)
    
    def _extract_email_address(self, header_value: str) -> str:
        """Extract email address from header value, removing display names."""
        if not header_value:
            return ""
        
        try:
            # First decode the header
            decoded = self._decode_header(header_value)
            
            # Use email.utils.parseaddr to extract just the email address
            import email.utils
            name, address = email.utils.parseaddr(decoded)
            
            # Return just the email address part
            return address if address else decoded
            
        except Exception as e:
            logger.error(f"Error extracting email address: {str(e)}")
            return str(header_value)
    
    async def fetch_email(self, uid: str) -> EmailMessage:
        """
        Fetch email message by UID.
        
        Args:
            uid: Email UID
            
        Returns:
            EmailMessage object
        """
        fetch_start = datetime.now()
        logger.debug(f"[FETCH] Starting fetch for email UID: {uid}")
        
        if not await self.ensure_connection():
            raise Exception("Failed to connect to IMAP server")
        
        try:
            logger.debug(f"[FETCH] Executing IMAP FETCH command for UID: {uid}")
            result, data = self.connection.fetch(uid, '(RFC822 FLAGS)')
            fetch_time = (datetime.now() - fetch_start).total_seconds()
            
            if result != 'OK':
                logger.error(f"[FETCH] Failed to fetch email {uid} in {fetch_time:.2f}s: {data}")
                raise Exception(f"Failed to fetch email {uid}: {data}")
            
            raw_email = data[0][1]
            email_message = email.message_from_bytes(raw_email)
            
            subject = self._decode_header(email_message.get('Subject', ''))
            sender = self._extract_email_address(email_message.get('From', ''))
            recipient = self._extract_email_address(email_message.get('To', ''))
            date = email_message.get('Date', '')
            
            body_text = ""
            body_html = ""
            attachments = []
            
            if email_message.is_multipart():
                for part in email_message.walk():
                    content_type = part.get_content_type()
                    content_disposition = part.get('Content-Disposition', '')
                    
                    if content_type == 'text/plain' and 'attachment' not in content_disposition:
                        charset = part.get_content_charset() or 'utf-8'
                        body_text = part.get_payload(decode=True).decode(charset, errors='ignore')
                    
                    elif content_type == 'text/html' and 'attachment' not in content_disposition:
                        charset = part.get_content_charset() or 'utf-8'
                        body_html = part.get_payload(decode=True).decode(charset, errors='ignore')
                    
                    elif 'attachment' in content_disposition:
                        filename = part.get_filename()
                        if filename:
                            filename = self._decode_header(filename)
                            content = part.get_payload(decode=True)
                            attachments.append({
                                'filename': filename,
                                'content_type': content_type,
                                'size': len(content) if content else 0,
                                'content_base64': base64.b64encode(content).decode('utf-8') if content else ""
                            })
            else:
                content_type = email_message.get_content_type()
                charset = email_message.get_content_charset() or 'utf-8'
                payload = email_message.get_payload(decode=True)
                
                if payload:
                    content = payload.decode(charset, errors='ignore')
                    if content_type == 'text/html':
                        body_html = content
                    else:
                        body_text = content
            
            headers = {}
            for key, value in email_message.items():
                headers[key] = self._decode_header(value)
            
            flags_data = data[0][0].decode('utf-8')
            flags = []
            if 'FLAGS' in flags_data:
                flag_part = flags_data.split('FLAGS (')[1].split(')')[0]
                flags = [flag.strip() for flag in flag_part.split()]
            
            parse_time = (datetime.now() - fetch_start).total_seconds()
            logger.info(f"[FETCH] Successfully fetched and parsed email {uid} (size: {len(raw_email)} bytes) in {parse_time:.2f}s")
            logger.debug(f"[FETCH] Email details - Subject: '{subject[:50]}...', Sender: {sender}, Attachments: {len(attachments)}")
            
            return EmailMessage(
                uid=uid,
                subject=subject,
                sender=sender,
                recipient=recipient,
                date=date,
                body_text=body_text,
                body_html=body_html,
                attachments=attachments,
                headers=headers,
                size=len(raw_email),
                flags=flags
            )
            
        except Exception as e:
            fetch_time = (datetime.now() - fetch_start).total_seconds()
            logger.error(f"[FETCH] Error fetching email {uid} after {fetch_time:.2f}s: {str(e)}")
            raise


class EmailIMAPMCPServer:
    """
    stdio-based MCP server for IMAP email integration.
    
    This server provides MCP protocol compliance over stdio and integrates
    with IMAP email servers for email automation tasks.
    """
    
    def __init__(self, email_config: Optional[EmailConfig] = None):
        """
        Initialize Email IMAP MCP server.
        
        Args:
            email_config: Email IMAP configuration
        """
        # Initialize email client with configuration
        self.email_config = email_config or EmailConfig()
        self.email_client = IMAPEmailClient(self.email_config)
        
        # MCP server info
        self.server_info = {
            "name": "email-imap-mcp-server",
            "version": "1.0.0",
            "description": "Email IMAP MCP Server for Email Automation"
        }
        
        # Available tools
        self.tools = {
            "get_email": {
                "name": "get_email",
                "description": "Get specific email by UID with attachments and base64 content by default",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "uid": {
                            "type": "string",
                            "description": "Email UID"
                        },
                        "folder": {
                            "type": "string",
                            "description": "Email folder",
                            "default": "INBOX"
                        },
                        "include_attachments": {
                            "type": "boolean",
                            "description": "Include attachment data with Base64 content",
                            "default": True
                        },
                        "include_body_html": {
                            "type": "boolean",
                            "description": "Include HTML body content",
                            "default": False
                        },
                        "include_headers": {
                            "type": "boolean",
                            "description": "Include email headers",
                            "default": False
                        }
                    },
                    "required": ["uid"]
                }
            },
            "get_recent_emails": {
                "name": "get_recent_emails",
                "description": "Get recent emails and return pure email JSON data (does not save to file)",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "folder": {
                            "type": "string",
                            "description": "Email folder to check (default: INBOX)",
                            "default": "INBOX"
                        },
                        "days": {
                            "type": "integer",
                            "description": "Number of days to look back for recent emails",
                            "default": 7
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Maximum number of emails to return",
                            "default": 1
                        },
                        "include_body_html": {
                            "type": "boolean",
                            "description": "Include HTML body content",
                            "default": False
                        },
                        "include_attachments": {
                            "type": "boolean",
                            "description": "Include attachment content in base64 format",
                            "default": False
                        }
                    }
                }
            },
            "extract_attachments": {
                "name": "extract_attachments",
                "description": "Extract and save attachments from email JSON file by decoding base64 content",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "json_file": {
                            "type": "string",
                            "description": "Path to the email JSON file containing attachments",
                            "default": "mail.json"
                        },
                        "output_dir": {
                            "type": "string", 
                            "description": "Directory to save extracted attachment files",
                            "default": "./attachments"
                        },
                        "overwrite": {
                            "type": "boolean",
                            "description": "Whether to overwrite existing files",
                            "default": False
                        }
                    },
                    "required": ["json_file"]
                }
            }
        }
        
        logger.info(f"Email IMAP MCP Server initialized for stdio")
    
    
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
            
            if tool_name == "get_email":
                result = await self._get_email(arguments)
            elif tool_name == "get_recent_emails":
                result = await self._get_recent_emails_json(arguments)
            elif tool_name == "extract_attachments":
                result = await self._extract_attachments(arguments)
            else:
                raise ValueError(f"Unknown tool: {tool_name}")
            
            execution_time = asyncio.get_event_loop().time() - start_time
            total_time = (datetime.now() - tool_start).total_seconds()
            
            logger.info(f"[TOOL_EXEC] Tool '{tool_name}' completed in {total_time:.2f}s")
            logger.debug(f"[TOOL_EXEC] Processing result for JSON serialization...")
            
            # Ensure all content in result is safe for JSON serialization
            safe_result = self._ensure_json_safe(result)
            
            # No special handling - all tools now return consistent format
            
            # Serialize JSON with proper UTF-8 handling
            try:
                json_text = json.dumps(safe_result, indent=2, ensure_ascii=False)
            except UnicodeEncodeError:
                # Fallback: use ensure_ascii=True if UTF-8 fails
                json_text = json.dumps(safe_result, indent=2, ensure_ascii=True)
            
            # Log message size for debugging
            message_size = len(json_text.encode('utf-8'))
            logger.info(f"[TOOL_EXEC] Response JSON size: {message_size:,} bytes ({message_size/1024:.1f} KB)")
            
            # Conservative limit for MCP protocol - start truncating at 500KB
            if message_size > 500 * 1024:  # 500KB
                logger.warning(f"[TOOL_EXEC] Large response detected: {message_size:,} bytes - truncating to prevent MCP protocol issues")
                
                # For large responses, truncate body content
                if 'body_text' in safe_result and len(safe_result['body_text']) > 5000:
                    original_length = len(safe_result['body_text'])
                    safe_result['body_text'] = safe_result['body_text'][:5000] + f"\n\n[TRUNCATED - Original length: {original_length} chars]"
                    logger.warning(f"[TOOL_EXEC] Truncated body_text from {original_length} to {len(safe_result['body_text'])} chars")
                
                # Remove large attachments base64 content for oversized responses
                if 'attachments' in safe_result:
                    for i, att in enumerate(safe_result['attachments']):
                        if 'content_base64' in att and len(att['content_base64']) > 100000:
                            original_size = len(att['content_base64'])
                            att['content_base64'] = "[REMOVED - Too large for MCP protocol]"
                            logger.warning(f"[TOOL_EXEC] Removed large attachment content ({original_size:,} chars) from attachment {i}")
                
                # Re-serialize after truncation
                try:
                    json_text = json.dumps(safe_result, indent=2, ensure_ascii=False)
                    new_size = len(json_text.encode('utf-8'))
                    logger.info(f"[TOOL_EXEC] After truncation: {new_size:,} bytes ({new_size/1024:.1f} KB)")
                except UnicodeEncodeError:
                    json_text = json.dumps(safe_result, indent=2, ensure_ascii=True)
                    new_size = len(json_text.encode('utf-8'))
                    logger.info(f"[TOOL_EXEC] After truncation (ASCII): {new_size:,} bytes ({new_size/1024:.1f} KB)")
            
            return MCPMessage(
                id=message.id,
                result={
                    "content": [
                        {
                            "type": "text",
                            "text": json_text
                        }
                    ],
                    "isError": not safe_result.get("success", True),
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
    
    def _safe_text(self, text: Any) -> str:
        """Safely convert text to string, handling encoding issues."""
        if text is None:
            return ""
        
        if isinstance(text, str):
            # For strings, ensure they can be JSON serialized
            try:
                # Test if the string can be JSON serialized
                json.dumps(text, ensure_ascii=False)
                return text
            except (UnicodeError, UnicodeDecodeError, UnicodeEncodeError):
                # If there are encoding issues, clean the string
                return text.encode('utf-8', errors='replace').decode('utf-8', errors='replace')
        else:
            # Convert to string and then safely encode
            try:
                str_text = str(text)
                json.dumps(str_text, ensure_ascii=False)
                return str_text
            except (UnicodeError, UnicodeDecodeError, UnicodeEncodeError):
                return str(text).encode('utf-8', errors='replace').decode('utf-8', errors='replace')
    
    def _clean_body_text(self, text: Any) -> str:
        """Clean body text by removing special characters like \\n, \\r, \\, \" etc."""
        if text is None:
            return ""
        
        # First ensure safe text conversion
        safe_text = self._safe_text(text)
        
        # Remove special characters
        cleaned_text = safe_text.replace('\n', ' ')  # Replace newlines with spaces
        cleaned_text = cleaned_text.replace('\r', '')  # Remove carriage returns
        cleaned_text = cleaned_text.replace('\\', '')  # Remove backslashes
        cleaned_text = cleaned_text.replace('"', "'")  # Replace double quotes with single quotes
        
        # Remove extra whitespace
        import re
        cleaned_text = re.sub(r'\s+', ' ', cleaned_text)  # Replace multiple spaces with single space
        cleaned_text = cleaned_text.strip()  # Remove leading/trailing whitespace
        
        return cleaned_text
    
    def _ensure_json_safe(self, obj: Any) -> Any:
        """Recursively ensure all strings in an object are JSON-safe."""
        if isinstance(obj, dict):
            return {k: self._ensure_json_safe(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self._ensure_json_safe(item) for item in obj]
        elif isinstance(obj, str):
            return self._safe_text(obj)
        else:
            return obj
    
    async def _get_email(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Get specific email by UID."""
        try:
            uid = arguments.get("uid")
            folder = arguments.get("folder", "INBOX")
            include_attachments = arguments.get("include_attachments", True)  # Default to True
            include_body_html = arguments.get("include_body_html", False)  # Default to False
            include_headers = arguments.get("include_headers", False)  # Default to False
            
            if not uid:
                return {
                    "success": False,
                    "error": "UID parameter is required",
                    "timestamp": datetime.now().isoformat()
                }
            
            await self.email_client.select_folder(folder)
            email_msg = await self.email_client.fetch_email(str(uid))
            
            # Ensure all text content is properly encoded
            result = {
                "success": True,
                "uid": str(email_msg.uid),
                "subject": self._clean_body_text(email_msg.subject),
                "sender": self._safe_text(email_msg.sender),
                "recipient": self._safe_text(email_msg.recipient),
                "date": self._safe_text(email_msg.date),
                "body_text": self._clean_body_text(email_msg.body_text),
                "size": email_msg.size,
                "flags": email_msg.flags,
                "attachments": [],
                "timestamp": datetime.now().isoformat()
            }
            
            # Only include body_html if explicitly requested
            if include_body_html:
                result["body_html"] = self._safe_text(email_msg.body_html)
            
            # Only include headers if explicitly requested
            if include_headers:
                result["headers"] = {k: self._safe_text(v) for k, v in email_msg.headers.items()}
            
            # Process attachments - now default to include with base64 content
            safe_attachments = []
            for att in email_msg.attachments:
                safe_att = {
                    "filename": self._safe_text(att.get("filename", "")),
                    "content_type": self._safe_text(att.get("content_type", "")),
                    "size": att.get("size", 0)
                }
                # Include base64 content by default when include_attachments is True
                if include_attachments:
                    base64_content = att.get("content_base64", "")
                    safe_att["content_base64"] = base64_content
                    logger.debug(f"[GET_EMAIL] Attachment '{safe_att['filename']}': base64 content {'included' if base64_content else 'empty'} ({len(base64_content)} chars)")
                safe_attachments.append(safe_att)
            result["attachments"] = safe_attachments
            
            return result
            
        except Exception as e:
            # Safe error handling with proper encoding
            error_msg = self._safe_text(str(e))
            
            return {
                "success": False,
                "error": f"Failed to get email: {error_msg}",
                "uid": self._safe_text(str(uid)) if uid else None,
                "timestamp": datetime.now().isoformat()
            }
        finally:
            await self.email_client.disconnect()
    
    async def _get_recent_emails_json(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Get recent emails and return only the latest email in pure JSON format."""
        operation_start = datetime.now()
        try:
            folder = arguments.get("folder", "INBOX")
            days = arguments.get("days", 7)
            limit = arguments.get("limit", 1)
            include_body_html = arguments.get("include_body_html", False)
            include_attachments = arguments.get("include_attachments", False)
            
            logger.info(f"[GET_RECENT] Starting operation - folder: {folder}, days: {days}, limit: {limit}")
            logger.debug(f"[GET_RECENT] Options - include_body_html: {include_body_html}, include_attachments: {include_attachments}")
            
            select_start = datetime.now()
            await self.email_client.select_folder(folder)
            select_time = (datetime.now() - select_start).total_seconds()
            logger.debug(f"[GET_RECENT] Folder selection completed in {select_time:.2f}s")
            
            since_date = (datetime.now() - timedelta(days=days)).strftime("%d-%b-%Y")
            criteria = f"SINCE {since_date}"
            logger.debug(f"[GET_RECENT] Search criteria: '{criteria}' (since {since_date})")
            
            search_start = datetime.now()
            uids = await self.email_client.search_emails(criteria, limit)
            search_time = (datetime.now() - search_start).total_seconds()
            logger.debug(f"[GET_RECENT] Email search completed in {search_time:.2f}s")
            
            if not uids:
                return {
                    "success": False,
                    "error": "No emails found",
                    "message": "No recent emails found in the specified time range",
                    "timestamp": datetime.now().isoformat()
                }
            
            # Get the requested number of emails (up to limit)
            emails_data = []
            
            logger.info(f"[GET_RECENT] Processing {len(uids[:limit])} emails...")
            for i, uid in enumerate(uids[:limit], 1):  # Process up to 'limit' emails
                try:
                    logger.debug(f"[GET_RECENT] Processing email {i}/{len(uids[:limit])} - UID: {uid}")
                    email_start = datetime.now()
                    email_msg = await self.email_client.fetch_email(uid)
                    email_time = (datetime.now() - email_start).total_seconds()
                    logger.debug(f"[GET_RECENT] Email {i} processed in {email_time:.2f}s")
                    
                    # Create email JSON data
                    email_data = {
                        "uid": str(email_msg.uid),
                        "subject": self._clean_body_text(email_msg.subject),
                        "sender": self._safe_text(email_msg.sender),
                        "recipient": self._safe_text(email_msg.recipient),
                        "date": self._safe_text(email_msg.date),
                        "body_text": self._clean_body_text(email_msg.body_text),
                        "size": email_msg.size,
                        "flags": email_msg.flags,
                        "attachments": []
                    }
                    
                    # Only include body_html if explicitly requested
                    if include_body_html:
                        email_data["body_html"] = self._safe_text(email_msg.body_html)
                    
                    # Process attachments - always include metadata
                    for att in email_msg.attachments:
                        safe_att = {
                            "filename": self._safe_text(att.get("filename", "")),
                            "content_type": self._safe_text(att.get("content_type", "")),
                            "size": att.get("size", 0)
                        }
                        # Only include base64 content if explicitly requested
                        if include_attachments:
                            safe_att["content_base64"] = att.get("content_base64", "")
                        email_data["attachments"].append(safe_att)
                    
                    emails_data.append(email_data)
                    
                except Exception as e:
                    # Log error but continue processing other emails
                    email_time = (datetime.now() - email_start).total_seconds()
                    logger.error(f"[GET_RECENT] Error processing email {i} (UID: {uid}) after {email_time:.2f}s: {str(e)}")
                    continue
            
            operation_time = (datetime.now() - operation_start).total_seconds()
            logger.info(f"[GET_RECENT] Operation completed in {operation_time:.2f}s - retrieved {len(emails_data)} emails")
            
            # Return with success format like get_email
            return {
                "result": emails_data
            }
        
            
        except Exception as e:
            operation_time = (datetime.now() - operation_start).total_seconds()
            logger.error(f"[GET_RECENT] Operation failed after {operation_time:.2f}s: {str(e)}")
            return {
                "success": False,
                "error": f"Failed to get recent emails: {self._safe_text(str(e))}",
                "message": "An error occurred while retrieving email data",
                "timestamp": datetime.now().isoformat()
            }
        finally:
            disconnect_start = datetime.now()
            await self.email_client.disconnect()
            disconnect_time = (datetime.now() - disconnect_start).total_seconds()
            logger.debug(f"[GET_RECENT] Disconnection completed in {disconnect_time:.2f}s")
    
    async def _extract_attachments(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Extract and save attachments from email JSON file."""
        try:
            json_file = arguments.get("json_file", "mail.json")
            output_dir = arguments.get("output_dir", "./attachments")
            overwrite = arguments.get("overwrite", False)
            
            # Check if JSON file exists
            if not os.path.exists(json_file):
                return {
                    "success": False,
                    "error": f"JSON file not found: {json_file}",
                    "message": "Please provide a valid path to the email JSON file",
                    "timestamp": datetime.now().isoformat()
                }
            
            # Read and parse JSON file
            try:
                with open(json_file, 'r', encoding='utf-8') as f:
                    file_content = f.read()
                
                # Clean the content before parsing JSON
                cleaned_content = self._clean_json_content(file_content)
                
                # Parse the cleaned JSON content
                email_data = json.loads(cleaned_content)
                
            except json.JSONDecodeError as e:
                return {
                    "success": False,
                    "error": f"Invalid JSON format: {str(e)}",
                    "message": "The provided file is not valid JSON",
                    "timestamp": datetime.now().isoformat()
                }
            except Exception as e:
                return {
                    "success": False,
                    "error": f"Failed to read JSON file: {str(e)}",
                    "message": "Could not read the JSON file",
                    "timestamp": datetime.now().isoformat()
                }
            
            # Extract attachments from email data
            attachments = []
            if isinstance(email_data, dict):
                attachments = email_data.get("attachments", [])
            elif isinstance(email_data, list):
                # If it's a list of emails, get attachments from first email
                if email_data and isinstance(email_data[0], dict):
                    attachments = email_data[0].get("attachments", [])
            
            if not attachments:
                return {
                    "success": False,
                    "error": "No attachments found in JSON file",
                    "message": "The email data does not contain any attachments",
                    "timestamp": datetime.now().isoformat()
                }
            
            # Create output directory if it doesn't exist
            try:
                os.makedirs(output_dir, exist_ok=True)
            except Exception as e:
                return {
                    "success": False,
                    "error": f"Failed to create output directory: {str(e)}",
                    "message": f"Cannot create directory: {output_dir}",
                    "timestamp": datetime.now().isoformat()
                }
            
            # Process each attachment
            extracted_files = []
            errors = []
            
            for i, attachment in enumerate(attachments):
                try:
                    filename = attachment.get("filename", f"attachment_{i}")
                    content_base64 = attachment.get("content_base64", "")
                    content_type = attachment.get("content_type", "application/octet-stream")
                    size = attachment.get("size", 0)
                    
                    if not content_base64:
                        errors.append(f"Attachment '{filename}': No base64 content found")
                        continue
                    
                    # Sanitize filename to prevent directory traversal
                    safe_filename = self._sanitize_filename(filename)
                    file_path = os.path.join(output_dir, safe_filename)
                    
                    # Check if file exists and handle overwrite setting
                    if os.path.exists(file_path) and not overwrite:
                        # Generate unique filename
                        name, ext = os.path.splitext(safe_filename)
                        counter = 1
                        while os.path.exists(file_path):
                            new_filename = f"{name}_{counter}{ext}"
                            file_path = os.path.join(output_dir, new_filename)
                            counter += 1
                        safe_filename = os.path.basename(file_path)
                    
                    # Decode base64 content
                    try:
                        file_content = base64.b64decode(content_base64)
                    except Exception as decode_error:
                        errors.append(f"Attachment '{filename}': Base64 decode error - {str(decode_error)}")
                        continue
                    
                    # Write file
                    try:
                        with open(file_path, 'wb') as f:
                            f.write(file_content)
                        
                        # Verify file size
                        actual_size = len(file_content)
                        
                        extracted_files.append({
                            "original_filename": filename,
                            "saved_filename": safe_filename,
                            "file_path": file_path,
                            "content_type": content_type,
                            "original_size": size,
                            "actual_size": actual_size,
                            "size_match": actual_size == size
                        })
                        
                    except Exception as write_error:
                        errors.append(f"Attachment '{filename}': Write error - {str(write_error)}")
                        continue
                        
                except Exception as att_error:
                    errors.append(f"Attachment {i}: Processing error - {str(att_error)}")
                    continue
            
            # Prepare result
            result = {
                "success": len(extracted_files) > 0,
                "extracted_count": len(extracted_files),
                "total_attachments": len(attachments),
                "output_directory": output_dir,
                "extracted_files": extracted_files,
                "timestamp": datetime.now().isoformat()
            }
            
            if errors:
                result["errors"] = errors
                result["error_count"] = len(errors)
            
            if len(extracted_files) == 0:
                result["error"] = "No attachments could be extracted"
                result["message"] = "All attachment extractions failed"
            elif errors:
                result["message"] = f"Extracted {len(extracted_files)} files with {len(errors)} errors"
            else:
                result["message"] = f"Successfully extracted {len(extracted_files)} attachment files"
            
            return result
            
        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to extract attachments: {self._safe_text(str(e))}",
                "message": "An unexpected error occurred during attachment extraction",
                "timestamp": datetime.now().isoformat()
            }
    
    def _sanitize_filename(self, filename: str) -> str:
        """Sanitize filename to prevent security issues."""
        if not filename:
            return "unnamed_attachment"
        
        import re
        
        # Remove any path separators to prevent directory traversal
        safe_filename = os.path.basename(filename)
        
        # Remove or replace dangerous characters
        safe_filename = re.sub(r'[<>:"/\\|?*]', '_', safe_filename)
        
        # Remove control characters
        safe_filename = re.sub(r'[\x00-\x1f\x7f]', '', safe_filename)
        
        # Limit filename length
        if len(safe_filename) > 255:
            name, ext = os.path.splitext(safe_filename)
            safe_filename = name[:255-len(ext)] + ext
        
        # Ensure filename is not empty after sanitization
        if not safe_filename.strip():
            return "unnamed_attachment"
        
        return safe_filename.strip()
    
    def _clean_json_content(self, content: str) -> str:
        """
        Clean JSON content by checking if it starts with '{' and ends with '}'.
        If not, remove the first line (if doesn't start with '{') and/or 
        the last line (if doesn't end with '}').
        
        Args:
            content: Raw file content that may contain non-JSON lines
            
        Returns:
            Cleaned content that should be valid JSON
        """
        if not content or not content.strip():
            return content
        
        lines = content.splitlines()
        if not lines:
            return content
        
        # Check if first line starts with '{', if not remove it
        if lines and not lines[0].strip().startswith('{'):
            lines = lines[1:]
            logger.info("Removed first line as it doesn't start with '{'")
        
        # Check if last line ends with '}', if not remove it
        if lines and not lines[-1].strip().endswith('}'):
            lines = lines[:-1]
            logger.info("Removed last line as it doesn't end with '}'")
        
        # Return cleaned content
        return '\n'.join(lines)
    
    async def run_stdio(self):
        """Run the MCP server using stdio."""
        logger.info("Starting Email IMAP MCP Server with stdio")
        
        # Log detailed email configuration status
        logger.info("[SERVER_CONFIG] Email IMAP MCP Server configuration:")
        logger.info(f"[SERVER_CONFIG]   Server: {self.email_config.server}")
        logger.info(f"[SERVER_CONFIG]   Port: {self.email_config.port}")
        logger.info(f"[SERVER_CONFIG]   Username: {self.email_config.username}")
        logger.info(f"[SERVER_CONFIG]   Password: {'SET' if self.email_config.password else 'NOT SET'}")
        logger.info(f"[SERVER_CONFIG]   Use SSL: {self.email_config.use_ssl}")
        logger.info(f"[SERVER_CONFIG]   Timeout: {self.email_config.timeout}s")
        
        if self.email_config.server and self.email_config.username:
            logger.info(f"[SERVER_CONFIG] Email IMAP fully configured: {self.email_config.server}:{self.email_config.port} ({self.email_config.username})")
        else:
            logger.warning("[SERVER_CONFIG] Email IMAP configuration incomplete - functionality will be limited")
        
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
            # Disconnect from email server
            await self.email_client.disconnect()
            logger.info("Email IMAP MCP Server stopped")


def load_env_config():
    """Load environment configuration from .env.mcp file."""
    env_file = Path(__file__).parent.parent / ".env.mcp"
    
    logger.info(f"[ENV_LOAD] Attempting to load environment from: {env_file}")
    logger.info(f"[ENV_LOAD] File exists: {env_file.exists()}")
    logger.info(f"[ENV_LOAD] DOTENV_AVAILABLE: {DOTENV_AVAILABLE}")
    
    if DOTENV_AVAILABLE and env_file.exists():
        logger.info(f"[ENV_LOAD] Loading environment from: {env_file}")
        # Load with override=True to ensure .env.mcp values take precedence
        load_dotenv(env_file, override=True)
        
        # Log what was loaded for debugging
        with open(env_file, 'r') as f:
            content = f.read()
            logger.debug(f"[ENV_LOAD] .env.mcp content:")
            for line_num, line in enumerate(content.splitlines(), 1):
                if line.strip() and not line.strip().startswith('#'):
                    if 'PASSWORD' in line:
                        # Hide password values in logs
                        key_part = line.split('=')[0]
                        logger.debug(f"[ENV_LOAD]   Line {line_num}: {key_part}=***")
                    else:
                        logger.debug(f"[ENV_LOAD]   Line {line_num}: {line}")
        
        logger.info(f"[ENV_LOAD] Successfully loaded environment from .env.mcp")
    elif env_file.exists():
        logger.warning(f"[ENV_LOAD] Found {env_file} but python-dotenv not available. Install with: pip install python-dotenv")
    else:
        logger.warning(f"[ENV_LOAD] No .env.mcp file found at: {env_file}")


async def main():
    """Main entry point."""
    import argparse
    
    # Load environment configuration first
    load_env_config()
    
    # Log environment variables for debugging
    logger.info("[ENV_DEBUG] Environment variables after loading .env.mcp:")
    logger.info(f"[ENV_DEBUG]   EMAIL_IMAP_SERVER: {os.getenv('EMAIL_IMAP_SERVER', 'NOT SET')}")
    logger.info(f"[ENV_DEBUG]   EMAIL_IMAP_PORT_IMAP: {os.getenv('EMAIL_IMAP_PORT_IMAP', 'NOT SET (default: 993)')}")
    logger.info(f"[ENV_DEBUG]   EMAIL_USERNAME: {os.getenv('EMAIL_USERNAME', 'NOT SET')}")
    logger.info(f"[ENV_DEBUG]   EMAIL_PASSWORD: {'SET (' + str(len(os.getenv('EMAIL_PASSWORD', ''))) + ' chars)' if os.getenv('EMAIL_PASSWORD') else 'NOT SET'}")
    logger.info(f"[ENV_DEBUG]   EMAIL_TIMEOUT: {os.getenv('EMAIL_TIMEOUT', 'NOT SET (default: 60)')}")
    
    # Validate critical IMAP configuration
    missing_config = []
    if not os.getenv('EMAIL_IMAP_SERVER'):
        missing_config.append('EMAIL_IMAP_SERVER')
    if not os.getenv('EMAIL_USERNAME'):
        missing_config.append('EMAIL_USERNAME')
    if not os.getenv('EMAIL_PASSWORD'):
        missing_config.append('EMAIL_PASSWORD')
        
    if missing_config:
        logger.error(f"[ENV_DEBUG] Missing critical IMAP configuration: {', '.join(missing_config)}")
        logger.error(f"[ENV_DEBUG] Please check .env.mcp file and ensure these variables are set")
    else:
        logger.info(f"[ENV_DEBUG] All critical IMAP configuration variables are set")
    
    parser = argparse.ArgumentParser(description="Email IMAP MCP Server (stdio)")
    
    # Email IMAP configuration (read from environment by default)
    parser.add_argument("--server", default=os.getenv("EMAIL_IMAP_SERVER"), help="IMAP server hostname")
    parser.add_argument("--imap-port", type=int, default=int(os.getenv("EMAIL_IMAP_PORT_IMAP", "993")), help="IMAP server port")
    parser.add_argument("--username", default=os.getenv("EMAIL_USERNAME"), help="Email username")
    parser.add_argument("--password", default=os.getenv("EMAIL_PASSWORD"), help="Email password")
    parser.add_argument("--no-ssl", action="store_true", help="Disable SSL/TLS")
    parser.add_argument("--timeout", type=int, default=int(os.getenv("EMAIL_TIMEOUT", "60")), help="Connection timeout (default: 60s for better compatibility with slower IMAP servers)")
    
    args = parser.parse_args()
    
    # Log parsed arguments for debugging
    logger.info("[ARGS_DEBUG] Parsed arguments:")
    logger.info(f"[ARGS_DEBUG]   server: {args.server}")
    logger.info(f"[ARGS_DEBUG]   imap_port: {args.imap_port}")
    logger.info(f"[ARGS_DEBUG]   username: {args.username}")
    logger.info(f"[ARGS_DEBUG]   password: {'SET' if args.password else 'NOT SET'}")
    logger.info(f"[ARGS_DEBUG]   no_ssl: {args.no_ssl}")
    logger.info(f"[ARGS_DEBUG]   timeout: {args.timeout}")
    
    # Validate required email parameters
    if not args.server or not args.username or not args.password:
        logger.warning("Missing email configuration - some functionality will be limited")
        logger.info("Set EMAIL_IMAP_SERVER, EMAIL_USERNAME, EMAIL_PASSWORD in .env.mcp for full functionality")
    
    # Create email configuration
    email_config = EmailConfig(
        server=args.server or "",
        port=args.imap_port,
        username=args.username or "",
        password=args.password or "",
        use_ssl=not args.no_ssl,
        timeout=args.timeout
    )
    
    # Create and start server
    server = EmailIMAPMCPServer(email_config=email_config)
    
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
