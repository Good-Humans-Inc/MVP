#!/usr/bin/env python3
"""
Test script for the update_fcm_token function in the schedule_notification module.
This script simulates HTTP requests to the function for testing purposes.
"""

import json
import argparse
import requests
import sys

def test_update_fcm_token(base_url, patient_id, fcm_token):
    """
    Test the update_fcm_token function with the provided parameters.
    
    Args:
        base_url (str): Base URL of the cloud function
        patient_id (str): ID of the patient to update
        fcm_token (str): Firebase Cloud Messaging token
    
    Returns:
        dict: Response from the cloud function
    """
    url = f"{base_url}/update_fcm_token"
    
    # Prepare request data
    data = {
        "patient_id": patient_id,
        "fcm_token": fcm_token
    }
    
    # Print request data
    print(f"Sending request to {url}")
    print(f"Request data: {json.dumps(data, indent=2)}")
    
    # Send request
    try:
        response = requests.post(url, json=data)
        response_data = response.json()
        
        # Print response
        print(f"Response status code: {response.status_code}")
        print(f"Response data: {json.dumps(response_data, indent=2)}")
        
        return response_data
    except Exception as e:
        print(f"Error: {str(e)}")
        return {"error": str(e)}

def main():
    parser = argparse.ArgumentParser(description="Test the update_fcm_token function")
    parser.add_argument("--base-url", required=True, help="Base URL of the cloud function")
    parser.add_argument("--patient-id", required=True, help="ID of the patient to update")
    parser.add_argument("--fcm-token", required=True, help="Firebase Cloud Messaging token")
    
    args = parser.parse_args()
    
    # Test the function
    test_update_fcm_token(
        args.base_url,
        args.patient_id,
        args.fcm_token
    )

if __name__ == "__main__":
    main() 