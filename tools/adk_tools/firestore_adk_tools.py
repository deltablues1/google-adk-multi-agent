"""
Firestore ADK Tools

ADK-compatible tools for Firestore database operations.
Provides CRUD operations for products, quotes, customers, and expense records.
"""

from typing import Optional, Dict, Any, List
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


def _get_db_handler():
    """Get database handler instance"""
    try:
        from tools.database.database_handler import get_database_handler
        return get_database_handler()
    except Exception as e:
        logger.error(f"Failed to get database handler: {e}")
        return None


# ============================================================================
# PRODUCTS TOOLS
# ============================================================================

async def add_product(
    name: str,
    price: float,
    currency: str = "EUR",
    category: str = "",
    description: str = "",
    stock: int = 0,
    sku: str = "",
    supplier: str = ""
) -> dict:
    """
    Add a new product to the products database.

    Args:
        name: Product name (required)
        price: Product price (required)
        currency: Currency code (default: "EUR")
        category: Product category (e.g., "Electronics", "Office Supplies")
        description: Product description
        stock: Current stock quantity (default: 0)
        sku: Stock Keeping Unit / Product code
        supplier: Supplier name

    Returns:
        Dictionary with:
            - product_id: Generated Firestore document ID
            - status: "success" or "error"
            - message: Success/error message

    Example:
        result = await add_product(
            name="Laptop Dell XPS 15",
            price=1299.99,
            category="Electronics",
            sku="DELL-XPS-15",
            stock=5
        )
    """
    logger.info(f"Adding product: {name} ({price} {currency})")

    try:
        db = _get_db_handler()
        if not db:
            return {"error": "Database not available", "status": "error"}

        product_data = {
            "name": name,
            "price": float(price),
            "currency": currency,
            "category": category,
            "description": description,
            "stock": int(stock),
            "sku": sku,
            "supplier": supplier,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        }

        product_id = await db.add_document("products", product_data)

        return {
            "product_id": product_id,
            "status": "success",
            "message": f"Product '{name}' added successfully"
        }

    except Exception as e:
        logger.error(f"add_product failed: {e}")
        return {
            "error": str(e),
            "status": "error",
            "message": f"Failed to add product: {e}"
        }


async def query_products(
    category: Optional[str] = None,
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
    limit: int = 50
) -> dict:
    """
    Query products from the database.

    Args:
        category: Filter by category (optional)
        min_price: Minimum price filter (optional)
        max_price: Maximum price filter (optional)
        limit: Maximum number of results (default: 50)

    Returns:
        Dictionary with:
            - products: List of product dictionaries
            - count: Number of products found
            - status: "success" or "error"

    Example:
        result = await query_products(
            category="Electronics",
            max_price=1000,
            limit=10
        )
    """
    logger.info(f"Querying products (category={category}, price range={min_price}-{max_price})")

    try:
        db = _get_db_handler()
        if not db:
            return {"error": "Database not available", "status": "error"}

        filters = []
        if category:
            filters.append(('category', '==', category))
        if min_price is not None:
            filters.append(('price', '>=', min_price))
        if max_price is not None:
            filters.append(('price', '<=', max_price))

        products = await db.query_documents("products", filters, limit=limit)

        return {
            "products": products,
            "count": len(products),
            "status": "success"
        }

    except Exception as e:
        logger.error(f"query_products failed: {e}")
        return {
            "error": str(e),
            "status": "error",
            "message": f"Failed to query products: {e}"
        }


# ============================================================================
# CUSTOMERS TOOLS
# ============================================================================

