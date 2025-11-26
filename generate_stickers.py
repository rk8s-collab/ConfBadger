#!/usr/bin/env python3
"""
Generate sticker labels from CSV data for 14-per-page A4 sheets (105x42.3mm format)
Compatible with Avery L7163 and similar label sheets
"""

import labels
import pandas as pd
from reportlab.graphics import shapes
from reportlab.lib import colors
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import argparse
import yaml
import logging
import sys
import pyqrcode
import png  # pypng module
import unicodedata
from PIL import Image as PILImage
from io import BytesIO
import tempfile
import os

# Set up logging
logging.basicConfig(
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.FileHandler("generate_stickers.log"),
        logging.StreamHandler()
    ])
logger = logging.getLogger(__name__)


def register_fonts():
    """Register custom fonts if available"""
    try:
        pdfmetrics.registerFont(TTFont('OpenSans-Bold', 'fonts/OpenSans-Bold.ttf'))
        pdfmetrics.registerFont(TTFont('OpenSans-Regular', 'fonts/OpenSans-Regular.ttf'))
        pdfmetrics.registerFont(TTFont('OpenSans-Semibold', 'fonts/OpenSans-Semibold.ttf'))
        return True
    except Exception as e:
        logger.warning(f"Could not register custom fonts: {e}. Using defaults.")
        return False


def draw_label(label, width, height, obj):
    """
    Draw a single label with attendee information
    Layout matches KCD badge style:
    - Top section: First name (large, black), Last name (medium, red)
    - Middle section: Title (small, black), Company (small, blue)
    - Bottom section: Colored bar with attendee type text (white)
    - Right side: QR code
    
    Args:
        label: The label object
        width: Label width in points (105mm ≈ 297.6pt)
        height: Label height in points (42.3mm ≈ 119.9pt)
        obj: Dictionary with attendee data
    """
    firstname = obj.get('First Name', '')
    lastname = obj.get('Last Name', '')
    company = obj.get('Company', '')
    title = obj.get('Title', '')
    ticket_title = obj.get('Ticket title', '')
    email = obj.get('Email', '')
    config_data = obj.get('_config', {})
    
    # Font setup
    try:
        name_font = 'OpenSans-Bold'
        regular_font = 'OpenSans-Regular'
    except:
        name_font = 'Helvetica-Bold'
        regular_font = 'Helvetica'
    
    # Colors
    black = colors.black
    red = colors.HexColor('#CF1313')
    blue = colors.HexColor('#14CED3')
    white = colors.white
    
    # QR code dimensions - full height of label
    qr_size = height  # Square QR code using full height
    qr_x_pos = width - qr_size  # Position on the right
    
    # Generate QR code with vCard data
    vcard_data = f'''BEGIN:VCARD
N:{lastname};{firstname};
FN:{firstname} {lastname}
TITLE:{title}
EMAIL;WORK;INTERNET:{email}
ORG:{company}
VERSION:3.0
END:VCARD'''
    
    qrcode = pyqrcode.create(unicodedata.normalize('NFKD', vcard_data).encode('ascii', 'ignore').decode('ascii'))
    
    # Save QR code to temporary file
    with tempfile.NamedTemporaryFile(mode='wb', suffix='.png', delete=False) as tmp_file:
        qr_temp_path = tmp_file.name
        qrcode.png(qr_temp_path, scale=4)
    
    # Add QR code image to label
    qr_image = shapes.Image(qr_x_pos, 0, qr_size, qr_size, qr_temp_path)
    label.add(qr_image)
    
    # Clean up temp file (will be deleted after the label is drawn)
    # Note: We can't delete it immediately as it needs to exist when the PDF is rendered
    
    # Text area width (leave space for QR code)
    text_area_width = qr_x_pos - 10  # 10pt padding
    
    # Starting Y position (from bottom, ReportLab uses bottom-left origin)
    y_pos = height - 15  # 15pt from top
    
    # First Name (large, black, bold)
    label.add(shapes.String(10, y_pos, firstname, 
                           fontName=name_font, fontSize=20, fillColor=black))
    y_pos -= 22
    
    # Last Name (medium, red, bold)
    label.add(shapes.String(10, y_pos, lastname.upper(), 
                           fontName=name_font, fontSize=11, fillColor=red))
    y_pos -= 15
    
    # Title (small, black)
    if title:
        label.add(shapes.String(10, y_pos, title, 
                               fontName=regular_font, fontSize=8, fillColor=black))
        y_pos -= 11
    
    # Company (small, blue)
    if company:
        label.add(shapes.String(10, y_pos, company, 
                               fontName=regular_font, fontSize=8, fillColor=blue))
    
    # Determine attendee type and color from config
    attendee_type = "ATTENDEE"  # Default
    bar_color = colors.HexColor('#9FDBFF')  # Default blue from config
    
    if config_data and 'attendee-types' in config_data:
        for atype in config_data['attendee-types']:
            if ticket_title in atype.get('ticket-titles', []):
                attendee_type = atype['name'].upper()
                # Parse color from config (format: "R, G, B")
                color_str = atype.get('color', '159, 219, 255')
                rgb_parts = [int(x.strip()) for x in color_str.split(',')]
                bar_color = colors.Color(rgb_parts[0]/255, rgb_parts[1]/255, rgb_parts[2]/255)
                break
    
    # Bottom colored bar with attendee type - only extends to QR code
    bar_height = 25
    bar_rect = shapes.Rect(0, 0, qr_x_pos, bar_height, 
                          fillColor=bar_color, strokeColor=None)
    label.add(bar_rect)
    
    # Center the attendee type text in the colored bar (not including QR area)
    type_string = shapes.String(0, bar_height/2 - 6, attendee_type,
                               fontName=name_font, fontSize=14, fillColor=white,
                               textAnchor='middle')
    type_string.x = qr_x_pos / 2
    label.add(type_string)


