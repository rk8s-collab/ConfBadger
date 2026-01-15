#!/bin/bash

# Wrapper script to generate stickers from CSV file
# Usage: ./generate.sh <csv-file> [--since DATE] [--after ORDER] [--debug]

if [ $# -eq 0 ]; then
    echo "Usage: $0 <csv-file> [--since DATE] [--after ORDER] [--debug]"
    echo ""
    echo "Examples:"
    echo "  $0 2025-11-26-kcd-romandie-participants.csv"
    echo "  $0 data.csv --since 2025-11-20"
    echo "  $0 data.csv --after CNCFE25280709"
    echo "  $0 data.csv --debug"
    exit 1
fi

CSV_FILE="$1"
shift  # Remove first argument, keep the rest for pass-through

# Check if CSV file exists
if [ ! -f "$CSV_FILE" ]; then
    echo "Error: CSV file '$CSV_FILE' not found"
    exit 1
fi

# Derive PDF filename from CSV filename
# Remove .csv extension and add .pdf
PDF_FILE="${CSV_FILE%.csv}.pdf"

echo "Generating stickers from $CSV_FILE -> $PDF_FILE"

# Run the Python script with derived PDF name and pass through any additional arguments
python3 generate_stickers.py --data "$CSV_FILE" --output "$PDF_FILE" "$@"
