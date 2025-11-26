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
    
    # Get layout settings from config
    layout = config_data.get('sticker-labels', {}).get('layout', {})
    fonts = config_data.get('sticker-labels', {}).get('fonts', {})
    truncate = config_data.get('sticker-labels', {}).get('truncate', {})
    banner_config = config_data.get('sticker-labels', {}).get('banner', {})
    
    # Default values if not in config
    qr_margin = layout.get('qr-margin', 3)
    left_margin = layout.get('text-left-margin', 5)
    top_margin = layout.get('text-top-margin', 22)
    qr_text_gap = layout.get('qr-text-gap', 5)
    
    first_name_size = fonts.get('first-name-size', 24)
    last_name_size = fonts.get('last-name-size', 13)
    title_size = fonts.get('title-size', 9)
    company_size = fonts.get('company-size', 9)
    banner_size = fonts.get('banner-size', 16)
    
    first_name_limit = truncate.get('first-name', 15)
    last_name_limit = truncate.get('last-name', 18)
    title_limit = truncate.get('title', 35)
    company_limit = truncate.get('company', 35)
    
    bar_height = banner_config.get('height', 25)
    
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
    
    # QR code dimensions - full height of label with margin
    qr_size = height - (2 * qr_margin)  # Square QR code with margins
    qr_x_pos = width - qr_size - qr_margin  # Position on the right with margin
    
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
    qr_image = shapes.Image(qr_x_pos, qr_margin, qr_size, qr_size, qr_temp_path)
    label.add(qr_image)
    
    # Clean up temp file (will be deleted after the label is drawn)
    # Note: We can't delete it immediately as it needs to exist when the PDF is rendered
    
    # Text area width (leave space for QR code)
    text_area_width = qr_x_pos - left_margin - qr_text_gap
    
    # Starting Y position (from bottom, ReportLab uses bottom-left origin)
    y_pos = height - top_margin
    
    # First Name (large, black, bold)
    # Truncate if too long to prevent overlap with QR code
    first_display = firstname
    if len(firstname) > first_name_limit:
        first_display = firstname[:first_name_limit] + "..."
    label.add(shapes.String(left_margin, y_pos, first_display, 
                           fontName=name_font, fontSize=first_name_size, fillColor=black))
    y_pos -= (first_name_size + 2)  # Space after first name
    
    # Last Name (medium, red, bold)
    # Truncate if too long
    last_display = lastname.upper()
    if len(lastname) > last_name_limit:
        last_display = lastname[:last_name_limit].upper() + "..."
    label.add(shapes.String(left_margin, y_pos, last_display, 
                           fontName=name_font, fontSize=last_name_size, fillColor=red))
    y_pos -= (last_name_size + 3)  # Space after last name
    
    # Title (small, black)
    # Truncate if too long
    if title:
        title_display = title
        if len(title) > title_limit:
            title_display = title[:title_limit] + "..."
        label.add(shapes.String(left_margin, y_pos, title_display, 
                               fontName=regular_font, fontSize=title_size, fillColor=black))
        y_pos -= (title_size + 2)
    
    # Company (small, blue)
    # Truncate if too long
    if company:
        company_display = company
        if len(company) > company_limit:
            company_display = company[:company_limit] + "..."
        label.add(shapes.String(left_margin, y_pos, company_display, 
                               fontName=regular_font, fontSize=company_size, fillColor=blue))
    
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
    bar_rect = shapes.Rect(0, 0, qr_x_pos, bar_height, 
                          fillColor=bar_color, strokeColor=None)
    label.add(bar_rect)
    
    # Center the attendee type text in the colored bar (not including QR area)
    type_string = shapes.String(0, bar_height/2 - (banner_size/2 - 2), attendee_type,
                               fontName=name_font, fontSize=banner_size, fillColor=white,
                               textAnchor='middle')
    type_string.x = qr_x_pos / 2
    label.add(type_string)


def create_label_specification(config_data=None):
    """
    Create label specification from config file
    """
    # Default values
    defaults = {
        'sheet-width': 210,
        'sheet-height': 297,
        'label-width': 105,
        'label-height': 42.3,
        'columns': 2,
        'rows': 7,
        'corner-radius': 0,
        'left-margin': 0,
        'right-margin': 0,
        'top-margin': 0.45,
        'bottom-margin': 0.45,
        'row-gap': 0,
        'column-gap': 0
    }
    
    # Load from config if available
    if config_data and 'sticker-labels' in config_data:
        label_config = config_data['sticker-labels']
        for key in defaults:
            if key in label_config:
                defaults[key] = label_config[key]
    
    specs = labels.Specification(
        sheet_width=defaults['sheet-width'],
        sheet_height=defaults['sheet-height'],
        columns=defaults['columns'],
        rows=defaults['rows'],
        label_width=defaults['label-width'],
        label_height=defaults['label-height'],
        corner_radius=defaults['corner-radius'],
        left_margin=defaults['left-margin'],
        right_margin=defaults['right-margin'],
        top_margin=defaults['top-margin'],
        bottom_margin=defaults['bottom-margin'],
        row_gap=defaults['row-gap'],
        column_gap=defaults['column-gap'],
    )
    return specs


def generate_stickers(csv_file='data.csv', output_file='stickers.pdf', config_file='config.yaml', debug=False):
    """
    Generate sticker labels from CSV file
    
    Args:
        csv_file: Path to CSV file with attendee data
        output_file: Path to output PDF file
        config_file: Path to config file (optional, for future customization)
        debug: If True, show label borders for debugging layout
    """
    logger.info(f"Reading data from {csv_file}")
    
    # Read CSV data
    try:
        df = pd.read_csv(csv_file)
        # Fill NaN values
        df = df.fillna('')
        # Sort by Last Name, then First Name
        df = df.sort_values(by=['Last Name', 'First Name'])
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
    specs = create_label_specification(config_data)
    
    # Create sheet with border based on debug flag
    sheet = labels.Sheet(specs, draw_label, border=debug)
    
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
    parser.add_argument('--debug', action='store_true',
                       help='Show label borders for debugging layout')
    
    args = parser.parse_args()
    
    generate_stickers(args.data, args.output, args.config, args.debug)


if __name__ == '__main__':
    main()
