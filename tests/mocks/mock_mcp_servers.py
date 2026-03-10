"""
Mock MCP Server Implementations

Provides mock implementations for testing MCP integrations
"""

from unittest.mock import MagicMock, Mock
from typing import Dict, List, Any


class MockGmailMCPServer:
    """Mock Gmail MCP Server for testing"""
    
    def __init__(self):
        self.threads = {
            "thread-1": {
                "id": "thread-1",
                "snippet": "Test email thread",
                "messages": [
                    {
                        "id": "msg-1",
                        "threadId": "thread-1",
                        "from": "test@example.com",
                        "to": "user@example.com",
                        "subject": "Test Email",
                        "body": "This is a test email"
                    }
                ]
            }
        }
        self.sent_messages = []
        self.drafts = []
    
    def search_threads(self, query: str, max_results: int = 10) -> List[Dict]:
        """Mock search threads"""
        return [
            {"id": tid, "snippet": data["snippet"]}
            for tid, data in list(self.threads.items())[:max_results]
        ]
    
    def get_thread(self, thread_id: str) -> Dict:
        """Mock get thread"""
        return self.threads.get(thread_id, {})
    
    def send_message(self, to: str, subject: str, body: str, **kwargs) -> Dict:
        """Mock send message"""
        msg = {
            "id": f"msg-{len(self.sent_messages) + 1}",
            "to": to,
            "subject": subject,
            "body": body,
            **kwargs
        }
        self.sent_messages.append(msg)
        return {"id": msg["id"], "status": "sent"}
    
    def create_draft(self, to: str, subject: str, body: str, **kwargs) -> Dict:
        """Mock create draft"""
        draft = {
            "id": f"draft-{len(self.drafts) + 1}",
            "to": to,
            "subject": subject,
            "body": body,
            **kwargs
        }
        self.drafts.append(draft)
        return {"id": draft["id"], "status": "draft"}


class MockDriveMCPServer:
    """Mock Drive MCP Server for testing"""
    
    def __init__(self):
        self.files = {
            "file-1": {
                "id": "file-1",
                "name": "test-document.docx",
                "mimeType": "application/vnd.google-apps.document",
                "owners": [{"emailAddress": "owner@example.com"}]
            },
            "file-2": {
                "id": "file-2",
                "name": "budget-2024.xlsx",
                "mimeType": "application/vnd.google-apps.spreadsheet",
                "owners": [{"emailAddress": "owner@example.com"}]
            }
        }
    
    def search_files(self, query: str, max_results: int = 10) -> List[Dict]:
        """Mock search files"""
        # Simple search by name
        results = []
        for fid, fdata in self.files.items():
            if query.lower() in fdata["name"].lower():
                results.append(fdata)
        return results[:max_results]
    
    def get_file(self, file_id: str) -> Dict:
        """Mock get file"""
        return self.files.get(file_id, {})
    
    def upload_file(self, file_name: str, content: str, mime_type: str) -> Dict:
        """Mock upload file"""
        file_id = f"file-{len(self.files) + 1}"
        self.files[file_id] = {
            "id": file_id,
            "name": file_name,
            "mimeType": mime_type,
            "content": content
        }
        return {"id": file_id, "status": "uploaded"}


class MockDocsMCPServer:
    """Mock Docs MCP Server for testing"""
    
    def __init__(self):
        self.documents = {}
    
    def create_document(self, title: str) -> Dict:
        """Mock create document"""
        doc_id = f"doc-{len(self.documents) + 1}"
        self.documents[doc_id] = {
            "documentId": doc_id,
            "title": title,
            "body": {"content": []}
        }
        return {"documentId": doc_id}
    
    def get_document(self, document_id: str) -> Dict:
        """Mock get document"""
        return self.documents.get(document_id, {})
    
    def insert_text(self, document_id: str, text: str, index: int = 1) -> Dict:
        """Mock insert text"""
        if document_id in self.documents:
            return {"documentId": document_id, "status": "inserted"}
        return {"error": "Document not found"}


class MockSheetsMCPServer:
    """Mock Sheets MCP Server for testing"""
    
    def __init__(self):
        self.spreadsheets = {}
    
    def create_spreadsheet(self, title: str) -> Dict:
        """Mock create spreadsheet"""
        sheet_id = f"sheet-{len(self.spreadsheets) + 1}"
        self.spreadsheets[sheet_id] = {
            "spreadsheetId": sheet_id,
            "properties": {"title": title},
            "sheets": [{"properties": {"title": "Sheet1"}}]
        }
        return {"spreadsheetId": sheet_id}
    
    def read_range(self, spreadsheet_id: str, range_name: str) -> Dict:
        """Mock read range"""
        return {
            "range": range_name,
            "values": [
                ["Header1", "Header2", "Header3"],
                ["Value1", "Value2", "Value3"]
            ]
        }
    
    def write_range(self, spreadsheet_id: str, range_name: str, values: List) -> Dict:
        """Mock write range"""
        return {"updatedCells": len(values), "status": "updated"}


