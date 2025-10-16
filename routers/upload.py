from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from pydantic import BaseModel
from typing import Optional
import logging
import os
from datetime import datetime
import httpx

from services.storage_service import storage_service
from core.supabase_client import supabase_client

router = APIRouter()
logger = logging.getLogger(__name__)

# External document processing API configuration
EXTERNAL_DOC_API_BASE_URL = "http://34.27.126.117:8000"
EXTERNAL_DOC_API_TIMEOUT = 30.0  # seconds

async def call_external_upload_api(
    file_id: str,
    file_url: str,
    room_id: str,
    user_id: str,
    file_name: str,
    content_type: str
) -> bool:
    """
    Call external document processing API to upload a document

    Returns:
        bool: True if successful, False otherwise
    """
    try:
        payload = {
            "file_id": file_id,
            "file_url": file_url,
            "ai_info": {},  # Empty dict as per API spec
            "room_id": room_id,
            "user_id": user_id,
            "file_name": file_name,
            "content_type": content_type
        }

        async with httpx.AsyncClient(timeout=EXTERNAL_DOC_API_TIMEOUT) as client:
            response = await client.post(
                f"{EXTERNAL_DOC_API_BASE_URL}/api/documents/upload",
                json=payload
            )

            if response.status_code == 200:
                logger.info(f"Successfully called external upload API for file {file_id}")
                return True
            else:
                logger.error(f"External upload API failed with status {response.status_code}: {response.text}")
                return False

    except httpx.TimeoutException:
        logger.error(f"External upload API timeout for file {file_id}")
        return False
    except Exception as e:
        logger.error(f"Error calling external upload API for file {file_id}: {str(e)}")
        return False

async def call_external_delete_api(file_id: str) -> bool:
    """
    Call external document processing API to delete a document

    Returns:
        bool: True if successful, False otherwise
    """
    try:
        async with httpx.AsyncClient(timeout=EXTERNAL_DOC_API_TIMEOUT) as client:
            response = await client.delete(
                f"{EXTERNAL_DOC_API_BASE_URL}/api/documents/delete/{file_id}"
            )

            if response.status_code == 200:
                logger.info(f"Successfully called external delete API for file {file_id}")
                return True
            else:
                logger.error(f"External delete API failed with status {response.status_code}: {response.text}")
                return False

    except httpx.TimeoutException:
        logger.error(f"External delete API timeout for file {file_id}")
        return False
    except Exception as e:
        logger.error(f"Error calling external delete API for file {file_id}: {str(e)}")
        return False

async def call_external_upload_api_for_ai(
    file_id: str,
    file_url: str,
    ai_info: dict,
    user_id: str,
    file_name: str,
    content_type: str
) -> bool:
    """
    Call external document processing API to upload a document for AI

    Args:
        file_id: The file ID from knowledge_files table
        file_url: Public URL of the uploaded file
        ai_info: AI information dict with id, name, description, personality, system_prompt
        user_id: User profile ID
        file_name: Original filename
        content_type: MIME type

    Returns:
        bool: True if successful, False otherwise
    """
    try:
        payload = {
            "file_id": file_id,
            "file_url": file_url,
            "ai_info": ai_info,
            "room_id": "",  # Empty for AI documents
            "user_id": user_id,
            "file_name": file_name,
            "content_type": content_type
        }

        async with httpx.AsyncClient(timeout=EXTERNAL_DOC_API_TIMEOUT) as client:
            response = await client.post(
                f"{EXTERNAL_DOC_API_BASE_URL}/api/documents/upload",
                json=payload
            )

            if response.status_code == 200:
                logger.info(f"Successfully called external upload API for AI file {file_id}")
                return True
            else:
                logger.error(f"External upload API failed with status {response.status_code}: {response.text}")
                return False

    except httpx.TimeoutException:
        logger.error(f"External upload API timeout for file {file_id}")
        return False
    except Exception as e:
        logger.error(f"Error calling external upload API for file {file_id}: {str(e)}")
        return False

class FileUploadResponse(BaseModel):
    file_id: str
    file_name: str
    file_path: str
    file_size: int
    content_type: str
    file_url: str
    message: str = "File uploaded successfully"

