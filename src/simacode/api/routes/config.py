"""
Configuration API routes for SimaCode API service.

This module provides endpoints for retrieving configuration information.
"""

import logging
from pathlib import Path
from typing import Any, Dict

from fastapi import APIRouter, Depends

from ..dependencies import get_config
from ..models import ConfigResponse
from ...config import Config

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/", response_model=ConfigResponse)
async def get_configuration(config: Config = Depends(get_config)):
    """
    Get current configuration information including config file path and settings.

    Returns:
        ConfigResponse: Configuration file path and current settings
    """
    project_root = Path.cwd()
    project_config_path = project_root / ".simacode" / "config.yaml"

    # Check if config file exists
    config_exists = project_config_path.exists()
    config_file_path = str(project_config_path) if config_exists else None

    # Get current configuration as dict (excluding sensitive data)
    config_dict = config.model_dump(mode="json")

    # Remove sensitive information
    if "ai" in config_dict and "api_key" in config_dict["ai"]:
        config_dict["ai"]["api_key"] = "***HIDDEN***" if config_dict["ai"]["api_key"] else None

    if "email" in config_dict:
        email_config = config_dict["email"]
        if "smtp" in email_config:
            if "password" in email_config["smtp"]:
                email_config["smtp"]["password"] = "***HIDDEN***" if email_config["smtp"]["password"] else None
        if "imap" in email_config:
            if "password" in email_config["imap"]:
                email_config["imap"]["password"] = "***HIDDEN***" if email_config["imap"]["password"] else None

    logger.debug(f"Configuration requested - config file exists: {config_exists}, path: {config_file_path}")

    return ConfigResponse(
        config_file_path=config_file_path,
        config_exists=config_exists,
        project_root=str(project_root),
        config_data=config_dict
    )