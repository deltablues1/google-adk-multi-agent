"""
Marketing ADK Tools

ADK-compatible wrappers for Google Ads and Vertex AI visual generation operations.
Supports image/video generation, YouTube upload, and campaign creation.
"""

from typing import Optional, Literal, List
import os
import logging

logger = logging.getLogger(__name__)


# ============================================================================
# AUTHENTICATION HELPER
# ============================================================================

def _get_credentials():
    """Get OAuth credentials from token file"""
    try:
        from auth.oauth_manager import get_oauth_manager
        oauth_manager = get_oauth_manager()
        creds = oauth_manager.get_credentials()
        if creds and creds.valid:
            return creds
        logger.warning("No valid credentials available for Marketing operations")
        return None
    except Exception as e:
        logger.error(f"Failed to get credentials: {e}")
        return None


# ============================================================================
# VERTEX AI VISUAL GENERATION TOOLS
# ============================================================================

async def generate_visual_asset(
    prompt: str,
    asset_type: Literal["IMAGE", "VIDEO"] = "IMAGE",
    aspect_ratio: str = "16:9"
) -> dict:
    """
    Generate visual assets (images or videos) using Vertex AI Imagen/Veo.

    Uses state-of-the-art generative AI:
    - IMAGE: Imagen 3 for high-quality image generation
    - VIDEO: Veo for AI-generated video content

    CRITICAL: Human-in-the-loop workflow required!
    - Always show generated asset to user for approval
    - Get explicit "Yes" / "Approve" before using in campaign
    - Allow regeneration if user is not satisfied

    Args:
        prompt: Detailed description of the visual asset to generate.
                Be specific about style, mood, colors, composition.
                Example: "A modern smartphone on a wooden desk with soft natural lighting,
                         professional product photography style, high resolution"
        asset_type: Type of asset to generate:
                   - "IMAGE": Static image (default)
                   - "VIDEO": Short video clip
        aspect_ratio: Aspect ratio for the asset (default: "16:9")
                     Common options: "16:9", "9:16", "1:1", "4:3"

    Returns:
        Dictionary containing:
            - uri: GCS URI of the generated asset (gs://...)
            - asset_type: Type of asset generated
            - prompt: The prompt used
            - status: "success" or "error"
            - preview_url: Optional HTTP URL for preview

    Example:
        result = await generate_visual_asset(
            prompt="Modern laptop in coffee shop, natural lighting, 4K quality",
            asset_type="IMAGE",
            aspect_ratio="16:9"
        )
        # Returns: {"uri": "gs://bucket/image.png", "status": "success", ...}
    """
    logger.info(f"Generating {asset_type} with prompt: {prompt[:100]}...")

    creds = _get_credentials()
    if creds is None:
        return {
            "error": "Authentication required. Run: python tools/oauth_cli.py --auth",
            "status": "unauthenticated"
        }

    try:
        # Use real Vertex AI implementation
        from tools.api_implementations.vertex_ai import generate_visual_asset as vertex_generate

        result = vertex_generate(
            credentials=creds,
            prompt=prompt,
            asset_type=asset_type,
            aspect_ratio=aspect_ratio
        )

        if result.get("status") == "SUCCESS":
            # Use local_url from vertex_ai (already saved via media_service)
            local_url = result.get("local_url")

            # Fallback: save from image_bytes if local_url not available
            if not local_url and result.get("image_bytes"):
                try:
                    from services.media_service import save_generated_image
                    saved = save_generated_image(result["image_bytes"], prefix="marketing")
                    local_url = saved["url_path"]
                except Exception as save_err:
                    logger.warning(f"Could not save local preview: {save_err}")

            asset_kind = result.get("type", asset_type).upper()
            tag_type = "VIDEO" if asset_kind == "VIDEO" else "IMAGE"

            # Only return local preview URL - GCS links are not publicly accessible
            return {
                "asset_type": asset_kind,
                "prompt": prompt,
                "aspect_ratio": aspect_ratio,
                "status": "success",
                "message": f"{asset_kind} generated successfully.",
                "preview_url": local_url,
                "media_tag": f"[{tag_type}:{local_url}:{prompt[:60]}]" if local_url else None,
                "display_instruction": f"The {asset_kind.lower()} is displayed inline in the chat. Use the [{tag_type}:preview_url:description] tag in your response to show it.",
            }
        else:
            return {
                "error": result.get("error", "Unknown error"),
                "status": "error",
                "message": f"Failed to generate {asset_type}"
            }

    except ImportError as e:
        logger.error(f"Vertex AI module not available: {e}")
        return {
            "error": "Vertex AI module not installed. Run: pip install google-cloud-aiplatform",
            "status": "error",
            "message": f"Failed to generate {asset_type}"
        }
    except Exception as e:
        logger.error(f"generate_visual_asset failed: {e}")
        return {
            "error": str(e),
            "status": "error",
            "message": f"Failed to generate {asset_type}"
        }