@router.post("/upload/room-document", response_model=FileUploadResponse)
async def upload_room_document(
    file: UploadFile = File(...),
    room_id: str = Form(...),
    uploaded_by: str = Form(...)
):
    """
    Upload a document file to a room's knowledge base

    Parameters:
    - file: The file to upload (pdf, md, or txt only)
    - room_id: The room ID where the file will be uploaded
    - uploaded_by: Profile ID of the user uploading the file

    Returns:
    - FileUploadResponse with file details

    Raises:
    - HTTPException 400: Invalid file type or file too large
    - HTTPException 404: Room not found
    - HTTPException 500: Upload or database error
    """

    try:
        # Validate required fields
        if not room_id or not uploaded_by:
            raise HTTPException(status_code=400, detail="room_id and uploaded_by are required")

        if not file.filename:
            raise HTTPException(status_code=400, detail="File name is required")

        # Read file content
        file_content = await file.read()
        file_size = len(file_content)

        # Validate file
        is_valid, error_msg = storage_service.validate_file(file.filename, file_size)
        if not is_valid:
            raise HTTPException(status_code=400, detail=error_msg)

        # Determine correct content type based on file extension
        _, ext = os.path.splitext(file.filename)
        content_type_map = {
            '.pdf': 'application/pdf',
            '.md': 'text/markdown',
            '.txt': 'text/plain'
        }
        content_type = content_type_map.get(ext.lower(), file.content_type or "application/octet-stream")

        # Verify room exists
        room_result = supabase_client.table("rooms").select("id").eq("id", room_id).is_("deleted_at", "null").execute()
        if not room_result.data:
            raise HTTPException(status_code=404, detail="Room not found")

        # Upload file to GCS
        success, file_path, upload_error = storage_service.upload_file(
            file_content=file_content,
            filename=file.filename,
            room_id=room_id,
            content_type=content_type
        )

        if not success:
            raise HTTPException(status_code=500, detail=upload_error)

        # Get public URL
        file_url = storage_service.get_file_url(file_path)

        # Insert record into knowledge_files table
        knowledge_file_data = {
            "room_id": room_id,
            "file_name": file.filename,
            "file_path": file_path,
            "file_size": file_size,
            "content_type": content_type,
            "uploaded_by": uploaded_by
        }

        db_result = supabase_client.table("knowledge_files").insert(knowledge_file_data).execute()

        if not db_result.data:
            # Rollback: delete uploaded file
            storage_service.delete_file(file_path)
            raise HTTPException(status_code=500, detail="Failed to save file record to database")

        file_record = db_result.data[0]
        file_id = file_record["id"]

        # Call external document processing API after successful Supabase insert
        external_api_success = await call_external_upload_api(
            file_id=file_id,
            file_url=file_url,
            room_id=room_id,
            user_id=uploaded_by,
            file_name=file.filename,
            content_type=content_type
        )

        if not external_api_success:
            # Rollback: delete from Supabase and GCS
            supabase_client.table("knowledge_files").delete().eq("id", file_id).execute()
            storage_service.delete_file(file_path)
            raise HTTPException(
                status_code=500,
                detail="Failed to process document with external API. Upload has been rolled back."
            )

        logger.info(f"File {file.filename} uploaded successfully to room {room_id} by user {uploaded_by}")

        return FileUploadResponse(
            file_id=file_id,
            file_name=file.filename,
            file_path=file_path,
            file_size=file_size,
            content_type=content_type,
            file_url=file_url
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error uploading file: {str(e)}")
        raise HTTPException(status_code=500, detail=f"An error occurred while uploading the file: {str(e)}")

@router.delete("/upload/room-document/{file_id}")
async def delete_room_document(file_id: str):
    """
    Delete a room document

    Parameters:
    - file_id: The ID of the file to delete

    Returns:
    - Success message

    Raises:
    - HTTPException 404: File not found
    - HTTPException 500: Delete error
    """
    try:
        # Get file record
        file_result = supabase_client.table("knowledge_files").select("*").eq("id", file_id).is_("deleted_at", "null").execute()

        if not file_result.data:
            raise HTTPException(status_code=404, detail="File not found")

        file_record = file_result.data[0]
        file_path = file_record["file_path"]

        # Call external document processing API before deleting from Supabase
        external_delete_success = await call_external_delete_api(file_id)
        if not external_delete_success:
            logger.warning(f"Failed to delete file {file_id} from external API, continuing with local deletion")

        # Delete from GCS
        success, error_msg = storage_service.delete_file(file_path)
        if not success:
            logger.warning(f"Failed to delete file from GCS: {error_msg}, continuing with database deletion")

        # Delete record from database (hard delete)
        delete_result = supabase_client.table("knowledge_files").delete().eq("id", file_id).execute()

        if not delete_result.data:
            raise HTTPException(status_code=500, detail="Failed to delete file record from database")

        logger.info(f"File {file_id} deleted successfully")

        return {"message": "File deleted successfully", "file_id": file_id}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error deleting file: {str(e)}")
        raise HTTPException(status_code=500, detail=f"An error occurred while deleting the file: {str(e)}")

@router.post("/upload/ai-document", response_model=FileUploadResponse)
async def upload_ai_document(
    file: UploadFile = File(...),
    ai_id: str = Form(...),
    uploaded_by: str = Form(...)
):
    """
    Upload a document file to an AI's knowledge base

    Parameters:
    - file: The file to upload (pdf, md, or txt only)
    - ai_id: The AI ID where the file will be uploaded
    - uploaded_by: Profile ID of the user uploading the file

    Returns:
    - FileUploadResponse with file details

    Raises:
    - HTTPException 400: Invalid file type or file too large
    - HTTPException 404: AI not found
    - HTTPException 500: Upload or database error
    """

    try:
        # Validate required fields
        if not ai_id or not uploaded_by:
            raise HTTPException(status_code=400, detail="ai_id and uploaded_by are required")

        if not file.filename:
            raise HTTPException(status_code=400, detail="File name is required")

        # Read file content
        file_content = await file.read()
        file_size = len(file_content)

        # Validate file
        is_valid, error_msg = storage_service.validate_file(file.filename, file_size)
        if not is_valid:
            raise HTTPException(status_code=400, detail=error_msg)

        # Determine correct content type based on file extension
        _, ext = os.path.splitext(file.filename)
        content_type_map = {
            '.pdf': 'application/pdf',
            '.md': 'text/markdown',
            '.txt': 'text/plain'
        }
        content_type = content_type_map.get(ext.lower(), file.content_type or "application/octet-stream")

        # Verify AI exists and get AI info
        ai_result = supabase_client.table("ai").select("id, name, description, personality, system_prompt").eq("id", ai_id).is_("deleted_at", "null").execute()
        if not ai_result.data:
            raise HTTPException(status_code=404, detail="AI not found")

        ai_info = ai_result.data[0]

        # Upload file to GCS
        success, file_path, upload_error = storage_service.upload_ai_file(
            file_content=file_content,
            filename=file.filename,
            ai_id=ai_id,
            content_type=content_type
        )

        if not success:
            raise HTTPException(status_code=500, detail=upload_error)

        # Get public URL
        file_url = storage_service.get_file_url(file_path)

        # Insert record into knowledge_files table
        knowledge_file_data = {
            "ai_id": ai_id,
            "file_name": file.filename,
            "file_path": file_path,
            "file_size": file_size,
            "content_type": content_type,
            "uploaded_by": uploaded_by
        }

        db_result = supabase_client.table("knowledge_files").insert(knowledge_file_data).execute()

        if not db_result.data:
            # Rollback: delete uploaded file
            storage_service.delete_file(file_path)
            raise HTTPException(status_code=500, detail="Failed to save file record to database")

        file_record = db_result.data[0]
        file_id = file_record["id"]

        # Call external document processing API after successful Supabase insert
        external_api_success = await call_external_upload_api_for_ai(
            file_id=file_id,
            file_url=file_url,
            ai_info=ai_info,
            user_id=uploaded_by,
            file_name=file.filename,
            content_type=content_type
        )

        if not external_api_success:
            # Rollback: delete from Supabase and GCS
            supabase_client.table("knowledge_files").delete().eq("id", file_id).execute()
            storage_service.delete_file(file_path)
            raise HTTPException(
                status_code=500,
                detail="Failed to process document with external API. Upload has been rolled back."
            )

        logger.info(f"File {file.filename} uploaded successfully to AI {ai_id} by user {uploaded_by}")

        return FileUploadResponse(
            file_id=file_id,
            file_name=file.filename,
            file_path=file_path,
            file_size=file_size,
            content_type=content_type,
            file_url=file_url
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error uploading file: {str(e)}")
        raise HTTPException(status_code=500, detail=f"An error occurred while uploading the file: {str(e)}")

@router.delete("/upload/ai-document/{file_id}")
async def delete_ai_document(file_id: str):
    """
    Delete an AI document

    Parameters:
    - file_id: The ID of the file to delete

    Returns:
    - Success message

    Raises:
    - HTTPException 404: File not found
    - HTTPException 500: Delete error
    """
    try:
        # Get file record
        file_result = supabase_client.table("knowledge_files").select("*").eq("id", file_id).is_("deleted_at", "null").execute()

        if not file_result.data:
            raise HTTPException(status_code=404, detail="File not found")

        file_record = file_result.data[0]
        file_path = file_record["file_path"]

        # Call external document processing API before deleting from Supabase
        external_delete_success = await call_external_delete_api(file_id)
        if not external_delete_success:
            logger.warning(f"Failed to delete file {file_id} from external API, continuing with local deletion")

        # Delete from GCS
        success, error_msg = storage_service.delete_file(file_path)
        if not success:
            logger.warning(f"Failed to delete file from GCS: {error_msg}, continuing with database deletion")

        # Delete record from database (hard delete)
        delete_result = supabase_client.table("knowledge_files").delete().eq("id", file_id).execute()

        if not delete_result.data:
            raise HTTPException(status_code=500, detail="Failed to delete file record from database")

        logger.info(f"File {file_id} deleted successfully")

        return {"message": "File deleted successfully", "file_id": file_id}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error deleting file: {str(e)}")
        raise HTTPException(status_code=500, detail=f"An error occurred while deleting the file: {str(e)}")
