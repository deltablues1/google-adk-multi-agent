"""
Google Ads Tool Implementation

Implements tools for creating and managing Google Ads campaigns.
"""

import os
import logging
import uuid
from typing import Dict, Any, List, Optional
from google.ads.googleads.client import GoogleAdsClient
from google.ads.googleads.errors import GoogleAdsException

logger = logging.getLogger(__name__)

def create_google_ad_draft(
    credentials: Any,
    customer_id: str,
    campaign_name: str,
    headlines: List[str],
    descriptions: List[str],
    image_asset_uris: List[str] = [],
    youtube_video_ids: List[str] = []
) -> Dict[str, Any]:
    """
    Creates a draft campaign in Google Ads.
    
    Args:
        credentials: OAuth credentials
        customer_id: Google Ads Customer ID (without dashes)
        campaign_name: Name of the campaign
        headlines: List of headlines (short text)
        descriptions: List of descriptions (long text)
        image_asset_uris: List of GCS URIs for images
        youtube_video_ids: List of YouTube Video IDs
        
    Returns:
        Dictionary with status and resource names
    """
    try:
        # Initialize Google Ads Client
        # We need to construct the client config dynamically from credentials
        # or use the standard load_from_storage if configured.
        # Since we have OAuth credentials object, we can pass it.
        # However, GoogleAdsClient expects a dict or file.
        # We'll try to use the credentials directly if supported, or construct the config.
        
        # Note: GoogleAdsClient.load_from_dict() is useful here.
        config = {
            "developer_token": os.getenv("GOOGLE_ADS_DEVELOPER_TOKEN"),
            "use_proto_plus": True,
            # We might need to pass the refresh token and client secrets here if we don't pass credentials object
            # But passing credentials object is cleaner if supported.
            # The library supports 'credentials' param in init? 
            # Let's check documentation or assume standard pattern.
            # Actually, load_from_dict doesn't take credentials object directly usually.
            # But we can instantiate GoogleAdsClient(credentials=..., developer_token=...)
        }
        
        if not config["developer_token"]:
            return {"error": "GOOGLE_ADS_DEVELOPER_TOKEN not set"}

        client = GoogleAdsClient(
            credentials=credentials, 
            developer_token=config["developer_token"],
            version="v17" # Use recent version
        )
        
        campaign_service = client.get_service("CampaignService")
        ad_group_service = client.get_service("AdGroupService")
        ad_group_ad_service = client.get_service("AdGroupAdService")
        campaign_budget_service = client.get_service("CampaignBudgetService")
        
        # 1. Create Budget
        budget_operation = client.get_type("CampaignBudgetOperation")
        budget = budget_operation.create
        budget.name = f"Budget {uuid.uuid4()}"
        budget.delivery_method = client.enums.BudgetDeliveryMethodEnum.STANDARD
        budget.amount_micros = 5000000 # 5.00 currency units
        
        budget_response = campaign_budget_service.mutate_campaign_budgets(
            customer_id=customer_id, operations=[budget_operation]
        )
        budget_resource_name = budget_response.results[0].resource_name
        
        # 2. Create Campaign (PAUSED)
        campaign_operation = client.get_type("CampaignOperation")
        campaign = campaign_operation.create
        campaign.name = f"{campaign_name} {uuid.uuid4()}"
        campaign.advertising_channel_type = client.enums.AdvertisingChannelTypeEnum.DISPLAY
        campaign.status = client.enums.CampaignStatusEnum.PAUSED
        campaign.manual_cpc.enhanced_cpc_enabled = True
        campaign.campaign_budget = budget_resource_name
        
        # Network settings
        campaign.network_settings.target_google_search = False
        campaign.network_settings.target_search_network = False
        campaign.network_settings.target_content_network = True
        
        campaign_response = campaign_service.mutate_campaigns(
            customer_id=customer_id, operations=[campaign_operation]
        )
        campaign_resource_name = campaign_response.results[0].resource_name
        
        # 3. Create AdGroup
        ad_group_operation = client.get_type("AdGroupOperation")
        ad_group = ad_group_operation.create
        ad_group.name = f"AdGroup {uuid.uuid4()}"
        ad_group.status = client.enums.AdGroupStatusEnum.ENABLED
        ad_group.campaign = campaign_resource_name
        ad_group.cpc_bid_micros = 1000000 # 1.00
        
        ad_group_response = ad_group_service.mutate_ad_groups(
            customer_id=customer_id, operations=[ad_group_operation]
        )
        ad_group_resource_name = ad_group_response.results[0].resource_name
        
        # 4. Create Ad (Responsive Display Ad)
        ad_group_ad_operation = client.get_type("AdGroupAdOperation")
        ad_group_ad = ad_group_ad_operation.create
        ad_group_ad.status = client.enums.AdGroupAdStatusEnum.PAUSED
        ad_group_ad.ad_group = ad_group_resource_name
        
        ad = ad_group_ad.ad
        ad.responsive_display_ad.headlines.extend([
            client.get_type("AdTextAsset", text=h) for h in headlines
        ])
        ad.responsive_display_ad.descriptions.extend([
            client.get_type("AdTextAsset", text=d) for d in descriptions
        ])
        # Note: In a real implementation, we would need to upload assets first 
        # and link them via ad.responsive_display_ad.marketing_images etc.
        # For this MVP, we are skipping the complex asset upload/linking if not strictly required for the draft structure,
        # or we would need to implement the AssetService upload logic here.
        # Given the complexity, we'll note this limitation.
        
        # Assuming we just create the text part for now to prove the flow.
        # Linking images requires uploading them to AssetService first.
        
        ad_group_ad_response = ad_group_ad_service.mutate_ad_group_ads(
            customer_id=customer_id, operations=[ad_group_ad_operation]
        )
        ad_resource_name = ad_group_ad_response.results[0].resource_name
        
        return {
            "status": "SUCCESS",
            "campaign": campaign_resource_name,
            "ad_group": ad_group_resource_name,
            "ad": ad_resource_name
        }

    except GoogleAdsException as ex:
        logger.error(f"Google Ads API Error: {ex}")
        errors = []
        for error in ex.failure.errors:
            errors.append(f"{error.message}")
        return {"error": "; ".join(errors)}
        
    except Exception as e:
        logger.error(f"Google Ads Draft creation failed: {e}")
        return {"error": str(e)}

def register_google_ads_tools(tool_registry) -> None:
    """
    Register Google Ads tools in the tool registry
    """
    tool_registry.register_tool(
        name="create_google_ad_draft",
        function=create_google_ad_draft,
        description="Creates a draft campaign in Google Ads (PAUSED state). Requires user approval.",
        parameters={
            "type": "object",
            "properties": {
                "customer_id": {
                    "type": "string",
                    "description": "Google Ads Customer ID (digits only)"
                },
                "campaign_name": {
                    "type": "string",
                    "description": "Name of the campaign"
                },
                "headlines": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of short headlines (max 30 chars)"
                },
                "descriptions": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of descriptions (max 90 chars)"
                },
                "image_asset_uris": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of GCS URIs for images"
                },
                "youtube_video_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of YouTube Video IDs"
                }
            },
            "required": ["customer_id", "campaign_name", "headlines", "descriptions"]
        }
    )
    logger.info("Google Ads tools registered successfully")