async def add_customer(
    name: str,
    email: str,
    company: str = "",
    phone: str = "",
    address: str = "",
    notes: str = ""
) -> dict:
    """
    Add a new customer to the customers database.

    Args:
        name: Customer name (required)
        email: Customer email (required)
        company: Company name
        phone: Phone number
        address: Full address
        notes: Additional notes

    Returns:
        Dictionary with:
            - customer_id: Generated Firestore document ID
            - status: "success" or "error"
            - message: Success/error message

    Example:
        result = await add_customer(
            name="John Doe",
            email="john@example.com",
            company="Acme Corp",
            phone="+385 99 123 4567"
        )
    """
    logger.info(f"Adding customer: {name} ({email})")

    try:
        db = _get_db_handler()
        if not db:
            return {"error": "Database not available", "status": "error"}

        customer_data = {
            "name": name,
            "email": email,
            "company": company,
            "phone": phone,
            "address": address,
            "notes": notes,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        }

        customer_id = await db.add_document("customers", customer_data)

        return {
            "customer_id": customer_id,
            "status": "success",
            "message": f"Customer '{name}' added successfully"
        }

    except Exception as e:
        logger.error(f"add_customer failed: {e}")
        return {
            "error": str(e),
            "status": "error",
            "message": f"Failed to add customer: {e}"
        }


async def find_customer(email: str) -> dict:
    """
    Find a customer by email address.

    Args:
        email: Customer email to search for

    Returns:
        Dictionary with:
            - customer: Customer data if found, None otherwise
            - found: Boolean indicating if customer was found
            - status: "success" or "error"

    Example:
        result = await find_customer("john@example.com")
        if result["found"]:
            print(f"Found: {result['customer']['name']}")
    """
    logger.info(f"Finding customer by email: {email}")

    try:
        db = _get_db_handler()
        if not db:
            return {"error": "Database not available", "status": "error"}

        customers = await db.query_documents("customers", [('email', '==', email)], limit=1)

        if customers:
            return {
                "customer": customers[0],
                "found": True,
                "status": "success"
            }
        else:
            return {
                "customer": None,
                "found": False,
                "status": "success",
                "message": f"No customer found with email: {email}"
            }

    except Exception as e:
        logger.error(f"find_customer failed: {e}")
        return {
            "error": str(e),
            "status": "error",
            "message": f"Failed to find customer: {e}"
        }


# ============================================================================
# QUOTES TOOLS
# ============================================================================

async def create_quote(
    customer_email: str,
    items: List[Dict[str, Any]],
    notes: str = "",
    valid_until: str = ""
) -> dict:
    """
    Create a new quote for a customer.

    Args:
        customer_email: Customer email address (must exist in customers database)
        items: List of items, each with:
            - product_name: Product name
            - quantity: Quantity
            - unit_price: Price per unit
            - (optional) product_id: Product ID if linking to products db
        notes: Additional notes for the quote
        valid_until: Quote validity date (YYYY-MM-DD format)

    Returns:
        Dictionary with:
            - quote_id: Generated Firestore document ID
            - total: Total quote amount
            - status: "success" or "error"
            - message: Success/error message

    Example:
        result = await create_quote(
            customer_email="john@example.com",
            items=[
                {"product_name": "Laptop", "quantity": 2, "unit_price": 999.99},
                {"product_name": "Mouse", "quantity": 2, "unit_price": 29.99}
            ],
            valid_until="2025-02-28"
        )
    """
    logger.info(f"Creating quote for: {customer_email}")

    try:
        db = _get_db_handler()
        if not db:
            return {"error": "Database not available", "status": "error"}

        # Calculate total
        total = sum(item["quantity"] * item["unit_price"] for item in items)

        # Find customer
        customer_result = await find_customer(customer_email)
        customer_id = customer_result.get("customer", {}).get("id") if customer_result.get("found") else None

        quote_data = {
            "customer_email": customer_email,
            "customer_id": customer_id,
            "items": items,
            "total": float(total),
            "currency": "EUR",  # Default, could be parameterized
            "status": "draft",
            "notes": notes,
            "valid_until": valid_until,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        }

        quote_id = await db.add_document("quotes", quote_data)

        return {
            "quote_id": quote_id,
            "total": total,
            "status": "success",
            "message": f"Quote created successfully (Total: {total} EUR)"
        }

    except Exception as e:
        logger.error(f"create_quote failed: {e}")
        return {
            "error": str(e),
            "status": "error",
            "message": f"Failed to create quote: {e}"
        }


