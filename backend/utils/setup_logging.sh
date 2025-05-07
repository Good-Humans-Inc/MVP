#!/bin/bash
# PEP MVP Structured Logging Setup Script
#
# This script helps set up the structured logging system across all backend functions.
# It creates the utils directory structure, updates required files, and converts existing
# Cloud Functions to use the new logging system.

set -e

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
BACKEND_DIR="$(dirname "$SCRIPT_DIR")"
UTILS_DIR="$BACKEND_DIR/utils"

# Color definitions
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}=== PEP MVP Structured Logging Setup ===${NC}"
echo -e "${BLUE}This script will help you implement the structured logging system.${NC}\n"

# Create utils directory if it doesn't exist
if [ ! -d "$UTILS_DIR" ]; then
    echo -e "${YELLOW}Creating utils directory...${NC}"
    mkdir -p "$UTILS_DIR"
fi

# Make sure this script is executable
chmod +x "$SCRIPT_DIR/setup_logging.sh"

# Make sure the logging update tool is executable
chmod +x "$SCRIPT_DIR/logging_update_tool.py"

# Make __init__.py file for utils directory
touch "$UTILS_DIR/__init__.py"
echo -e "${GREEN}Created $UTILS_DIR/__init__.py${NC}"

# List all Cloud Function directories
FUNCTION_DIRS=$(find "$BACKEND_DIR" -maxdepth 1 -type d -not -path "$BACKEND_DIR" -not -path "$BACKEND_DIR/utils" -not -path "$BACKEND_DIR/.hypothesis" -not -path "$BACKEND_DIR/.*")

echo -e "\n${BLUE}Found the following Cloud Function directories:${NC}"
for dir in $FUNCTION_DIRS; do
    echo "- $(basename "$dir")"
done

echo -e "\n${YELLOW}Would you like to update all Cloud Functions with structured logging? (y/n)${NC}"
read -r UPDATE_ALL

if [[ "$UPDATE_ALL" =~ ^[Yy]$ ]]; then
    echo -e "\n${BLUE}Converting all Cloud Functions to use structured logging...${NC}"
    
    for func_dir in $FUNCTION_DIRS; do
        FUNC_NAME=$(basename "$func_dir")
        echo -e "\n${YELLOW}Converting $FUNC_NAME...${NC}"
        
        # Create requirements.txt if it doesn't exist
        if [ ! -f "$func_dir/requirements.txt" ]; then
            echo "google-cloud-logging>=3.0.0" > "$func_dir/requirements.txt"
            echo -e "${GREEN}Created requirements.txt with google-cloud-logging dependency${NC}"
        elif ! grep -q "google-cloud-logging" "$func_dir/requirements.txt"; then
            echo "google-cloud-logging>=3.0.0" >> "$func_dir/requirements.txt"
            echo -e "${GREEN}Added google-cloud-logging to requirements.txt${NC}"
        fi
        
        # Run the conversion tool
        python "$SCRIPT_DIR/logging_update_tool.py" "$func_dir"
    done
    
    echo -e "\n${GREEN}Conversion complete! Please review the changes before deploying.${NC}"
else
    echo -e "\n${BLUE}Skipping automatic conversion.${NC}"
    echo -e "${YELLOW}You can manually convert individual functions with:${NC}"
    echo -e "python $SCRIPT_DIR/logging_update_tool.py <function_directory>"
fi

# Create dashboard
echo -e "\n${YELLOW}Would you like to set up a new logging dashboard in Google Cloud Monitoring? (y/n)${NC}"
read -r SETUP_DASHBOARD

if [[ "$SETUP_DASHBOARD" =~ ^[Yy]$ ]]; then
    echo -e "\n${BLUE}Setting up logging dashboard...${NC}"
    echo -e "${YELLOW}Please follow these steps:${NC}"
    echo -e "1. Go to Google Cloud Console > Monitoring > Dashboards"
    echo -e "2. Click 'Create Dashboard'"
    echo -e "3. Click 'JSON Editor'"
    echo -e "4. Paste the contents of $SCRIPT_DIR/logging_dashboard.json"
    echo -e "5. Click 'Save'"
fi

echo -e "\n${GREEN}Setup complete!${NC}"
echo -e "${BLUE}Here are some next steps:${NC}"
echo -e "1. Review the converted code to ensure it works as expected"
echo -e "2. Deploy the updated functions to Google Cloud"
echo -e "3. Set up Log-based Metrics in Google Cloud Monitoring"
echo -e "4. Create alerts for critical errors"
echo -e "\n${YELLOW}For more information, see $UTILS_DIR/README.md${NC}" 