class MockCalendarMCPServer:
    """Mock Calendar MCP Server for testing"""

    def __init__(self):
        self.events = {}

    def create_event(self, summary: str, start_time: str, end_time: str, **kwargs) -> Dict:
        """Mock create event"""
        event_id = f"event-{len(self.events) + 1}"
        self.events[event_id] = {
            "id": event_id,
            "summary": summary,
            "start": {"dateTime": start_time},
            "end": {"dateTime": end_time},
            **kwargs
        }
        return {"id": event_id, "status": "confirmed"}

    def list_events(self, time_min: str, time_max: str = None, max_results: int = 10) -> List[Dict]:
        """Mock list events"""
        return list(self.events.values())[:max_results]


class MockContactsMCPServer:
    """Mock Contacts MCP Server for testing"""

    def __init__(self):
        self.contacts = {
            "person-1": {
                "resourceName": "person-1",
                "emailAddresses": [{"value": "john.doe@example.com"}],
                "names": [{"displayName": "John Doe"}],
                "phoneNumbers": [{"value": "+1-555-0100"}]
            },
            "person-2": {
                "resourceName": "person-2",
                "emailAddresses": [{"value": "jane.smith@example.com"}],
                "names": [{"displayName": "Jane Smith"}],
                "phoneNumbers": [{"value": "+1-555-0101"}]
            }
        }

    def search_contacts(self, query: str, max_results: int = 10) -> List[Dict]:
        """Mock search contacts"""
        results = []
        query_lower = query.lower()
        for cid, contact in self.contacts.items():
            # Search by name or email
            name = contact.get("names", [{}])[0].get("displayName", "").lower()
            email = contact.get("emailAddresses", [{}])[0].get("value", "").lower()
            if query_lower in name or query_lower in email:
                results.append(contact)
        return results[:max_results]

    def get_contact(self, resource_name: str) -> Dict:
        """Mock get contact"""
        return self.contacts.get(resource_name, {})

    def create_contact(self, name: str, email: str, phone: str = None) -> Dict:
        """Mock create contact"""
        resource_name = f"person-{len(self.contacts) + 1}"
        contact = {
            "resourceName": resource_name,
            "names": [{"displayName": name}],
            "emailAddresses": [{"value": email}]
        }
        if phone:
            contact["phoneNumbers"] = [{"value": phone}]
        self.contacts[resource_name] = contact
        return {"resourceName": resource_name, "status": "created"}


class MockTasksMCPServer:
    """Mock Tasks MCP Server for testing"""

    def __init__(self):
        self.task_lists = {
            "list-1": {
                "id": "list-1",
                "title": "My Tasks",
                "tasks": {}
            }
        }

    def list_task_lists(self) -> List[Dict]:
        """Mock list task lists"""
        return [{"id": lid, "title": data["title"]} for lid, data in self.task_lists.items()]

    def create_task(self, task_list_id: str, title: str, notes: str = None, due: str = None) -> Dict:
        """Mock create task"""
        if task_list_id not in self.task_lists:
            return {"error": "Task list not found"}

        task_id = f"task-{len(self.task_lists[task_list_id]['tasks']) + 1}"
        task = {
            "id": task_id,
            "title": title,
            "notes": notes,
            "due": due,
            "status": "needsAction"
        }
        self.task_lists[task_list_id]["tasks"][task_id] = task
        return {"id": task_id, "status": "created"}

    def list_tasks(self, task_list_id: str, max_results: int = 10) -> List[Dict]:
        """Mock list tasks"""
        if task_list_id not in self.task_lists:
            return []
        return list(self.task_lists[task_list_id]["tasks"].values())[:max_results]

    def update_task(self, task_list_id: str, task_id: str, status: str = None, **kwargs) -> Dict:
        """Mock update task"""
        if task_list_id in self.task_lists and task_id in self.task_lists[task_list_id]["tasks"]:
            if status:
                self.task_lists[task_list_id]["tasks"][task_id]["status"] = status
            return {"id": task_id, "status": "updated"}
        return {"error": "Task not found"}