def create_label_specification():
    """
    Create label specification for Buroline 500028 (14 labels per A4 sheet)
    105mm x 42.3mm labels, 2 columns x 7 rows
    """
    specs = labels.Specification(
        sheet_width=210,      # A4 width in mm
        sheet_height=297,     # A4 height in mm
        columns=2,            # 2 columns
        rows=7,               # 7 rows = 14 labels total
        label_width=105,      # Label width (Buroline 500028)
        label_height=42.3,    # Label height (Buroline 500028)
        corner_radius=2,      # Rounded corners
        left_margin=0,        # No left margin
        right_margin=0,       # No right margin
        top_margin=0.45,      # Center vertically (0.9mm / 2)
        bottom_margin=0.45,   # Center vertically (0.9mm / 2)
        row_gap=0,            # No gap between rows
        column_gap=0,         # No gap between columns
    )
    return specs


def generate_stickers(csv_file='data.csv', output_file='stickers.pdf', config_file='config.yaml'):
    """
    Generate sticker labels from CSV file
    
    Args:
        csv_file: Path to CSV file with attendee data
        output_file: Path to output PDF file
        config_file: Path to config file (optional, for future customization)
    """
    logger.info(f"Reading data from {csv_file}")
    
    # Read CSV data
    try:
        df = pd.read_csv(csv_file)
        # Fill NaN values
        df = df.fillna('')
    except Exception as e:
        logger.error(f"Error reading CSV file: {e}")
        sys.exit(1)
    
    # Load config
    config_data = {}
    try:
        with open(config_file, 'r') as f:
            config_data = yaml.safe_load(f)
    except Exception as e:
        logger.warning(f"Could not load config file: {e}. Using defaults.")
    
    # Register fonts
    register_fonts()
    
    # Create label specification
    specs = create_label_specification()
    
    # Create sheet
    sheet = labels.Sheet(specs, draw_label, border=False)
    
    # Add each attendee to the sheet
    logger.info(f"Processing {len(df)} attendees")
    for index, row in df.iterrows():
        attendee_data = {
            'First Name': row.get('First Name', ''),
            'Last Name': row.get('Last Name', ''),
            'Company': row.get('Company', ''),
            'Title': row.get('Title', ''),
            'Email': row.get('Email', ''),
            'Ticket title': row.get('Ticket title', ''),
            '_config': config_data  # Pass config to draw function
        }
        sheet.add_label(attendee_data)
    
    # Save PDF
    logger.info(f"Saving sticker labels to {output_file}")
    sheet.save(output_file)
    
    # Calculate pages
    total_labels = len(df)
    pages = (total_labels + 13) // 14  # 14 labels per page
    logger.info(f"Generated {total_labels} labels across {pages} page(s)")
    
    return output_file


def main():
    parser = argparse.ArgumentParser(description='Generate sticker labels from CSV data')
    parser.add_argument('--data', default='data.csv',
                       help='CSV file with attendee data (default: data.csv)')
    parser.add_argument('--output', default='stickers.pdf',
                       help='Output PDF file (default: stickers.pdf)')
    parser.add_argument('--config', default='config.yaml',
                       help='Config file (default: config.yaml)')
    
    args = parser.parse_args()
    
    generate_stickers(args.data, args.output, args.config)


if __name__ == '__main__':
    main()
