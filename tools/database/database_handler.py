"""
Database Handler Tool

Manages interactions with Google Cloud Firestore.
Serves as the backend for Episodic Memory (chat logs) and Semantic Memory (vectors).
"""

import logging
import os
from typing import Dict, Any, List, Optional
from datetime import datetime
from google.cloud import firestore
from google.oauth2 import service_account
from tools.google_api_client import create_api_client_auto

logger = logging.getLogger(__name__)

class DatabaseHandler:
    """
    Handles Firestore operations.
    Singleton pattern to maintain connection.
    """
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(DatabaseHandler, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
            
        self.client = self._initialize_client()
        self._initialized = True

    def _initialize_client(self) -> Optional[firestore.Client]:
        """Initialize Firestore client using default credentials"""
        try:
            import google.auth
            
            # Try using Application Default Credentials first (works better for Firestore)
            try:
                credentials, project_id = google.auth.default()
                logger.info(f"🔥 Connecting to Firestore using ADC (Project: {project_id})...")
                return firestore.Client(project=project_id, credentials=credentials)
            except Exception as e:
                logger.warning(f"ADC failed, falling back to app credentials: {e}")

            # Fallback to app credentials
            api_client = create_api_client_auto()
            credentials = api_client.credentials
            
            # Get project ID from env or credentials
            project_id = os.getenv('GOOGLE_CLOUD_PROJECT')
            if not project_id and hasattr(credentials, 'project_id'):
                project_id = credentials.project_id
                
            if not project_id:
                logger.warning("⚠️ GOOGLE_CLOUD_PROJECT not set. Firestore might fail.")
                
            logger.info(f"🔥 Connecting to Firestore using App Creds (Project: {project_id})...")
            
            return firestore.Client(project=project_id, credentials=credentials)
            
        except Exception as e:
            logger.error(f"❌ Failed to initialize Firestore: {e}")
            return None

    async def add_document(self, collection: str, data: Dict[str, Any], doc_id: Optional[str] = None) -> str:
        """Add a document to a collection"""
        if not self.client:
            logger.error("Firestore client not initialized")
            return ""
            
        try:
            # Add timestamp if missing
            if 'created_at' not in data:
                data['created_at'] = datetime.utcnow()
                
            col_ref = self.client.collection(collection)
            
            if doc_id:
                doc_ref = col_ref.document(doc_id)
                doc_ref.set(data)
            else:
                update_time, doc_ref = col_ref.add(data)
                
            logger.info(f"✅ Document added to '{collection}': {doc_ref.id}")
            return doc_ref.id
            
        except Exception as e:
            logger.error(f"❌ Failed to add document: {e}")
            raise

    async def get_document(self, collection: str, doc_id: str) -> Optional[Dict[str, Any]]:
        """Get a document by ID"""
        if not self.client:
            return None
            
        try:
            doc_ref = self.client.collection(collection).document(doc_id)
            doc = doc_ref.get()
            
            if doc.exists:
                return doc.to_dict()
            else:
                logger.warning(f"Document {doc_id} not found in {collection}")
                return None
                
        except Exception as e:
            logger.error(f"❌ Failed to get document: {e}")
            return None

    async def query_documents(self, collection: str, filters: List[tuple], limit: int = 10) -> List[Dict[str, Any]]:
        """
        Query documents with filters.
        filters = [('field', '==', 'value'), ...]
        """
        if not self.client:
            return []
            
        try:
            query = self.client.collection(collection)
            
            for field, op, value in filters:
                query = query.where(field, op, value)
                
            docs = query.limit(limit).stream()
            # Include document ID in results
            results = []
            for doc in docs:
                data = doc.to_dict()
                data['_id'] = doc.id  # Add document ID
                results.append(data)
            return results
            
        except Exception as e:
            logger.error(f"❌ Failed to query documents: {e}")
            return []

    async def delete_document(self, collection: str, doc_id: str) -> bool:
        """Delete a document"""
        if not self.client:
            return False
            
        try:
            self.client.collection(collection).document(doc_id).delete()
            logger.info(f"🗑️ Document deleted: {doc_id}")
            return True
        except Exception as e:
            logger.error(f"❌ Failed to delete document: {e}")
            return False

    async def delete_documents_by_field(self, collection: str, field: str, value: Any) -> int:
        """
        Delete all documents where field == value.
        Useful for cleaning up old chunks of a file.
        """
        if not self.client:
            return 0
            
        try:
            # Query for documents to delete
            docs = self.client.collection(collection).where(field, '==', value).stream()
            
            count = 0
            batch = self.client.batch()
            
            for doc in docs:
                batch.delete(doc.reference)
                count += 1
                
                # Commit in batches of 500 (Firestore limit)
                if count % 500 == 0:
                    batch.commit()
                    batch = self.client.batch()
            
            # Commit remaining
            if count % 500 != 0:
                batch.commit()
                
            logger.info(f"🗑️ Deleted {count} documents from '{collection}' where {field}={value}")
            return count
            
        except Exception as e:
            logger.error(f"❌ Failed to batch delete documents: {e}")
            return 0

# Global instance
_db_handler = DatabaseHandler()

def get_database_handler() -> DatabaseHandler:
    return _db_handler
