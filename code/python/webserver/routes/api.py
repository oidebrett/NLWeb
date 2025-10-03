"""Core API routes for aiohttp server"""

from aiohttp import web
import logging
import json
from typing import Dict, Any
from methods.whoHandler import WhoHandler
from methods.generate_answer import GenerateAnswer
from webserver.aiohttp_streaming_wrapper import AioHttpStreamingWrapper
from core.retriever import get_vector_db_client
from core.utils.utils import get_param
from data_loading.db_load import loadJsonToDB, delete_site
import json
import asyncio
import sys
import io
import os
import tempfile
import zipfile
from pathlib import Path
from core.config import CONFIG

logger = logging.getLogger(__name__)

# Create a lock to serialize database operations
db_lock = asyncio.Lock()

def setup_api_routes(app: web.Application):
    """Setup core API routes"""
    # Query endpoints
    app.router.add_get('/ask', ask_handler)
    app.router.add_post('/ask', ask_handler)
    
    # Info endpoints
    app.router.add_get('/who', who_handler)
    app.router.add_get('/sites', sites_handler)

    # Site management endpoints
    app.router.add_post('/api/sites/add', add_site_handler)
    app.router.add_post('/api/sites/delete', delete_site_handler)
    app.router.add_get('/api/upload/config', upload_config_handler)

async def upload_config_handler(request: web.Request) -> web.Response:
    """
    Get OAuth configuration for enabled providers.
    
    Returns:
        200: {
            },
            ...
        }
    """
    try:
        # Use the global CONFIG which has upload_docs_enabled flag
        def str_to_bool(val) -> bool:
            return str(val).lower() in ("1", "true", "yes", "on")

        upload_docs_enabled = str_to_bool(getattr(CONFIG.nlweb, "upload_docs_enabled", "false"))
        
        # Build response with enabled providers and their config
        response = upload_docs_enabled
        logger.info(f"Upload config requested, returning: {response}")
        return web.json_response(response)
        
    except Exception as e:
        logger.error(f"Error getting upload config: {e}")
        return web.json_response({})

async def ask_handler(request: web.Request) -> web.Response:
    """Handle /ask endpoint for generating answers"""
    
    # Get query parameters
    query_params = dict(request.query)
    
    # For POST requests, merge body parameters
    if request.method == 'POST':
        try:
            if request.content_type == 'application/json':
                body_data = await request.json()
                query_params.update(body_data)
            elif request.content_type == 'application/x-www-form-urlencoded':
                body_data = await request.post()
                query_params.update(dict(body_data))
        except Exception as e:
            logger.warning(f"Failed to parse POST body: {e}")
    
    # Check if SSE streaming is requested
    is_sse = request.get('is_sse', False)
    streaming = get_param(query_params, "streaming", str, "True")
    streaming = streaming not in ["False", "false", "0"]
    
    if is_sse or streaming:
        return await handle_streaming_ask(request, query_params)
    else:
        return await handle_regular_ask(request, query_params)


async def handle_streaming_ask(request: web.Request, query_params: Dict[str, Any]) -> web.StreamResponse:
    """Handle streaming (SSE) ask requests"""
    
    # Create SSE response
    response = web.StreamResponse(
        status=200,
        headers={
            'Content-Type': 'text/event-stream',
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
            'X-Accel-Buffering': 'no'
        }
    )
    
    await response.prepare(request)
    
    # Create aiohttp-compatible wrapper
    wrapper = AioHttpStreamingWrapper(request, response, query_params)
    await wrapper.prepare_response()
    
    try:
        # Determine which handler to use based on generate_mode
        generate_mode = query_params.get('generate_mode', 'none')
        
        if generate_mode == 'generate':
            handler = GenerateAnswer(query_params, wrapper)
            await handler.runQuery()
        else:
            # Use base NLWebHandler for other modes
            from core.baseHandler import NLWebHandler
            handler = NLWebHandler(query_params, wrapper)
            await handler.runQuery()
        
        # Send completion message
        await wrapper.write_stream({"message_type": "complete"})
        
    except Exception as e:
        logger.error(f"Error in streaming ask handler: {e}", exc_info=True)
        await wrapper.send_error_response(500, str(e))
    finally:
        await wrapper.finish_response()
    
    return response


async def handle_regular_ask(request: web.Request, query_params: Dict[str, Any]) -> web.Response:
    """Handle non-streaming ask requests"""
    
    try:
        # Determine which handler to use
        generate_mode = query_params.get('generate_mode', 'none')
        
        if generate_mode == 'generate':
            handler = GenerateAnswer(query_params, None)
        else:
            from core.baseHandler import NLWebHandler
            handler = NLWebHandler(query_params, None)
        
        # Run the query - it will return the complete response
        result = await handler.runQuery()
        
        # Return the response directly
        return web.json_response(result)
        
    except Exception as e:
        logger.error(f"Error in regular ask handler: {e}", exc_info=True)
        return web.json_response({
            "message_type": "error",
            "error": str(e)
        }, status=500)


async def who_handler(request: web.Request) -> web.Response:
    """Handle /who endpoint"""
    
    try:
        # Get query parameters
        query_params = dict(request.query)
        
        # Run the who handler
        handler = WhoHandler(query_params, None)
        result = await handler.runQuery()
        
        return web.json_response(result)
        
    except Exception as e:
        logger.error(f"Error in who handler: {e}", exc_info=True)
        return web.json_response({
            "message_type": "error",
            "error": str(e)
        }, status=500)


