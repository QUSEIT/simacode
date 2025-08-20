#!/usr/bin/env python3
"""
Email IMAP MCP Server (HTTP/WebSocket)

A HTTP-based MCP server that provides IMAP email checking and retrieval functionality.
It communicates with SimaCode via HTTP/WebSocket protocol and provides email automation
capabilities including checking for new emails, retrieving email content, and handling attachments.

Features:
- HTTP-based MCP server with WebSocket support
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
except ImportError:
    DOTENV_AVAILABLE = False
    print("Warning: python-dotenv not available. Consider installing with: pip install python-dotenv", file=sys.stderr)

# HTTP server support
try:
    from aiohttp import web, WSMsgType
    from aiohttp.web import Request, Response, WebSocketResponse
except ImportError:
    print("Error: aiohttp package not available. Please install with: pip install aiohttp", file=sys.stderr)
    sys.exit(1)

# Add parent directory to path for MCP imports
sys.path.insert(0, str(Path(__file__).parent.parent))

# MCP Protocol imports (using our existing MCP implementation)
from src.simacode.mcp.protocol import MCPMessage, MCPMethods, MCPErrorCodes


# Configure logging
logging.basicConfig(
    level=logging.INFO,
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
    timeout: int = 30


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
        
    async def connect(self) -> bool:
        """
        Connect to IMAP server.
        
        Returns:
            bool: True if connection successful, False otherwise
        """
        try:
            logger.info(f"Connecting to IMAP server: {self.config.server}:{self.config.port}")
            
            if self.config.use_ssl:
                self.connection = imaplib.IMAP4_SSL(
                    self.config.server, 
                    self.config.port,
                    timeout=self.config.timeout
                )
            else:
                self.connection = imaplib.IMAP4(
                    self.config.server,
                    self.config.port,
                    timeout=self.config.timeout
                )
            
            # Login
            result = self.connection.login(self.config.username, self.config.password)
            
            if result[0] == 'OK':
                self.last_connect_time = datetime.now()
                logger.info("Successfully connected and authenticated to IMAP server")
                return True
            else:
                logger.error(f"Failed to authenticate: {result[1]}")
                return False
                
        except Exception as e:
            logger.error(f"Failed to connect to IMAP server: {str(e)}")
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
        # Check if we have a connection and it's recent
        if self.connection and self.last_connect_time:
            time_since_connect = datetime.now() - self.last_connect_time
            if time_since_connect.total_seconds() < 300:  # 5 minutes
                try:
                    # Test connection with NOOP
                    result = self.connection.noop()
                    if result[0] == 'OK':
                        return True
                except:
                    pass
        
        # Reconnect if needed
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
        if not await self.ensure_connection():
            raise Exception("Failed to connect to IMAP server")
        
        try:
            result, data = self.connection.select(folder)
            if result != 'OK':
                raise Exception(f"Failed to select folder '{folder}': {data}")
            
            self.current_folder = folder
            message_count = int(data[0])
            
            return {
                "folder": folder,
                "message_count": message_count,
                "selected": True
            }
            
        except Exception as e:
            logger.error(f"Error selecting folder '{folder}': {str(e)}")
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
        if not await self.ensure_connection():
            raise Exception("Failed to connect to IMAP server")
        
        try:
            result, data = self.connection.search(None, criteria)
            if result != 'OK':
                raise Exception(f"Search failed: {data}")
            
            uids = data[0].split()
            uids = uids[-limit:] if len(uids) > limit else uids
            uids.reverse()
            
            return [uid.decode('utf-8') for uid in uids]
            
        except Exception as e:
            logger.error(f"Error searching emails: {str(e)}")
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
    
    async def fetch_email(self, uid: str) -> EmailMessage:
        """
        Fetch email message by UID.
        
        Args:
            uid: Email UID
            
        Returns:
            EmailMessage object
        """
        if not await self.ensure_connection():
            raise Exception("Failed to connect to IMAP server")
        
        try:
            result, data = self.connection.fetch(uid, '(RFC822 FLAGS)')
            if result != 'OK':
                raise Exception(f"Failed to fetch email {uid}: {data}")
            
            raw_email = data[0][1]
            email_message = email.message_from_bytes(raw_email)
            
            subject = self._decode_header(email_message.get('Subject', ''))
            sender = self._decode_header(email_message.get('From', ''))
            recipient = self._decode_header(email_message.get('To', ''))
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
            logger.error(f"Error fetching email {uid}: {str(e)}")
            raise


class EmailIMAPMCPServer:
    """
    HTTP-based MCP server for IMAP email integration.
    
    This server provides MCP protocol compliance over HTTP/WebSocket and integrates
    with IMAP email servers for email automation tasks.
    """
    
    def __init__(self, host: str = "0.0.0.0", port: int = 8081, email_config: Optional[EmailConfig] = None):
        """
        Initialize Email IMAP MCP server.
        
        Args:
            host: Server host address
            port: Server port number
            email_config: Email IMAP configuration
        """
        self.host = host
        self.port = port
        self.app = web.Application()
        
        # Initialize email client with configuration
        self.email_config = email_config or EmailConfig()
        self.email_client = IMAPEmailClient(self.email_config)
        
        # Setup routes
        self._setup_routes()
        
        # MCP server info
        self.server_info = {
            "name": "email-imap-mcp-server",
            "version": "1.0.0",
            "description": "Email IMAP MCP Server for Email Automation"
        }
        
        # Available tools
        self.tools = {
            "list_folders": {
                "name": "list_folders",
                "description": "List available email folders/mailboxes",
                "input_schema": {
                    "type": "object",
                    "properties": {}
                }
            },
            "check_emails": {
                "name": "check_emails",
                "description": "Check for emails in a folder with optional filtering",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "folder": {
                            "type": "string",
                            "description": "Email folder to check (default: INBOX)",
                            "default": "INBOX"
                        },
                        "criteria": {
                            "type": "string",
                            "description": "IMAP search criteria (e.g., 'UNSEEN', 'FROM sender@email.com')",
                            "default": "ALL"
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Maximum number of emails to return",
                            "default": 10
                        }
                    }
                }
            },
            "get_email": {
                "name": "get_email",
                "description": "Get specific email by UID with optional attachments",
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
                            "description": "Include attachment data in Base64 format",
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
                        "include_attachments": {
                            "type": "boolean",
                            "description": "Include attachment content in base64 format",
                            "default": True
                        }
                    }
                }
            },
            "save_latest_email_json": {
                "name": "save_latest_email_json",
                "description": "Get the latest email and save it as a pure JSON file",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "filename": {
                            "type": "string",
                            "description": "Output filename (default: mail.json)",
                            "default": "mail.json"
                        },
                        "folder": {
                            "type": "string",
                            "description": "Email folder to check (default: INBOX)",
                            "default": "INBOX"
                        },
                        "days": {
                            "type": "integer",
                            "description": "Number of days back to search (default: 7)",
                            "default": 7
                        },
                        "include_attachments": {
                            "type": "boolean",
                            "description": "Whether to include attachment content with base64 data (default: true)",
                            "default": True
                        }
                    }
                }
            }
        }
        
        logger.info(f"Email IMAP MCP Server initialized on {host}:{port}")
    
    def _setup_routes(self):
        """Setup HTTP routes for MCP protocol."""
        self.app.router.add_get('/health', self._health_check)
        self.app.router.add_post('/mcp', self._handle_mcp_request)
        self.app.router.add_get('/mcp/ws', self._handle_websocket)
        
    async def _health_check(self, request: Request) -> Response:
        """Health check endpoint."""
        # Test email connection
        connection_status = "disconnected"
        try:
            connected = await self.email_client.ensure_connection()
            connection_status = "connected" if connected else "failed"
            await self.email_client.disconnect()
        except Exception as e:
            connection_status = f"error: {str(e)}"
        
        health_data = {
            "status": "healthy",
            "server": self.server_info,
            "email_config": {
                "server": self.email_config.server,
                "port": self.email_config.port,
                "username": self.email_config.username,
                "use_ssl": self.email_config.use_ssl,
                "connection_status": connection_status
            },
            "timestamp": datetime.now().isoformat()
        }
            
        return web.json_response(health_data)
    
    async def _handle_mcp_request(self, request: Request) -> Response:
        """Handle HTTP-based MCP requests."""
        try:
            request_data = await request.json()
            mcp_message = MCPMessage.from_dict(request_data)
            
            logger.info(f"Received MCP request: {mcp_message.method}")
            
            response = await self._process_mcp_message(mcp_message)
            
            if response is None:
                return web.Response(status=204)
            
            return web.json_response(response.to_dict())
            
        except Exception as e:
            logger.error(f"Error handling MCP request: {str(e)}")
            
            error_response = MCPMessage(
                id=request_data.get("id") if 'request_data' in locals() else None,
                error={
                    "code": MCPErrorCodes.INTERNAL_ERROR,
                    "message": str(e)
                }
            )
            
            return web.json_response(error_response.to_dict())
    
    async def _handle_websocket(self, request: Request) -> WebSocketResponse:
        """Handle WebSocket-based MCP connections."""
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        
        logger.info("WebSocket connection established")
        
        try:
            async for msg in ws:
                if msg.type == WSMsgType.TEXT:
                    try:
                        request_data = json.loads(msg.data)
                        mcp_message = MCPMessage.from_dict(request_data)
                        
                        response = await self._process_mcp_message(mcp_message)
                        
                        if response is not None:
                            await ws.send_str(response.to_json())
                        
                    except Exception as e:
                        logger.error(f"Error processing WebSocket message: {str(e)}")
                        
                        request_id = None
                        try:
                            if 'request_data' in locals():
                                request_id = request_data.get("id")
                        except:
                            pass
                        
                        error_response = MCPMessage(
                            id=request_id,
                            error={
                                "code": MCPErrorCodes.INTERNAL_ERROR,
                                "message": str(e)
                            }
                        )
                        
                        await ws.send_str(error_response.to_json())
                        
                elif msg.type == WSMsgType.ERROR:
                    logger.error(f"WebSocket error: {ws.exception()}")
                    break
                    
        except Exception as e:
            logger.error(f"WebSocket connection error: {str(e)}")
        finally:
            logger.info("WebSocket connection closed")
            
        return ws
    
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
        try:
            params = message.params or {}
            tool_name = params.get("name")
            arguments = params.get("arguments", {})
            
            if tool_name not in self.tools:
                return MCPMessage(
                    id=message.id,
                    error={
                        "code": MCPErrorCodes.TOOL_NOT_FOUND,
                        "message": f"Tool '{tool_name}' not found"
                    }
                )
            
            start_time = asyncio.get_event_loop().time()
            
            if tool_name == "list_folders":
                result = await self._list_folders(arguments)
            elif tool_name == "check_emails":
                result = await self._check_emails(arguments)
            elif tool_name == "get_email":
                result = await self._get_email(arguments)
            elif tool_name == "get_recent_emails":
                result = await self._get_recent_emails_json(arguments)
            elif tool_name == "save_latest_email_json":
                result = await self._save_latest_email_json(arguments)
            else:
                raise ValueError(f"Unknown tool: {tool_name}")
            
            execution_time = asyncio.get_event_loop().time() - start_time
            
            # Ensure all content in result is safe for JSON serialization
            safe_result = self._ensure_json_safe(result)
            
            # Special handling for get_recent_emails to return pure email data
            if tool_name == "get_recent_emails":
                # Check if result is an error (dict with "error" key) or success (list/dict without error)
                is_error = isinstance(safe_result, dict) and safe_result.get("error") is not None
                
                if not is_error:
                    # For successful email retrieval, return only the email data without MCP wrapper
                    return MCPMessage(
                        id=message.id,
                        result={
                            "content": [
                                {
                                    "type": "text", 
                                    "text": json.dumps(safe_result, indent=2, ensure_ascii=False)
                                }
                            ]
                        }
                    )
                else:
                    # For errors, still use the standard error format
                    return MCPMessage(
                        id=message.id,
                        result={
                            "content": [
                                {
                                    "type": "text",
                                    "text": json.dumps(safe_result, indent=2, ensure_ascii=False)
                                }
                            ],
                            "isError": True
                        }
                    )
            
            return MCPMessage(
                id=message.id,
                result={
                    "content": [
                        {
                            "type": "text",
                            "text": json.dumps(safe_result, indent=2, ensure_ascii=False)
                        }
                    ],
                    "isError": not safe_result.get("success", True),
                    "metadata": {
                        "execution_time": execution_time,
                        "tool": tool_name
                    }
                }
            )
            
        except Exception as e:
            logger.error(f"Tool execution error: {str(e)}")
            
            return MCPMessage(
                id=message.id,
                error={
                    "code": MCPErrorCodes.INTERNAL_ERROR,
                    "message": str(e)
                }
            )
    
    async def _list_folders(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """List email folders."""
        try:
            folders = await self.email_client.list_folders()
            
            return {
                "success": True,
                "folders": folders,
                "count": len(folders),
                "timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to list folders: {str(e)}",
                "timestamp": datetime.now().isoformat()
            }
        finally:
            await self.email_client.disconnect()
    
    async def _check_emails(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Check for emails in folder."""
        try:
            folder = arguments.get("folder", "INBOX")
            criteria = arguments.get("criteria", "ALL")
            limit = arguments.get("limit", 10)
            
            folder_info = await self.email_client.select_folder(folder)
            uids = await self.email_client.search_emails(criteria, limit)
            
            emails = []
            for uid in uids:
                try:
                    email_msg = await self.email_client.fetch_email(uid)
                    emails.append({
                        "uid": email_msg.uid,
                        "subject": email_msg.subject,
                        "sender": email_msg.sender,
                        "date": email_msg.date,
                        "size": email_msg.size,
                        "flags": email_msg.flags,
                        "has_attachments": len(email_msg.attachments) > 0
                    })
                except Exception as e:
                    logger.error(f"Error fetching email {uid}: {str(e)}")
                    continue
            
            return {
                "success": True,
                "folder": folder,
                "folder_info": folder_info,
                "search_criteria": criteria,
                "emails": emails,
                "count": len(emails),
                "timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to check emails: {str(e)}",
                "timestamp": datetime.now().isoformat()
            }
        finally:
            await self.email_client.disconnect()
    
    def _safe_text(self, text: Any) -> str:
        """Safely convert text to string, handling encoding issues."""
        if text is None:
            return ""
        
        if isinstance(text, str):
            # Ensure the string is properly encoded for JSON
            return text.encode('utf-8', errors='ignore').decode('utf-8')
        else:
            # Convert to string and then safely encode
            return str(text).encode('utf-8', errors='ignore').decode('utf-8')
    
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
            include_attachments = arguments.get("include_attachments", False)
            
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
                "subject": self._safe_text(email_msg.subject),
                "sender": self._safe_text(email_msg.sender),
                "recipient": self._safe_text(email_msg.recipient),
                "date": self._safe_text(email_msg.date),
                "body_text": self._safe_text(email_msg.body_text),
                "body_html": self._safe_text(email_msg.body_html),
                "headers": {k: self._safe_text(v) for k, v in email_msg.headers.items()},
                "size": email_msg.size,
                "flags": email_msg.flags,
                "attachments": [],
                "timestamp": datetime.now().isoformat()
            }
            
            if include_attachments:
                # Safely process attachments with base64 content
                safe_attachments = []
                for att in email_msg.attachments:
                    safe_att = {
                        "filename": self._safe_text(att.get("filename", "")),
                        "content_type": self._safe_text(att.get("content_type", "")),
                        "size": att.get("size", 0),
                        "content_base64": att.get("content_base64", "")
                    }
                    safe_attachments.append(safe_att)
                result["attachments"] = safe_attachments
            else:
                # Just include attachment metadata without content
                for att in email_msg.attachments:
                    result["attachments"].append({
                        "filename": self._safe_text(att.get("filename", "")),
                        "content_type": self._safe_text(att.get("content_type", "")),
                        "size": att.get("size", 0)
                    })
            
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
        try:
            folder = arguments.get("folder", "INBOX")
            days = arguments.get("days", 7)
            limit = arguments.get("limit", 1)
            include_attachments = arguments.get("include_attachments", True)
            
            await self.email_client.select_folder(folder)
            
            since_date = (datetime.now() - timedelta(days=days)).strftime("%d-%b-%Y")
            criteria = f"SINCE {since_date}"
            
            uids = await self.email_client.search_emails(criteria, limit)
            
            if not uids:
                return {
                    "error": "No emails found",
                    "message": "No recent emails found in the specified time range"
                }
            
            # Get the requested number of emails (up to limit)
            emails_data = []
            
            for uid in uids[:limit]:  # Process up to 'limit' emails
                try:
                    email_msg = await self.email_client.fetch_email(uid)
                    
                    # Create email JSON data
                    email_data = {
                        "uid": str(email_msg.uid),
                        "subject": self._safe_text(email_msg.subject),
                        "sender": self._safe_text(email_msg.sender),
                        "recipient": self._safe_text(email_msg.recipient),
                        "date": self._safe_text(email_msg.date),
                        "body_text": self._safe_text(email_msg.body_text),
                        "body_html": self._safe_text(email_msg.body_html),
                        "size": email_msg.size,
                        "flags": email_msg.flags,
                        "attachments": []
                    }
                    
                    # Process attachments
                    if include_attachments:
                        # Include full attachment data with base64 content
                        for att in email_msg.attachments:
                            safe_att = {
                                "filename": self._safe_text(att.get("filename", "")),
                                "content_type": self._safe_text(att.get("content_type", "")),
                                "size": att.get("size", 0),
                                "content_base64": att.get("content_base64", "")
                            }
                            email_data["attachments"].append(safe_att)
                    else:
                        # Include only attachment metadata
                        for att in email_msg.attachments:
                            email_data["attachments"].append({
                                "filename": self._safe_text(att.get("filename", "")),
                                "content_type": self._safe_text(att.get("content_type", "")),
                                "size": att.get("size", 0)
                            })
                    
                    emails_data.append(email_data)
                    
                except Exception as e:
                    # Log error but continue processing other emails
                    logger.error(f"Error processing email {uid}: {str(e)}")
                    continue
            
            # Return single email if limit is 1, otherwise return array
            if limit == 1 and emails_data:
                return emails_data[0]
            else:
                return emails_data
            
        except Exception as e:
            return {
                "error": f"Failed to get recent emails: {self._safe_text(str(e))}",
                "message": "An error occurred while retrieving email data"
            }
        finally:
            await self.email_client.disconnect()
    
    async def _save_latest_email_json(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Get the latest email and save it as pure JSON file."""
        try:
            filename = arguments.get("filename", "mail.json")
            folder = arguments.get("folder", "INBOX")
            days = arguments.get("days", 7)
            include_attachments = arguments.get("include_attachments", True)
            
            # Get the latest email using the existing method
            email_json_result = await self._get_recent_emails_json({
                "folder": folder,
                "days": days,
                "limit": 1,
                "include_attachments": include_attachments
            })
            
            # Check if we got email data successfully
            if "error" in email_json_result:
                return {
                    "success": False,
                    "error": email_json_result["error"],
                    "message": email_json_result.get("message", "Failed to retrieve email"),
                    "timestamp": datetime.now().isoformat()
                }
            
            # Write the pure email JSON to file
            try:
                with open(filename, 'w', encoding='utf-8') as f:
                    json.dump(email_json_result, f, ensure_ascii=False, indent=2)
                
                return {
                    "success": True,
                    "message": f"Latest email saved to {filename}",
                    "filename": filename,
                    "email_summary": {
                        "uid": email_json_result.get("uid"),
                        "subject": email_json_result.get("subject"),
                        "sender": email_json_result.get("sender"),
                        "date": email_json_result.get("date"),
                        "size": email_json_result.get("size"),
                        "attachments_count": len(email_json_result.get("attachments", []))
                    },
                    "timestamp": datetime.now().isoformat()
                }
                
            except Exception as file_error:
                return {
                    "success": False,
                    "error": f"Failed to save file: {str(file_error)}",
                    "message": "Email was retrieved but could not be saved to file",
                    "timestamp": datetime.now().isoformat()
                }
                
        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to save latest email JSON: {self._safe_text(str(e))}",
                "message": "An error occurred while processing the request",
                "timestamp": datetime.now().isoformat()
            }
        finally:
            await self.email_client.disconnect()
    
    async def start_server(self):
        """Start the HTTP server."""
        logger.info(f"Starting Email IMAP MCP Server on {self.host}:{self.port}")
        
        # Log email configuration status
        if self.email_config.server and self.email_config.username:
            logger.info(f"Email IMAP configured: {self.email_config.server}:{self.email_config.port} ({self.email_config.username})")
        else:
            logger.warning("Email IMAP configuration incomplete - functionality will be limited")
        
        runner = web.AppRunner(self.app)
        await runner.setup()
        
        site = web.TCPSite(runner, self.host, self.port)
        await site.start()
        
        logger.info(f"Email IMAP MCP Server started successfully")
        logger.info(f"Health check: http://{self.host}:{self.port}/health")
        logger.info(f"MCP HTTP endpoint: http://{self.host}:{self.port}/mcp")
        logger.info(f"MCP WebSocket endpoint: ws://{self.host}:{self.port}/mcp/ws")
        
        return runner
    
    async def stop_server(self, runner):
        """Stop the HTTP server."""
        logger.info("Shutting down Email IMAP MCP Server...")
        
        # Disconnect from email server
        await self.email_client.disconnect()
        
        # Stop HTTP server
        await runner.cleanup()
        logger.info("Email IMAP MCP Server stopped")


def load_env_config():
    """Load environment configuration from .env.mcp file."""
    env_file = Path(__file__).parent.parent / ".env.mcp"
    
    if DOTENV_AVAILABLE and env_file.exists():
        logger.info(f"Loading environment from: {env_file}")
        load_dotenv(env_file)
    elif env_file.exists():
        logger.warning(f"Found {env_file} but python-dotenv not available. Install with: pip install python-dotenv")
    else:
        logger.info(f"No .env.mcp file found at: {env_file}")


async def main():
    """Main entry point."""
    import argparse
    
    # Load environment configuration first
    load_env_config()
    
    parser = argparse.ArgumentParser(description="Email IMAP MCP Server (HTTP/WebSocket)")
    parser.add_argument("--host", default=os.getenv("EMAIL_IMAP_HOST", "0.0.0.0"), help="Server host address")
    parser.add_argument("--port", type=int, default=int(os.getenv("EMAIL_IMAP_PORT", "8081")), help="Server port number")
    
    # Email IMAP configuration (read from environment by default)
    parser.add_argument("--server", default=os.getenv("EMAIL_IMAP_SERVER"), help="IMAP server hostname")
    parser.add_argument("--imap-port", type=int, default=int(os.getenv("EMAIL_IMAP_PORT_IMAP", "993")), help="IMAP server port")
    parser.add_argument("--username", default=os.getenv("EMAIL_USERNAME"), help="Email username")
    parser.add_argument("--password", default=os.getenv("EMAIL_PASSWORD"), help="Email password")
    parser.add_argument("--no-ssl", action="store_true", help="Disable SSL/TLS")
    parser.add_argument("--timeout", type=int, default=int(os.getenv("EMAIL_TIMEOUT", "30")), help="Connection timeout")
    
    args = parser.parse_args()
    
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
    server = EmailIMAPMCPServer(host=args.host, port=args.port, email_config=email_config)
    
    runner = await server.start_server()
    
    try:
        # Keep server running
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        logger.info("Shutting down server...")
    except asyncio.CancelledError:
        logger.info("Server cancelled, shutting down...")
    finally:
        await server.stop_server(runner)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nServer stopped by user.")
    except Exception as e:
        print(f"Server error: {e}")
        sys.exit(1)
