# Conference Badge Generator

A web application for generating and managing conference badges from CSV data. The application allows you to upload
 attendee data, generate badges with QR codes, and search through attendees.

## Features

- Upload CSV files with attendee information
- Generate badges with QR codes containing attendee details
- Search attendees by name, title, company, or ticket type
- Preview and download individual badges
- Real-time search with instant results
- Modern, responsive user interface

## Prerequisites

- Python 3.7 or higher
- Node.js 14 or higher
- npm (Node Package Manager)

## Installation

1. Clone the repository:
```bash
git clone https://github.com/wrkode/ConfBadger.git
cd ConfBadger
```

2. Install Python dependencies:
```bash
pip install -r requirements.txt
```

3. Install Node.js dependencies:
```bash
cd frontend
npm install
```

## Configuration

### Config file

Configuration is stored in a yaml file, which is `config.yaml` by default.

#### Attendee types

Create one list item in `attendee-types` for each attendee type. Each list item should have a `name` which will be
printed to the badge and a `ticket-titles` which is a list of ticket types from the data file.

### Font settings

Each text element has an object in the `fonts` list. The name of the text element defines the font used. If the font
file is not found a default font will be used. `size` defines the size of the text element in points. `syle` defines if 
the text element should be capitlaized. If the value is `"capitals"` then capitalized otherwise not.
Text elements supproted: `first-name`: first name, `last-name`: last name, `title`: title, `company`: company,
`attendee-type`: attendee type. 

### Labels

In the `labels` section any number of text labels can be defined. The `text` attribute of the label is the text, `font`
defines the font with a refernce to the ttf file, `size` defines the size in points, `position` defines the coordinates
of the top left corner of the label, `color` defines the R, G and B values of the text color, `style` defines if the
text should be capitalized with "capitals".

### QR code settings

With the `status` parameter of the `qr-code` section it is possible to define what data is put to the QR code.
"vcard" adds the name, email and company of the participant as a VCARD to the QR code. "hash" adds the Order numbers
only. "false" will not add the QR code at all. 
If the whole `qr-code` section is omitted no QR code will be added If the `status` fields are omitted the VCARD will be
added.

### Customize the code 
#### Fonts

To change the TrueType font used you need to update the source code, update ```font```, ```font2``` and ```font3```
varible to point to your font path.

## Running the Application

You can start both the backend and frontend servers in one of two ways:

### Option 1: Using the startup script (Recommended)
From the root directory, simply run:
```bash
./start.sh
```
This will start both the backend (http://localhost:8000) and frontend (http://localhost:3000) servers concurrently.

### Option 2: Manual startup
If you prefer to start the servers manually:

1. Start the FastAPI backend (from the root directory):
```bash
python3 app.py
```
The backend will be available at http://localhost:8000

2. Start the React frontend (from the frontend directory):
```bash
cd frontend
npm start
```
The frontend will be available at http://localhost:3000

## CSV File Format

The application expects a CSV file downloaded from Bevy with the following columns:
- Order number
- Ticket number
- First Name
- Last Name
- Email
- Twitter
- Company
- Title
- Featured
- Ticket title
- Ticket venue
- Access code
- Discount
- Price
- Currency
- Number of tickets
- Paid by (name)
- Paid by (email)
- Paid date (UTC)
- Checkin Date (UTC)
- Ticket Price Paid

Example CSV format:
```csv
Order number,Ticket number,First Name,Last Name,Email,Twitter,Company,Title,Featured,Ticket title,Ticket venue,Access code,Discount,Price,Currency,Number of tickets,Paid by (name),Paid by (email),Paid date (UTC),Checkin Date (UTC),Ticket Price Paid
CNCFE12345678,CNCFA23456789,Name,Ofaperson,email.ofsomeone@working.here,,,,,Early Bird,In-person,,,45.00,EUR,1,Name Ofaperson,email.ofsomeone@working.here,2025-01-20 15:09:24+00:00,,45.00
```

## Usage

1. **Upload CSV File**
   - Click the "Upload CSV File" button
   - Select your CSV file with attendee information
   - The system will validate the file and generate badges

2. **Search Attendees**
   - Use the search fields to filter attendees by:
     - Name (searches in both first and last name)
     - Title
     - Company
     - Ticket Type
   - Results update automatically as you type
   - Clear individual fields using the X button
   - Reset all filters using the "Clear Search" button

3. **Preview and Download Badges**
   - Each attendee card shows basic information
   - Use the "Preview Badge" button to view the badge in a new tab
   - Use the "Download" button to download the badge

## Command line options

It is possible to generate the badges using `python3 confbadger.py`. Command line options in this case:

```
-h, --help            show this help message and exit
--data DATA           List of attendees in the CSV format as exported from Bevy. Default is data.csv
--save-path SAVE_PATH Path to save the generated badges. Default is ./codes
--template TEMPLATE   Template for the badges. Default is the example KCDAMS2023_Badge_Template.png file
--flags               Adds flags to the badges. False by default.
--config CONFIG       Config file. Default is config.yaml.
```

## Check-in labels on a Brother QL-810W

`label_render.py` renders a single peel-and-stick label for **DK-11202 die-cut
stock (62 x 29mm)**: attendee first name plus a QR of the bare ticket number.
Nothing else goes on it — last name, company and the attendee-type banner are
already on the pre-printed card. This is separate from the A4 sticker sheet
produced by `generate_stickers.py`.

Preview one without a printer (PNG carries 300dpi, so print at 100% scale to
check it physically):

```bash
python3 label_render.py --name Rob --ticket CNCFA23236346 --out preview.png
python3 test_label_render.py
```

### Printing

Install the printing dependency:

```bash
pip install brother_ql
```

Find the printer. **USB is discoverable, network is not** — `discover` raises
`NotImplementedError` on the network backend, so the IP has to come from
elsewhere:

```bash
brother_ql --backend pyusb discover   # macOS also needs: brew install libusb
lpstat -v                             # if already added to macOS, shows the device URI
```

Otherwise take the address from the router's DHCP table, and give the printer a
reservation so it survives a reboot at the venue.

Then print:

```bash
python3 print_label.py --name Rob --ticket CNCFA23236346 \
    --printer tcp://192.168.1.50:9100
```

Useful flags: `--dry-run` builds the instructions without a printer,
`--rotate 180` if the label comes out inverted relative to the card, and
`--threshold` (default 70) if the print looks washed out or too heavy.

The raster is generated at exactly 696x271 pixels because `brother_ql` rejects a
die-cut image of any other size rather than rescaling it.

## Project Structure

```
ConfBadger/
├── app.py                 # FastAPI backend
├── confbadger.py          # Badge generation logic
├── requirements.txt       # Python dependencies
├── data.sample.csv        # Anonymised sample; copy to data.csv to try it
├── label_render.py        # Single DK-11202 check-in label for the QL-810W
├── print_label.py         # Sends one rendered label to the QL-810W
├── KCDAMS2023_Badge_Template.png  # Badge template
├── frontend/              # React frontend
│   ├── package.json
│   ├── public/
│   └── src/
├── badges/                # Generated badges
├── codes/                 # Generated QR codes
├── fonts/                 # Font files
└── flags/                 # Country flag images
```

## Development

- Backend: FastAPI (Python)
- Frontend: React with Material-UI
- Badge Generation: PIL (Python Imaging Library)
- QR Code Generation: PyQRCode

## License

This project is licensed under the MIT License - see the LICENSE file for details.