import io
import json

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse

from ..schemas import (
    DeleteResponse,
    FileInfoResponse,
    ListResponse,
    OperationResponse,
    ProviderName,
    UploadResponse,
)
from ..storage_service import StorageService


router = APIRouter(prefix="/storage", tags=["Storage"])


@router.post(
    "/upload",
    response_model=UploadResponse,
)
async def upload_file(
    provider: ProviderName = Query(..., description="Storage provider"),
    file: UploadFile = File(...),
    metadata_json: str | None = Form(default=None),
):
    service = StorageService()
    parsed_metadata: dict[str, str] | None = None
    if metadata_json:
        try:
            parsed = json.loads(metadata_json)
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=400, detail="metadata_json must be valid JSON.") from exc
        if not isinstance(parsed, dict):
            raise HTTPException(status_code=400, detail="metadata_json must be a JSON object.")
        parsed_metadata = {
            str(key).strip(): str(value).strip()
            for key, value in parsed.items()
            if str(key).strip() and str(value).strip()
        }
    return service.upload_file(provider=provider, file=file, metadata_json=parsed_metadata)


@router.get("/download")
def download_file(
    document_id: str = Query(
        ...,
        description="Document ID from uploaded_documents table",
    ),
):
    service = StorageService()
    content, file_name, content_type = service.download_file_by_id(
        document_id=document_id,
    )

    return StreamingResponse(
        io.BytesIO(content),
        media_type=content_type or "application/octet-stream",
        headers={
            "Content-Disposition": f'attachment; filename="{file_name}"',
        },
    )


@router.delete(
    "/delete",
    response_model=DeleteResponse,
    response_model_exclude_none=True,
)
def delete_file(
    document_id: str = Query(
        ...,
        description="Document ID from uploaded_documents table",
    ),
):
    service = StorageService()
    return service.delete_file_by_id(document_id=document_id)


@router.post(
    "/move",
    response_model=OperationResponse,
    response_model_exclude_none=True,
)
def move_file(
    document_id: str = Query(
        ...,
        description="Document ID from uploaded_documents table",
    ),
    target_folder_name: str = Query(
        ...,
        description="Target folder inside processed-documents",
    ),
):
    service = StorageService()
    return service.move_file_to_processed_folder(
        document_id=document_id,
        target_folder_name=target_folder_name,
    )


@router.post(
    "/copy",
    response_model=OperationResponse,
    response_model_exclude_none=True,
)
def copy_file(
    document_id: str = Query(
        ...,
        description="Document ID from uploaded_documents table",
    ),
    target_folder_name: str = Query(
        ...,
        description="Target folder inside processed-documents",
    ),
):
    service = StorageService()
    return service.copy_file_to_processed_folder(
        document_id=document_id,
        target_folder_name=target_folder_name,
    )


@router.post(
    "/create-folder",
    response_model=OperationResponse,
    response_model_exclude_none=True,
)
def create_folder(
    provider: ProviderName = Query(
        ...,
        description="Storage provider",
    ),
    folder_name: str = Query(
        ...,
        description="Folder inside processed-documents. Example: cv, payslip, invoice",
    ),
):
    service = StorageService()
    return service.create_processed_folder(
        provider=provider,
        folder_name=folder_name,
    )


@router.get(
    "/info",
    response_model=FileInfoResponse,
    response_model_exclude_none=True,
)
def get_file_info(
    document_id: str = Query(
        ...,
        description="Document ID from uploaded_documents table",
    ),
):
    service = StorageService()
    return service.get_file_info_by_id(document_id=document_id)


@router.get(
    "/list",
    response_model=ListResponse,
    response_model_exclude_none=True,
)
def list_files(
    provider: ProviderName = Query(
        ...,
        description="Storage provider",
    ),
    folder_type: str = Query(
        ...,
        description="raw or processed",
    ),
    folder_name: str | None = Query(
        default=None,
        description="Optional subfolder inside processed-documents",
    ),
):
    service = StorageService()
    return service.list_files_by_type(
        provider=provider,
        folder_type=folder_type,
        folder_name=folder_name,
    )
