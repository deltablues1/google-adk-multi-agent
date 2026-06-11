"""
Setup GCS Bucket for Generated Assets

Run this script once to create the Cloud Storage bucket for marketing assets.
"""

import os
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv()

PROJECT_ID = os.getenv("GOOGLE_CLOUD_PROJECT", "lyrical-star-497817-m3")
LOCATION = os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1")
BUCKET_NAME = os.getenv("GOOGLE_CLOUD_STORAGE_BUCKET", "lyrical-star-497817-m3-assets")

def setup_bucket():
    """Create GCS bucket if it doesn't exist"""
    try:
        from google.cloud import storage

        print(f"Project: {PROJECT_ID}")
        print(f"Location: {LOCATION}")
        print(f"Bucket: {BUCKET_NAME}")
        print()

        client = storage.Client(project=PROJECT_ID)

        # Check if bucket exists
        try:
            bucket = client.get_bucket(BUCKET_NAME)
            print(f"✅ Bucket '{BUCKET_NAME}' already exists!")
            print(f"   Location: {bucket.location}")
            print(f"   Created: {bucket.time_created}")
            return True
        except Exception as e:
            if "404" in str(e) or "Not Found" in str(e):
                print(f"Bucket '{BUCKET_NAME}' not found. Creating...")
            else:
                print(f"Error checking bucket: {e}")

        # Create bucket
        bucket = storage.Bucket(client, BUCKET_NAME)
        bucket.location = LOCATION
        bucket.storage_class = "STANDARD"

        # Set uniform bucket-level access
        bucket.iam_configuration.uniform_bucket_level_access_enabled = True

        # Create the bucket
        client.create_bucket(bucket)

        print(f"✅ Bucket '{BUCKET_NAME}' created successfully!")
        print(f"   Location: {LOCATION}")

        # Create folder structure
        blob = bucket.blob("generated_assets/.keep")
        blob.upload_from_string("")
        print("   Created folder: generated_assets/")

        return True

    except Exception as e:
        print(f"❌ Error: {e}")
        return False

def list_buckets():
    """List all buckets in the project"""
    try:
        from google.cloud import storage
        client = storage.Client(project=PROJECT_ID)

        print(f"\nExisting buckets in project {PROJECT_ID}:")
        buckets = list(client.list_buckets())
        if buckets:
            for bucket in buckets:
                print(f"  - {bucket.name}")
        else:
            print("  (no buckets found)")

    except Exception as e:
        print(f"Error listing buckets: {e}")

if __name__ == "__main__":
    print("=" * 60)
    print("GCS Bucket Setup for Marketing Assets")
    print("=" * 60)
    print()

    list_buckets()
    print()

    success = setup_bucket()

    if success:
        print()
        print("=" * 60)
        print("Next steps:")
        print("  1. Test with: python main.py")
        print("  2. Ask: 'Generiraj sliku za coffee shop oglas'")
        print("=" * 60)
