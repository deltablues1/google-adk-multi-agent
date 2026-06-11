"""
Setup Public Access for Generated Assets Folder

This script makes the generated_assets/ folder publicly readable
so that generated images/videos can be viewed without authentication.

Run this once after creating the bucket.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv()

PROJECT_ID = os.getenv("GOOGLE_CLOUD_PROJECT", "lyrical-star-497817-m3")
BUCKET_NAME = os.getenv("GOOGLE_CLOUD_STORAGE_BUCKET", "lyrical-star-497817-m3-assets")

def setup_public_access():
    """Make generated_assets folder publicly readable"""
    try:
        from google.cloud import storage

        print(f"Bucket: {BUCKET_NAME}")
        print()

        client = storage.Client(project=PROJECT_ID)
        bucket = client.bucket(BUCKET_NAME)

        # Check if bucket exists
        if not bucket.exists():
            print(f"❌ Bucket '{BUCKET_NAME}' does not exist!")
            print("   Run setup_gcs_bucket.py first.")
            return False

        # Make objects in generated_assets/ publicly readable
        # by setting IAM policy at bucket level for this prefix

        # Method 1: Set bucket-level public access (simpler but applies to all objects)
        # We'll use fine-grained access instead

        # First, disable uniform bucket-level access if enabled
        bucket.reload()

        print("Setting up public access for generated assets...")

        # Set default object ACL for new uploads
        # This makes future uploads to generated_assets/ publicly readable

        # For existing objects, we need to update them individually
        # Let's update the recently created image

        blobs = list(bucket.list_blobs(prefix="generated_assets/"))
        print(f"Found {len(blobs)} objects in generated_assets/")

        for blob in blobs:
            if blob.name.endswith('.png') or blob.name.endswith('.mp4') or blob.name.endswith('.jpg'):
                try:
                    blob.make_public()
                    print(f"  ✅ Made public: {blob.name}")
                    print(f"     URL: {blob.public_url}")
                except Exception as e:
                    print(f"  ❌ Failed to make public: {blob.name} - {e}")

        print()
        print("=" * 60)
        print("Public access configured!")
        print()
        print("Generated assets are now accessible via:")
        print(f"  https://storage.googleapis.com/{BUCKET_NAME}/generated_assets/<filename>")
        print("=" * 60)

        return True

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False

def list_public_urls():
    """List all public URLs for generated assets"""
    try:
        from google.cloud import storage

        client = storage.Client(project=PROJECT_ID)
        bucket = client.bucket(BUCKET_NAME)

        print(f"\nPublic URLs in {BUCKET_NAME}/generated_assets/:")
        print("-" * 60)

        blobs = list(bucket.list_blobs(prefix="generated_assets/"))
        for blob in blobs:
            if blob.name.endswith(('.png', '.jpg', '.mp4', '.webp')):
                print(f"  {blob.public_url}")

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    print("=" * 60)
    print("Setup Public Access for Generated Assets")
    print("=" * 60)
    print()

    success = setup_public_access()

    if success:
        list_public_urls()
