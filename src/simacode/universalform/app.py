"""
Universal Form Generator API routes.

This module handles the universal form generator endpoints for:
- Serving the form builder/preview HTML interface
- Loading and saving form configurations
- Handling form submissions
"""

import base64
import json
import logging
import os
from pathlib import Path
from typing import Dict, Any, Optional, List

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

try:
    from ..ai.factory import AIClientFactory
    from ..ai.base import Message, Role
    from ..config import Config
    AI_CLIENT_AVAILABLE = True
except ImportError:
    AI_CLIENT_AVAILABLE = False

logger = logging.getLogger(__name__)

def get_ai_config() -> Optional[Dict[str, Any]]:
    """
    Get AI client configuration from project config file.
    
    Returns:
        AI configuration dictionary or None if not configured
    """
    try:
        if AI_CLIENT_AVAILABLE:
            # Load config from project .simacode/config.yaml
            config = Config.load()
            ai_config = config.ai
            
            if ai_config.api_key:
                client_config = {
                    "provider": ai_config.provider,
                    "api_key": ai_config.api_key,
                    "model": ai_config.model,
                    "temperature": ai_config.temperature,
                    "max_tokens": ai_config.max_tokens,
                    "timeout": ai_config.timeout
                }
                
                # Add base_url if configured
                if ai_config.base_url:
                    client_config["base_url"] = ai_config.base_url
                
                logger.debug("AI configuration loaded from config file")
                logger.debug(f"Provider: {ai_config.provider}, Model: {ai_config.model}")
                return client_config
            else:
                logger.debug("OpenAI API key not found in configuration")
    except Exception as e:
        logger.warning(f"Failed to load configuration: {str(e)}")
        
    return None

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
    async def get_universalform_page(
        formdata: Optional[str] = Query(None),
        m: Optional[str] = Query(None)
    ):
        """
        Serve the universal form generator HTML page.
        
        Args:
            formdata: Optional base64-encoded form data for pre-filling
            m: Optional mode parameter (m=1 enables multi-form mode by default)
        
        Returns:
            HTML page with form builder and preview functionality
        """
        logger.info("=== GET /universalform/ called ===")
        logger.info(f"Formdata parameter present: {bool(formdata)}")
        logger.info(f"Multi-form mode parameter (m): {m}")
        
        if formdata:
            logger.info(f"Formdata length: {len(formdata)}")
            logger.info(f"Formdata first 50 chars: {formdata[:50]}...")
        
        try:
            html_file = UNIVERSALFORM_DIR / "index.html"
            logger.debug(f"Looking for HTML file at: {html_file}")
            
            if not html_file.exists():
                logger.error(f"HTML file not found: {html_file}")
                raise HTTPException(status_code=404, detail="Universal form page not found")
            
            with open(html_file, 'r', encoding='utf-8') as f:
                content = f.read()
            logger.debug(f"HTML file loaded, length: {len(content)}")
            
            # If formdata parameter exists, process it and inject the result
            if formdata:
                logger.info("Processing formdata parameter...")
                try:
                    # Process preset data using the backend API
                    logger.debug("Calling process_preset_data_internal...")
                    processed_result = await process_preset_data_internal(formdata)
                    logger.info(f"Preset data processing result: success={processed_result['success']}")
                    if processed_result['success']:
                        logger.info(f"  - is_multiple: {processed_result['is_multiple']}")
                        logger.info(f"  - has_form_config: {processed_result['has_form_config']}")
                        logger.info(f"  - processed_data type: {type(processed_result.get('processed_data', None)).__name__}")
                    else:
                        logger.warning(f"  - error: {processed_result.get('error', 'Unknown')}")
                    
                    # Inject both original formdata and processed result into the HTML
                    injection_script = f"""
                    <script>
                    window.presetFormData = '{formdata}';
                    window.processedPresetData = {json.dumps(processed_result)};
                    window.multiFormMode = {json.dumps(m == '1')};
                    </script>
                    """
                    # Insert before closing </head> tag
                    content = content.replace('</head>', f'{injection_script}</head>')
                    logger.debug("JavaScript injection completed successfully")
                    
                except Exception as e:
                    logger.error(f"Error processing preset data: {str(e)}", exc_info=True)
                    # Fallback: just inject the original formdata
                    logger.info("Using fallback injection (original formdata only)")
                    injection_script = f"""
                    <script>
                    window.presetFormData = '{formdata}';
                    window.processedPresetData = null;
                    window.multiFormMode = {json.dumps(m == '1')};
                    </script>
                    """
                    content = content.replace('</head>', f'{injection_script}</head>')
            
            # If no formdata but m=1 parameter exists, still inject multi-form mode flag
            elif m == '1':
                logger.info("No formdata but m=1 parameter present, injecting multi-form mode flag")
                injection_script = f"""
                <script>
                window.multiFormMode = true;
                </script>
                """
                content = content.replace('</head>', f'{injection_script}</head>')
                logger.debug("Multi-form mode flag injection completed")
            
            logger.info(f"Returning HTML response, final length: {len(content)}")
            return HTMLResponse(content=content)
        
        except Exception as e:
            logger.error(f"Error serving universal form page: {str(e)}", exc_info=True)
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

    async def process_preset_data_internal(formdata: str) -> Dict[str, Any]:
        """
        Internal function to process preset data for injection into HTML.
        """
        logger.info("=== process_preset_data_internal called ===")
        logger.debug(f"Input formdata length: {len(formdata)}")
        
        try:
            # Decode base64 data
            logger.debug("Decoding base64 data...")
            decoded_data = base64.b64decode(formdata).decode('utf-8')
            logger.info(f"Decoded data length: {len(decoded_data)}")
            logger.debug(f"Decoded data preview (first 200 chars): {decoded_data[:200]}...")
            
            # formdata is always non-JSON text data that needs AI processing
            preset_data = decoded_data
            is_json_data = False
            is_multiple_forms = False  # Will be determined by AI processing result
            logger.info("Processing formdata as text content (non-JSON)")
            logger.info("Will use AI to process text content")
            
            # Load current form configuration
            logger.debug(f"Checking for form configuration at: {CONFIG_FILE}")
            form_fields = []
            if CONFIG_FILE.exists():
                logger.info("✓ Form configuration file found")
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    form_fields = config.get("fields", [])
                logger.info(f"Loaded {len(form_fields)} form fields from config")
                for i, field in enumerate(form_fields):
                    logger.debug(f"  Field {i+1}: {field.get('key', 'N/A')} ({field.get('type', 'N/A')}) - {field.get('label', 'N/A')}")
            else:
                logger.warning("✗ No form configuration file found")
            
            # Always use AI processing for text data
            logger.info("Starting AI data processing...")
            processed_data = await _process_data_with_ai(preset_data, form_fields, is_multiple_forms, is_json_data)
            logger.info(f"AI processing completed, result type: {type(processed_data).__name__}")
            
            # Check if AI returned multiple records (determine if it's multiple forms)
            if isinstance(processed_data, list):
                is_multiple_forms = True
                logger.info(f"AI returned array, setting is_multiple to True ({len(processed_data)} records)")
            else:
                is_multiple_forms = False
                logger.info("AI returned single object, setting is_multiple to False")
            
            result = {
                "success": True,
                "processed_data": processed_data,
                "is_multiple": is_multiple_forms,
                "original_data": preset_data,
                "has_form_config": bool(form_fields)
            }
            logger.info("=== process_preset_data_internal completed successfully ===")
            logger.debug(f"Final result keys: {list(result.keys())}")
            return result
            
        except Exception as e:
            logger.error(f"=== process_preset_data_internal failed ===")
            logger.error(f"Error: {str(e)}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "processed_data": None,
                "is_multiple": False,
                "original_data": None,
                "has_form_config": False
            }

    @router.post("/preset-data")
    async def process_preset_data(formdata: str):
        """
        Process base64-encoded text data and use OpenAI to extract structured form data.
        
        Args:
            formdata: Base64-encoded text data
            
        Returns:
            Processed form data for pre-filling
        """
        try:
            # Decode base64 data as text
            try:
                decoded_data = base64.b64decode(formdata).decode('utf-8')
            except Exception as e:
                logger.error(f"Failed to decode preset data: {str(e)}")
                raise HTTPException(status_code=400, detail="Invalid base64 data format")
            
            # Load current form configuration
            form_fields = []
            if CONFIG_FILE.exists():
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    form_fields = config.get("fields", [])
            
            if not form_fields:
                return JSONResponse(content={
                    "error": "No form configuration found",
                    "original_data": decoded_data
                })
            
            # Process text data with AI
            processed_data = await _process_data_with_ai(decoded_data, form_fields, False, False)
            
            # Determine if result is multiple forms
            is_multiple_forms = isinstance(processed_data, list)
            
            return JSONResponse(content={
                "success": True,
                "processed_data": processed_data,
                "is_multiple": is_multiple_forms,
                "original_data": decoded_data
            })
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error processing preset data: {str(e)}")
            raise HTTPException(status_code=500, detail="Failed to process preset data")
    
    async def _process_data_with_ai(preset_data: str, form_fields: List[Dict], is_multiple: bool, is_json_data: bool = False) -> Any:
        """
        Process text preset data using OpenAI to intelligently extract structured data.
        """
        logger.info("=== _process_data_with_ai called ===")
        logger.debug(f"Parameters: is_multiple={is_multiple}, is_json_data={is_json_data}")
        logger.debug(f"Form fields count: {len(form_fields)}")
        logger.debug(f"AI_CLIENT_AVAILABLE: {AI_CLIENT_AVAILABLE}")
        
        ai_config = get_ai_config()
        logger.debug(f"AI config available: {bool(ai_config)}")
        
        try:
            if AI_CLIENT_AVAILABLE and ai_config:
                logger.info("✓ AI client available and API key present - using AI processing")
                # Use AI client to process the text data
                return await _process_with_ai_client(preset_data, form_fields, is_multiple, is_json_data, ai_config)
            else:
                logger.warning("✗ AI client not available or API key missing - returning empty data")
                return {} 
                
        except Exception as e:
            logger.error(f"AI processing failed: {str(e)}", exc_info=True)
            logger.info("Returning empty data as fallback due to error")
            return {}
    
    async def _process_with_ai_client(preset_data: str, form_fields: List[Dict], is_multiple: bool, is_json_data: bool = False, ai_config: Dict[str, Any] = None) -> Any:
        """
        Use AI client to extract structured data from text content.
        """
        logger.info("=== _process_with_ai_client called ===")
        logger.debug(f"Parameters: is_multiple={is_multiple}, is_json_data={is_json_data}")
        
        try:
            # Use provided AI configuration
            logger.debug("Using AI configuration from config file...")
            client_config = ai_config.copy() if ai_config else {}
            logger.debug(f"Client config: {dict(client_config, api_key='***MASKED***')}")
            
            logger.debug("Creating AI client from factory...")
            client = AIClientFactory.create_client(client_config)
            logger.info(f"✓ AI client created: {client.provider_name}")
            
            # Prepare form fields description for AI
            logger.debug("Preparing form fields description for AI...")
            fields_description = []
            for i, field in enumerate(form_fields):
                field_desc = f"- {field.get('key', '')} ({field.get('type', 'text')}): {field.get('label', '')}"
                if field.get('options'):
                    field_desc += f" [options: {field.get('options')}]"
                if field.get('required'):
                    field_desc += " [required]"
                fields_description.append(field_desc)
                logger.debug(f"  Field {i+1}: {field_desc}")
            
            fields_str = "\n".join(fields_description)
            logger.debug(f"Form fields description prepared ({len(fields_description)} fields)")
            
            # Create prompt for AI - always processing text data
            if form_fields:
                # We have form fields, map text data to them
                user_prompt = f"""
You are tasked with extracting structured data from text content and mapping it to specific form fields.

Form Fields to extract data for:
{fields_str}

Text Content:
{preset_data}

Please analyze the text content (which may be a table, document, or other structured text) and extract relevant data to fill out the form fields. If the text contains multiple records (like a table with multiple rows), return a JSON array with one object per record. If it's a single record, return a JSON object.

For each record, create an object with keys matching the form field keys. Extract the most relevant values from the text. For form fields of type 'select' or 'checkbox', ensure the values match the available options when possible.

Return only valid JSON (either object or array), no additional text.
"""
            else:
                # No form fields defined, extract general structured data
                user_prompt = f"""
You are tasked with extracting structured data from text content.

Text Content:
{preset_data}

Please analyze the text content (which may be a table, document, or other structured text) and convert it into structured JSON data. If the text contains multiple records (like a table with multiple rows), return a JSON array with one object per record. If it's a single record, return a JSON object.

Use descriptive field names that match the content. For example, if the text contains names, use 'name' as the field key. If it contains amounts, use appropriate keys like 'amount', 'price', 'salary', etc.

Return only valid JSON (either object or array), no additional text.
"""
            
            # Create messages using the existing Message class
            logger.debug("Creating AI messages...")
            messages = [
                Message(role=Role.SYSTEM, content="You are a helpful assistant that maps data to form fields. Always return valid JSON."),
                Message(role=Role.USER, content=user_prompt)
            ]
            logger.debug(f"System message length: {len(messages[0].content)}")
            logger.debug(f"User prompt length: {len(user_prompt)}")
            
            # Call AI client
            logger.info("Calling AI client...")
            logger.debug("Making AI API request...")
            response = await client.chat(messages)
            logger.info("✓ AI API call completed")
            
            ai_response = response.content.strip()
            logger.debug(f"AI response length: {len(ai_response)}")
            logger.debug(f"AI response preview (first 200 chars): {ai_response[:200]}...")
            
            if hasattr(response, 'usage') and response.usage:
                logger.debug(f"AI usage: {response.usage}")
            if hasattr(response, 'model') and response.model:
                logger.debug(f"AI model used: {response.model}")
            
            # Try to extract JSON from response
            logger.debug("Parsing AI response as JSON...")
            try:
                # Remove markdown code blocks if present
                cleaned_response = ai_response
                if ai_response.startswith('```json'):
                    cleaned_response = ai_response[7:]
                    logger.debug("Removed ```json prefix")
                if cleaned_response.startswith('```'):
                    cleaned_response = cleaned_response[3:]
                    logger.debug("Removed ``` prefix")
                if cleaned_response.endswith('```'):
                    cleaned_response = cleaned_response[:-3]
                    logger.debug("Removed ``` suffix")
                
                if cleaned_response != ai_response:
                    logger.debug(f"Cleaned response length: {len(cleaned_response)}")
                
                logger.debug("Attempting to parse cleaned response as JSON...")
                mapped_data = json.loads(cleaned_response.strip())
                logger.info(f"✓ AI client successfully processed preset data")
                logger.debug(f"Parsed data type: {type(mapped_data).__name__}")
                
                if isinstance(mapped_data, dict):
                    logger.debug(f"Result object keys: {list(mapped_data.keys())}")
                elif isinstance(mapped_data, list):
                    logger.debug(f"Result array length: {len(mapped_data)}")
                    if mapped_data:
                        logger.debug(f"First item keys: {list(mapped_data[0].keys()) if isinstance(mapped_data[0], dict) else 'Not a dict'}")
                
                # For non-JSON input data, we need to determine if the result should be treated as multiple forms
                if not is_json_data and isinstance(mapped_data, list):
                    logger.info(f"Non-JSON input resulted in array of {len(mapped_data)} items")
                    return mapped_data
                    
                logger.debug("Returning mapped data from AI processing")
                return mapped_data
                
            except json.JSONDecodeError as e:
                logger.error(f"✗ Failed to parse AI response as JSON: {e}")
                logger.error(f"Raw AI Response: {repr(ai_response)}")
                logger.error(f"Cleaned Response: {repr(cleaned_response)}")
                logger.info("Falling back to simple field mapping...")
                
                # Fallback for parsing errors
                logger.info("Returning empty data due to JSON parse error")
                return {}
                
        except Exception as e:
            logger.error(f"✗ AI client processing failed: {str(e)}", exc_info=True)
            logger.info("Returning empty data due to error")
            return {}
    

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