from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from pydantic import BaseModel
from typing import Optional
import logging
import os
from datetime import datetime

from services.storage_service import storage_service
from core.supabase_client import supabase_client

router = APIRouter()
logger = logging.getLogger(__name__)

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

        logger.info(f"File {file.filename} uploaded successfully to room {room_id} by user {uploaded_by}")

        return FileUploadResponse(
            file_id=file_record["id"],
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
