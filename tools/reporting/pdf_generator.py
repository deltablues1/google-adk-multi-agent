"""
PDF Generator Tool

Helper class to generate PDF reports using ReportLab.
"""

import logging
import os
from typing import List, Dict, Any
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet

logger = logging.getLogger(__name__)

class PDFGenerator:
    """
    Handles PDF generation.
    """
    
    def generate_pdf(self, filename: str, title: str, data: List[Dict[str, Any]], headers: List[str]) -> str:
        """
        Generates a PDF with a title and a table of data.
        Returns the absolute path of the generated file.
        """
        try:
            logger.info(f"📄 Generating PDF: {filename}...")
            
            doc = SimpleDocTemplate(filename, pagesize=letter)
            elements = []
            styles = getSampleStyleSheet()
            
            # Title
            elements.append(Paragraph(title, styles['Title']))
            elements.append(Spacer(1, 12))
            
            # Table Data
            table_data = [headers] # Header row
            
            for item in data:
                row = [str(item.get(h, "")) for h in headers]
                table_data.append(row)
                
            # Table Style
            table = Table(table_data)
            table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
                ('GRID', (0, 0), (-1, -1), 1, colors.black),
            ]))
            
            elements.append(table)
            
            # Build
            doc.build(elements)
            logger.info(f"✅ PDF generated successfully: {filename}")
            return os.path.abspath(filename)
            
        except Exception as e:
            logger.error(f"❌ Failed to generate PDF: {e}")
            return ""

# Global instance
_pdf_generator = PDFGenerator()

def get_pdf_generator() -> PDFGenerator:
    return _pdf_generator
