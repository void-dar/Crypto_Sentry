from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from ...db.main import get_session
from ..services.utils import S3Service
from ...auth.services.dependency import get_current_user
from ...db.models import User, ImageUpload
from typing import Dict

upload_router = APIRouter(prefix="/uploads", tags=["uploads"])

s3_service = S3Service() 

@upload_router.post("/generate-presigned")
async def generate_upload_url(
    filename: str = Query(...),
    content_type: str = Query(...),
    file_size: int = Query(...),
    plant_type: str = Query(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
) -> Dict:
    """Client calls this to get presigned PUT URL"""
    return s3_service.generate_presigned_upload_url(
        filename=filename,
        content_type=content_type,
        file_size=file_size,
        plant_type=plant_type,
        user_id=str(current_user.id),
        session=db,
    )

@upload_router.post("/confirm/{image_id}")
async def confirm_upload(
    image_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
) -> Dict:
    """Client calls this after successful upload to confirm"""
    return s3_service.confirm_upload(image_id, str(current_user.id), db)

@upload_router.get("/view/{image_id}")
async def get_view_url(
    image_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    """Get temporary presigned GET URL for viewing the image"""
    image = await db.get(ImageUpload, image_id)
    if not image or image.user_id != current_user.id:
        raise HTTPException(404, "Image not found or unauthorized")
    url = s3_service.generate_presigned_view_url(image.image_path)
    return {"view_url": url}
async def generate_upload_url(
    filename: str = Query(...),
    content_type: str = Query(...),
    file_size: int = Query(...),
    plant_type: str = Query(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
) -> Dict:
    """Client calls this to get presigned PUT URL"""
    return s3_service.generate_presigned_upload_url(
        filename=filename,
        content_type=content_type,
        file_size=file_size,
        plant_type=plant_type,
        user_id=str(current_user.id),
        session=db,
    )