async def sites_handler(request: web.Request) -> web.Response:
    """Handle /sites endpoint to get available sites"""
    
    try:
        # Get query parameters
        query_params = dict(request.query)
        
        # Check if streaming is requested
        streaming = get_param(query_params, "streaming", str, "False")
        streaming = streaming not in ["False", "false", "0"]
        
        # Create a retriever client
        retriever = get_vector_db_client(query_params=query_params)
        
        # Get the list of sites
        sites = await retriever.get_sites()
        
        # Prepare the response
        response_data = {
            "message-type": "sites",
            "sites": sites
        }
        
        if streaming or request.get('is_sse', False):
            # Return as SSE
            response = web.StreamResponse(
                status=200,
                headers={
                    'Content-Type': 'text/event-stream',
                    'Cache-Control': 'no-cache',
                    'Connection': 'keep-alive',
                    'X-Accel-Buffering': 'no'
                }
            )
            await response.prepare(request)
            await response.write(f"data: {json.dumps(response_data)}\n\n".encode())
            return response
        else:
            # Return as JSON
            return web.json_response(response_data)
            
    except Exception as e:
        logger.error(f"Error getting sites: {e}", exc_info=True)
        error_data = {
            "message-type": "error",
            "error": f"Failed to get sites: {str(e)}"
        }
        return web.json_response(error_data, status=500)


async def add_site_handler(request: web.Request) -> web.Response:
    """Handle /api/sites/add endpoint for adding new sites from URL or zip upload"""

    try:
        site_name = None
        rss_url = None
        zip_path = None

        if request.content_type.startswith("application/json"):
            # JSON payload (URL case)
            try:
                data = await request.json()
            except Exception as e:
                return web.json_response({"error": "Invalid JSON"}, status=400)

            site_name = data.get("name")
            rss_url = data.get("url")

        elif request.content_type.startswith("multipart/"):
            # File upload (ZIP case)
            reader = await request.multipart()
            field = await reader.next()

            while field is not None:
                if field.name == "name":
                    site_name = await field.text()
                elif field.name == "zipfile":
                    import tempfile, os
                    tmpdir = tempfile.mkdtemp()
                    zip_path = os.path.join(tmpdir, field.filename)

                    with open(zip_path, 'wb') as f:
                        while True:
                            chunk = await field.read_chunk()
                            if not chunk:
                                break
                            f.write(chunk)
                field = await reader.next()
        else:
            return web.json_response({"error": "Unsupported Content-Type"}, status=400)

        # Validate inputs
        if not site_name:
            return web.json_response({"error": "Missing site name"}, status=400)

        if not rss_url and not zip_path:
            return web.json_response({"error": "Missing url or zipfile"}, status=400)

        if rss_url and zip_path:
            return web.json_response({"error": "Provide either url or zipfile, not both"}, status=400)

        # Process
        documents_added = 0
        async with db_lock:
            if rss_url:
                documents_added = await loadJsonToDB(rss_url, site_name, force_recompute=False)
            else:
                import zipfile, tempfile
                extract_dir = tempfile.mkdtemp()
                with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                    zip_ref.extractall(extract_dir)

                # Detect "zip wrapped in a single directory" case
                entries = os.listdir(extract_dir)
                if len(entries) == 1:
                    single_entry = os.path.join(extract_dir, entries[0])
                    if os.path.isdir(single_entry):
                        extract_dir = single_entry  # point into the actual root folder

                documents_added = await load_directory_to_db(extract_dir, site_name)

        if documents_added > 0:
            return web.json_response({
                "status": "success",
                "documents_added": documents_added,
                "source_type": "url" if rss_url else "zipfile"
            })
        else:
            return web.json_response({
                "status": "error",
                "message": "No documents could be extracted"
            }, status=400)

    except Exception as e:
        import traceback
        traceback.print_exc()
        return web.json_response({"error": "Internal server error"}, status=500)


async def delete_site_handler(request: web.Request) -> web.Response:
    """Handle /api/sites/delete endpoint for deleting sites"""

    try:
        # Parse request body
        try:
            data = await request.json()
        except Exception as e:
            logger.warning(f"Failed to parse JSON body: {e}")
            return web.json_response({
                "error": "Invalid JSON in request body"
            }, status=400)

        # Extract required parameter
        site_name = data.get("name")

        if not site_name:
            return web.json_response({
                "error": "Missing site name"
            }, status=400)

        # Delete site from database with lock for thread safety
        async with db_lock:
            await delete_site(site_name)

        logger.info(f"Successfully deleted site '{site_name}'")
        return web.json_response({
            "status": "success"
        })

    except Exception as e:
        logger.error(f"Failed to delete site: {e}", exc_info=True)
        return web.json_response({
            "error": "Internal server error"
        }, status=500)

async def load_directory_to_db(directory_path: str, site_name: str) -> int:
    """
    Load all files from a directory into the database.
    Returns the total number of documents added.
    """
    if not os.path.isdir(directory_path):
        raise ValueError(f"'{directory_path}' is not a valid directory")

    total_documents = 0

    # List all files in the directory
    for filename in os.listdir(directory_path):
        file_path = os.path.join(directory_path, filename)
        if os.path.isfile(file_path):
            logger.info(f"Processing file: {file_path}")
            try:
                documents_added = await loadJsonToDB(file_path, site_name, force_recompute=False)
                total_documents += documents_added
                logger.info(f"Added {documents_added} documents from {file_path}")
            except Exception as e:
                logger.error(f"Error processing file {file_path}: {e}")
                # Continue processing other files even if one fails
                continue

    return total_documents
