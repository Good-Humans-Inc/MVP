#!/usr/bin/env python3
"""
Logging Update Tool

This script helps update existing Cloud Functions to use the new structured logging system.
It performs a series of replacements to convert standard logging to structured logging.

Usage:
  python logging_update_tool.py path/to/function_folder

Example:
  python logging_update_tool.py ../schedule_notification
"""

import os
import re
import sys
import glob
from pathlib import Path

# Patterns to find and replace
REPLACEMENT_PATTERNS = [
    # Import statements
    (
        r'import logging\s*\n\s*# Configure logging\s*\n\s*logging\.basicConfig\(.*\)\s*\n\s*logger\s*=\s*logging\.getLogger\(__name__\)',
        'import sys\nimport os\n\n# Add parent directory to path to import shared modules\nsys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), \'..\')))\nfrom utils.logging_utils import create_logger, log_function_call, log_user_activity\n\n# Create structured logger\nlog = create_logger(\'$SERVICE_NAME\')'
    ),
    # Function decorators
    (
        r'@functions_framework.http\s*\ndef\s+(\w+)',
        '@functions_framework.http\n@log_function_call(log)\ndef \\1'
    ),
    # Simple info logs
    (
        r'logger\.info\(f"([^"]+)"\)',
        'log.info("\\1")'
    ),
    # Simple error logs
    (
        r'logger\.error\(f"([^"]+)"\)',
        'log.error("\\1")'
    ),
    # Simple warning logs
    (
        r'logger\.warning\(f"([^"]+)"\)',
        'log.warning("\\1")'
    ),
    # Add context to user_id
    (
        r'user_id\s*=\s*request_json\.get\(\'user_id\'\)(\s*\n)',
        'user_id = request_json.get(\'user_id\')\\1\n        # Update logger context with user_id\n        log.set_context(user_id=user_id)\\1'
    ),
    # Convert simple print statements
    (
        r'print\(f"([^"]+)"\)',
        'log.info("\\1")'
    ),
]

# Function to process a file
def process_file(file_path, service_name):
    print(f"Processing {file_path}...")
    
    # Read the file
    with open(file_path, 'r') as f:
        content = f.read()
    
    # Apply replacements
    for pattern, replacement in REPLACEMENT_PATTERNS:
        # Replace service name placeholder
        actual_replacement = replacement.replace('$SERVICE_NAME', service_name)
        content = re.sub(pattern, actual_replacement, content)
    
    # Write the updated content
    with open(file_path, 'w') as f:
        f.write(content)
    
    print(f"Updated {file_path}")

def main():
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} path/to/function_folder")
        sys.exit(1)
    
    function_path = sys.argv[1]
    if not os.path.isdir(function_path):
        print(f"Error: {function_path} is not a directory")
        sys.exit(1)
    
    # Get the service name from the folder name
    service_name = os.path.basename(os.path.abspath(function_path))
    print(f"Service name: {service_name}")
    
    # Find Python files to process
    python_files = glob.glob(os.path.join(function_path, "*.py"))
    
    if not python_files:
        print(f"No Python files found in {function_path}")
        sys.exit(1)
    
    # Process each file
    for file_path in python_files:
        process_file(file_path, service_name)
    
    print(f"Successfully updated {len(python_files)} files in {service_name}")
    print("\nNext steps:")
    print("1. Review the changes manually to ensure they make sense")
    print("2. Update any complex logging patterns that couldn't be automatically converted")
    print("3. Test the function locally before deploying")

if __name__ == "__main__":
    main() 