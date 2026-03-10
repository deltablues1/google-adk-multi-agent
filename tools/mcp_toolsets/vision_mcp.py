"""
Vision MCP Toolset
Defines tools for OCR and image analysis using Gemini 2.5 Flash.
"""

from google.genai.types import Tool, FunctionDeclaration

def get_vision_mcp_tools() -> list[Tool]:
    """
    Returns Vision MCP tools as Google ADK Tool objects.
    """
    tools = [
        Tool(
            function_declarations=[
                FunctionDeclaration(
                    name="extract_receipt_data",
                    description="Extracts structured data from a receipt image (base64 or Drive ID). Returns merchant, date, amount, items, etc.",
                    parameters={
                        "type": "OBJECT",
                        "properties": {
                            "image_data": {
                                "type": "STRING",
                                "description": "Base64 encoded image data OR Google Drive File ID"
                            },
                            "mime_type": {
                                "type": "STRING",
                                "description": "MIME type of the image (e.g., 'image/jpeg'). Optional if Drive ID is used."
                            }
                        },
                        "required": ["image_data"]
                    }
                ),
                FunctionDeclaration(
                    name="categorize_expense",
                    description="Categorizes an expense based on merchant and items.",
                    parameters={
                        "type": "OBJECT",
                        "properties": {
                            "merchant": {
                                "type": "STRING",
                                "description": "Name of the merchant"
                            },
                            "items": {
                                "type": "ARRAY",
                                "items": {"type": "STRING"},
                                "description": "List of items purchased"
                            },
                            "total_amount": {
                                "type": "NUMBER",
                                "description": "Total amount of the expense"
                            }
                        },
                        "required": ["merchant", "total_amount"]
                    }
                )
            ]
        )
    ]
    return tools