class MockFirecrawlMCPServer:
    """Mock Firecrawl MCP Server for testing"""

    def __init__(self):
        self.scraped_pages = {}

    def scrape(self, url: str, formats: List[str] = None) -> Dict:
        """Mock scrape single page"""
        # Return mock markdown content
        mock_content = f"""# Page Title from {url}

This is mock content scraped from {url}.

## Section 1
Lorem ipsum dolor sit amet, consectetur adipiscing elit.

## Section 2
- Point 1
- Point 2
- Point 3

**Important:** This is mock data for testing.
"""
        self.scraped_pages[url] = mock_content
        return {
            "success": True,
            "markdown": mock_content,
            "html": f"<html><body>{mock_content}</body></html>",
            "metadata": {
                "title": f"Page Title from {url}",
                "description": "Mock description",
                "url": url
            }
        }

    def crawl(self, url: str, max_depth: int = 2, limit: int = 10) -> Dict:
        """Mock crawl website"""
        # Return mock crawled pages
        pages = []
        for i in range(min(limit, 5)):
            page_url = f"{url}/page-{i+1}"
            pages.append({
                "url": page_url,
                "markdown": f"# Page {i+1}\n\nContent from {page_url}",
                "metadata": {"title": f"Page {i+1}"}
            })
        return {
            "success": True,
            "pages": pages,
            "total": len(pages)
        }

    def search(self, query: str, max_results: int = 5) -> Dict:
        """Mock search web"""
        # Return mock search results
        results = []
        for i in range(min(max_results, 3)):
            results.append({
                "url": f"https://example.com/result-{i+1}",
                "title": f"Search Result {i+1} for: {query}",
                "markdown": f"# Result {i+1}\n\nContent related to {query}",
                "metadata": {"description": f"Description for result {i+1}"}
            })
        return {
            "success": True,
            "results": results,
            "total": len(results)
        }

    def extract(self, url: str, schema: Dict) -> Dict:
        """Mock extract structured data"""
        # Return mock extracted data based on schema
        return {
            "success": True,
            "data": {
                "title": "Mock Extracted Title",
                "content": "Mock extracted content",
                "metadata": {"source": url}
            }
        }


class MockAgentQLMCPServer:
    """Mock AgentQL MCP Server for testing"""

    def __init__(self):
        pass

    def query(self, url: str, query: str) -> Dict:
        """Mock AgentQL query"""
        # Return mock structured data
        return {
            "success": True,
            "data": {
                "product_name": "Mock Product",
                "price": 29.99,
                "rating": 4.5,
                "reviews_count": 1234,
                "availability": "In Stock"
            },
            "url": url,
            "query": query
        }

    def extract_schema(self, url: str, schema: Dict) -> Dict:
        """Mock extract with schema"""
        # Return data matching schema structure
        return {
            "success": True,
            "data": {
                "product": {
                    "name": "Mock Product",
                    "price": 29.99,
                    "specs": ["Spec 1", "Spec 2", "Spec 3"]
                },
                "seller": {
                    "name": "Mock Seller",
                    "rating": 4.8
                }
            }
        }

    def extract_list(self, url: str, description: str, max_items: int = 10) -> Dict:
        """Mock extract list of items"""
        # Return mock list
        items = []
        for i in range(min(max_items, 5)):
            items.append({
                "title": f"Item {i+1}",
                "price": 19.99 + (i * 10),
                "rating": 4.0 + (i * 0.1)
            })
        return {
            "success": True,
            "items": items,
            "total": len(items)
        }

    def extract_table(self, url: str, table_selector: str = None) -> Dict:
        """Mock extract table"""
        # Return mock table data
        return {
            "success": True,
            "headers": ["Column 1", "Column 2", "Column 3"],
            "rows": [
                ["Row 1 Col 1", "Row 1 Col 2", "Row 1 Col 3"],
                ["Row 2 Col 1", "Row 2 Col 2", "Row 2 Col 3"],
                ["Row 3 Col 1", "Row 3 Col 2", "Row 3 Col 3"]
            ]
        }

    def screenshot(self, url: str, full_page: bool = False) -> Dict:
        """Mock screenshot"""
        return {
            "success": True,
            "screenshot_path": f"/mock/screenshots/{url.replace('/', '_')}.png",
            "url": url
        }


# Factory functions for easy mock creation

def create_mock_gmail_server() -> MockGmailMCPServer:
    """Create mock Gmail server"""
    return MockGmailMCPServer()


def create_mock_drive_server() -> MockDriveMCPServer:
    """Create mock Drive server"""
    return MockDriveMCPServer()


def create_mock_docs_server() -> MockDocsMCPServer:
    """Create mock Docs server"""
    return MockDocsMCPServer()


def create_mock_sheets_server() -> MockSheetsMCPServer:
    """Create mock Sheets server"""
    return MockSheetsMCPServer()


def create_mock_calendar_server() -> MockCalendarMCPServer:
    """Create mock Calendar server"""
    return MockCalendarMCPServer()


def create_mock_contacts_server() -> MockContactsMCPServer:
    """Create mock Contacts server"""
    return MockContactsMCPServer()


def create_mock_tasks_server() -> MockTasksMCPServer:
    """Create mock Tasks server"""
    return MockTasksMCPServer()


def create_mock_firecrawl_server() -> MockFirecrawlMCPServer:
    """Create mock Firecrawl server"""
    return MockFirecrawlMCPServer()


def create_mock_agentql_server() -> MockAgentQLMCPServer:
    """Create mock AgentQL server"""
    return MockAgentQLMCPServer()