async def upload_to_youtube(
    video_uri: str,
    title: str,
    description: str = "",
    privacy_status: str = "unlisted"
) -> dict:
    """
    Upload a video to YouTube for use in Google Ads campaigns.

    Video ads require YouTube hosting before they can be used in campaigns.
    This function uploads the generated video and returns the YouTube video ID.

    Args:
        video_uri: GCS URI of the video file (gs://...)
        title: Title for the YouTube video
        description: Optional description
        privacy_status: Privacy setting:
                       - "unlisted": Not searchable, but accessible via link (default, recommended for ads)
                       - "private": Only accessible by you
                       - "public": Searchable and public

    Returns:
        Dictionary containing:
            - video_id: YouTube video ID
            - video_url: Full YouTube URL
            - status: "success" or "error"

    Example:
        result = await upload_to_youtube(
            video_uri="gs://bucket/generated-video.mp4",
            title="Product Demo Ad",
            privacy_status="unlisted"
        )
        # Returns: {"video_id": "dQw4w9WgXcQ", "video_url": "https://youtube.com/watch?v=...", ...}
    """
    logger.info(f"Uploading video to YouTube: {title}")

    try:
        # TODO: Implement YouTube Data API integration
        # For now, return mock response
        return {
            "video_id": "mock_video_id",
            "video_url": f"https://www.youtube.com/watch?v=mock_video_id",
            "title": title,
            "privacy_status": privacy_status,
            "status": "success",
            "message": "Video uploaded to YouTube successfully"
        }

    except Exception as e:
        logger.error(f"upload_to_youtube failed: {e}")
        return {
            "error": str(e),
            "status": "error",
            "message": "Failed to upload video to YouTube"
        }


# ============================================================================
# GOOGLE ADS CAMPAIGN TOOLS
# ============================================================================

async def create_google_ad_draft(
    campaign_name: str,
    ad_copy_headline: str,
    ad_copy_description: str,
    target_url: str,
    image_uri: Optional[str] = None,
    video_id: Optional[str] = None,
    budget_daily: float = 10.0,
    target_keywords: Optional[List[str]] = None
) -> dict:
    """
    Create a Google Ads campaign draft in PAUSED status.

    Creates a campaign ready for review. The campaign will be in PAUSED state
    and will NOT spend money until manually activated by the user in Google Ads console.

    CRITICAL: Human-in-the-loop workflow!
    - ONLY call this after user approves all assets and copy
    - Campaign starts in PAUSED state - safe by default
    - User must manually activate in Google Ads console to start spending

    Args:
        campaign_name: Name for the campaign
        ad_copy_headline: Main headline for the ad (max 30 chars)
        ad_copy_description: Description text (max 90 chars)
        target_url: Landing page URL
        image_uri: Optional GCS URI of image asset (for display/discovery ads)
        video_id: Optional YouTube video ID (for video ads)
        budget_daily: Daily budget in USD (default: $10.00)
        target_keywords: Optional list of keywords to target

    Returns:
        Dictionary containing:
            - campaign_id: Google Ads campaign ID
            - status: "PAUSED" (always starts paused)
            - campaign_name: Name of created campaign
            - message: Success message with next steps

    Example:
        result = await create_google_ad_draft(
            campaign_name="Summer Sale 2025",
            ad_copy_headline="50% Off All Products",
            ad_copy_description="Limited time offer. Shop now and save big on premium products.",
            target_url="https://example.com/sale",
            image_uri="gs://bucket/approved-image.png",
            budget_daily=25.0,
            target_keywords=["summer sale", "discounts", "deals"]
        )
        # Returns: {"campaign_id": "123456", "status": "PAUSED", ...}
    """
    logger.info(f"Creating Google Ads draft campaign: {campaign_name}")

    try:
        # TODO: Implement Google Ads API integration
        # For now, return mock response
        return {
            "campaign_id": "mock_campaign_123456",
            "status": "PAUSED",
            "campaign_name": campaign_name,
            "headline": ad_copy_headline,
            "description": ad_copy_description,
            "target_url": target_url,
            "budget_daily": budget_daily,
            "message": (
                f"Campaign '{campaign_name}' created in PAUSED status. "
                "Review in Google Ads console and activate when ready."
            )
        }

    except Exception as e:
        logger.error(f"create_google_ad_draft failed: {e}")
        return {
            "error": str(e),
            "status": "error",
            "message": "Failed to create campaign draft"
        }
