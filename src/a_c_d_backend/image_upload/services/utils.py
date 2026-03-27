import cloudinary
import cloudinary.uploader
import cloudinary.api
from cloudinary.utils import api_sign_request
from datetime import datetime
from fastapi import HTTPException
from sqlmodel import Session, select
from ...db.models import ImageUpload
from ...db.main import get_session  # your async session dep
from typing import Dict, Any
import os
import uuid

# Configure once (can be in config.py or here)
cloudinary.config(
    cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
    api_key=os.getenv("CLOUDINARY_API_KEY"),
    api_secret=os.getenv("CLOUDINARY_API_SECRET"),
    secure=True,
)

class CloudinaryService:
    def __init__(self):
        self.allowed_mimetypes = ["image/jpeg", "image/png", "image/webp"]
        self.max_size_bytes = 10 * 1024 * 1024  # 10MB

    def generate_upload_signature(
        self,
        plant_type: str,
        user_id: str,
        filename: str,
        content_type: str,
        file_size: int,
        session: Session,
    ) -> Dict[str, Any]:
        """Generate timestamp + signature for client direct upload"""
        if content_type not in self.allowed_mimetypes:
            raise HTTPException(400, "Invalid image type (JPEG, PNG, WebP only)")

        if file_size > self.max_size_bytes:
            raise HTTPException(400, f"File too large (max {self.max_size_bytes // (1024*1024)}MB)")

        # Optional: Add folder or tags
        folder = f"plant-disease/{plant_type}/{user_id}"
        public_id_prefix = f"{folder}/{datetime.utcnow().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:8]}"

        # Parameters to sign (must include timestamp; add any restricted params)
        params_to_sign = {
            "timestamp": int(datetime.utcnow().timestamp()),
            "folder": folder,               # optional
            # "public_id": public_id_prefix,  # optional - Cloudinary auto-generates if omitted
            # "upload_preset": "ml_input",    # if using preset
        }

        signature = api_sign_request(params_to_sign, cloudinary.config().api_secret)

        # Create pending DB record
        image_record = ImageUpload(
            user_id=user_id,
            plant_type=plant_type,
            image_path="",  # Filled after upload
            uploaded_at=datetime.utcnow(),
        )
        session.add(image_record)
        session.commit()
        session.refresh(image_record)

        return {
            "api_key": cloudinary.config().api_key,
            "timestamp": params_to_sign["timestamp"],
            "signature": signature,
            "folder": folder,
            "cloud_name": cloudinary.config().cloud_name,
            "image_id": str(image_record.id),  # Client sends back after upload
            "upload_url": f"https://api.cloudinary.com/v1_1/{cloudinary.config().cloud_name}/image/upload",
        }

    def confirm_and_save_upload(
        self,
        image_id: str,
        public_id: str,
        secure_url: str,
        user_id: str,
        session: Session,
    ) -> Dict[str, str]:
        """Client calls after successful upload; verify & save metadata"""
        image = session.exec(
            select(ImageUpload).where(ImageUpload.id == image_id, ImageUpload.user_id == user_id)
        ).first()

        if not image:
            raise HTTPException(404, "Image record not found")

        try:
            # Verify resource exists (optional but good for security)
            resource = cloudinary.api.resource(public_id=public_id, resource_type="image")
            if resource["bytes"] > self.max_size_bytes:
                cloudinary.api.delete_resources([public_id], resource_type="image")
                session.delete(image)
                session.commit()
                raise HTTPException(400, "File size exceeded limit after upload")

            # Save metadata
            image.image_path = public_id
            # image.url = secure_url  # Add url field if needed
            session.commit()

            return {
                "success": True,
                "message": "Upload confirmed and saved",
                "image_id": image_id,
                "secure_url": secure_url,
                "public_id": public_id,
            }

        except cloudinary.api.Error as e:
            session.delete(image)
            session.commit()
            raise HTTPException(400, f"Cloudinary verification failed: {str(e)}")

    def get_view_url(self, public_id: str, expires_in: int = 3600) -> str:
        """Generate signed delivery URL if transformations needed or private"""
        # Cloudinary URLs are public by default; use signed if you enable signed URLs
        return cloudinary.utils.cloudinary_url(
            public_id,
            secure=True,
            sign_url=True,  # If you enable strict transformations
            expires_at=int(datetime.utcnow().timestamp()) + expires_in,
        )[0]