# ============================================================================
# EXPENSE RECORDS TOOLS
# ============================================================================

async def add_expense_record(
    vendor: str,
    amount: float,
    currency: str = "EUR",
    date: str = "",
    category: str = "",
    description: str = "",
    invoice_number: str = "",
    payment_method: str = "",
    items: Optional[List[Dict[str, Any]]] = None
) -> dict:
    """
    Add a new expense record from an invoice/receipt.

    Args:
        vendor: Vendor/supplier name (required)
        amount: Total amount (required)
        currency: Currency code (default: "EUR")
        date: Expense date (YYYY-MM-DD format)
        category: Expense category (e.g., "Office Supplies", "Travel")
        description: Expense description
        invoice_number: Invoice/receipt number
        payment_method: Payment method (e.g., "Credit Card", "Cash")
        items: Optional list of line items from invoice

    Returns:
        Dictionary with:
            - expense_id: Generated Firestore document ID
            - status: "success" or "error"
            - message: Success/error message

    Example:
        result = await add_expense_record(
            vendor="Office Depot",
            amount=249.99,
            date="2025-01-15",
            category="Office Supplies",
            invoice_number="INV-2025-001",
            items=[
                {"description": "Paper A4", "quantity": 10, "unit_price": 5.99},
                {"description": "Pens", "quantity": 20, "unit_price": 1.50}
            ]
        )
    """
    logger.info(f"Adding expense record: {vendor} ({amount} {currency})")

    try:
        db = _get_db_handler()
        if not db:
            return {"error": "Database not available", "status": "error"}

        expense_data = {
            "vendor": vendor,
            "amount": float(amount),
            "currency": currency,
            "date": date if date else datetime.utcnow().strftime("%Y-%m-%d"),
            "category": category,
            "description": description,
            "invoice_number": invoice_number,
            "payment_method": payment_method,
            "items": items or [],
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        }

        expense_id = await db.add_document("expense-records", expense_data)

        return {
            "expense_id": expense_id,
            "status": "success",
            "message": f"Expense record added: {vendor} - {amount} {currency}"
        }

    except Exception as e:
        logger.error(f"add_expense_record failed: {e}")
        return {
            "error": str(e),
            "status": "error",
            "message": f"Failed to add expense record: {e}"
        }


async def query_expenses(
    vendor: Optional[str] = None,
    category: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: int = 50
) -> dict:
    """
    Query expense records from the database.

    Args:
        vendor: Filter by vendor name (optional)
        category: Filter by category (optional)
        start_date: Filter by start date (YYYY-MM-DD) (optional)
        end_date: Filter by end date (YYYY-MM-DD) (optional)
        limit: Maximum number of results (default: 50)

    Returns:
        Dictionary with:
            - expenses: List of expense records
            - count: Number of records found
            - total_amount: Sum of all expense amounts
            - status: "success" or "error"

    Example:
        result = await query_expenses(
            category="Office Supplies",
            start_date="2025-01-01",
            end_date="2025-01-31"
        )
    """
    logger.info(f"Querying expenses (vendor={vendor}, category={category})")

    try:
        db = _get_db_handler()
        if not db:
            return {"error": "Database not available", "status": "error"}

        filters = []
        if vendor:
            filters.append(('vendor', '==', vendor))
        if category:
            filters.append(('category', '==', category))
        if start_date:
            filters.append(('date', '>=', start_date))
        if end_date:
            filters.append(('date', '<=', end_date))

        expenses = await db.query_documents("expense-records", filters, limit=limit)

        # Calculate total
        total_amount = sum(exp.get("amount", 0) for exp in expenses)

        return {
            "expenses": expenses,
            "count": len(expenses),
            "total_amount": total_amount,
            "status": "success"
        }

    except Exception as e:
        logger.error(f"query_expenses failed: {e}")
        return {
            "error": str(e),
            "status": "error",
            "message": f"Failed to query expenses: {e}"
        }
