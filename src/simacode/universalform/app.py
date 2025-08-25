"""
Universal Form Generator API routes.

This module handles the universal form generator endpoints for:
- Serving the form builder/preview HTML interface
- Loading and saving form configurations
- Handling form submissions
"""

import json
import logging
import os
from pathlib import Path
from typing import Dict, Any, Optional

try:
    from fastapi import APIRouter, Request, HTTPException, Query
    from fastapi.responses import HTMLResponse, JSONResponse
    from fastapi.templating import Jinja2Templates
    from pydantic import BaseModel
    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False
    APIRouter = None
    Request = None
    HTTPException = None
    BaseModel = None

logger = logging.getLogger(__name__)

if FASTAPI_AVAILABLE:
    router = APIRouter()

    class FormField(BaseModel):
        key: str
        label: str
        type: str
        placeholder: Optional[str] = ""
        options: Optional[str] = ""
        required: bool = False

    class FormConfig(BaseModel):
        name: Optional[str] = ""
        postUrl: Optional[str] = ""

    class UniversalFormData(BaseModel):
        fields: list[FormField]
        config: FormConfig

    # Path to universalform directory and config file
    UNIVERSALFORM_DIR = Path(__file__).parent
    # Config file should be in the current working directory where simacode serve is run
    CONFIG_FILE = Path.cwd() / "universalform.json"

    @router.get("/", response_class=HTMLResponse)
    async def get_universalform_page():
        """
        Serve the universal form generator HTML page.
        
        Returns:
            HTML page with form builder and preview functionality
        """
        try:
            html_file = UNIVERSALFORM_DIR / "index.html"
            if not html_file.exists():
                raise HTTPException(status_code=404, detail="Universal form page not found")
            
            with open(html_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            return HTMLResponse(content=content)
        
        except Exception as e:
            logger.error(f"Error serving universal form page: {str(e)}")
            raise HTTPException(status_code=500, detail="Internal server error")

    @router.get("/config")
    async def get_form_config():
        """
        Load form configuration from universalform.json.
        
        Returns:
            JSON configuration with fields and settings
        """
        try:
            if CONFIG_FILE.exists():
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                return JSONResponse(content=config)
            else:
                # Return default empty configuration
                default_config = {
                    "fields": [],
                    "config": {
                        "name": "",
                        "postUrl": ""
                    }
                }
                return JSONResponse(content=default_config)
        
        except Exception as e:
            logger.error(f"Error loading form configuration: {str(e)}")
            raise HTTPException(status_code=500, detail="Failed to load configuration")

    @router.post("/config")
    async def save_form_config(form_data: UniversalFormData):
        """
        Save form configuration to universalform.json.
        
        Args:
            form_data: Form configuration data including fields and settings
            
        Returns:
            Success response
        """
        try:
            # Ensure the config directory exists
            CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
            
            # Convert to dict for JSON serialization
            config_dict = {
                "fields": [field.model_dump() for field in form_data.fields],
                "config": form_data.config.model_dump()
            }
            
            # Save to file
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(config_dict, f, ensure_ascii=False, indent=2)
            
            logger.info(f"Form configuration saved to {CONFIG_FILE}")
            return JSONResponse(content={"message": "Configuration saved successfully"})
        
        except Exception as e:
            logger.error(f"Error saving form configuration: {str(e)}")
            raise HTTPException(status_code=500, detail="Failed to save configuration")

    @router.post("/submit")
    async def handle_form_submission(request: Request):
        """
        Handle form submission and forward to configured POST URL.
        
        Args:
            request: HTTP request containing form data
            
        Returns:
            Success/failure response
        """
        try:
            # Get form data from request
            form_data = await request.json()
            
            # Log the submission
            logger.info(f"Form submission received: {json.dumps(form_data, ensure_ascii=False, indent=2)}")
            
            # Load configuration to get POST URL
            post_url = None
            if CONFIG_FILE.exists():
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    post_url = config.get("config", {}).get("postUrl")
            
            if post_url:
                # Forward to configured URL
                import httpx
                async with httpx.AsyncClient() as client:
                    response = await client.post(post_url, json=form_data)
                    if response.status_code == 200:
                        return JSONResponse(content={"message": "Form submitted successfully", "status": "success"})
                    else:
                        logger.warning(f"Form submission failed with status {response.status_code}")
                        return JSONResponse(
                            status_code=response.status_code,
                            content={"message": f"Submission failed: HTTP {response.status_code}", "status": "error"}
                        )
            else:
                # No POST URL configured, just log and return success
                logger.info("No POST URL configured, form data logged only")
                return JSONResponse(content={"message": "Form data received and logged", "status": "success"})
        
        except Exception as e:
            logger.error(f"Error handling form submission: {str(e)}")
            raise HTTPException(status_code=500, detail="Failed to process form submission")

else:
    # Placeholder router for when FastAPI is not available
    class MockRouter:
        def get(self, *args, **kwargs):
            def decorator(func):
                return func
            return decorator
        
        def post(self, *args, **kwargs):
            def decorator(func):
                return func
            return decorator
    
    router = MockRouter()