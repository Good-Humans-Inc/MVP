#!/usr/bin/env python3
"""
Test script for the update_information cloud function.
This script simulates HTTP requests to the function for testing purposes.
"""

import json
import argparse
import requests
import sys
from datetime import datetime

def test_update_information(base_url, patient_id, notification_time=None, ultimate_goal=None, exercise_routine=None):
    """
    Test the update_information cloud function with the provided parameters.
    
    Args:
        base_url (str): Base URL of the cloud function
        patient_id (str): ID of the patient to update
        notification_time (str, optional): Notification time in HH:MM format
        ultimate_goal (str, optional): Patient's ultimate goal
        exercise_routine (list, optional): List of exercises for the patient's routine
    
    Returns:
        dict: Response from the cloud function
    """
    url = f"{base_url}/update_information"
    
    # Prepare request data
    data = {
        "patient_id": patient_id
    }
    
    if notification_time:
        data["notification_time"] = notification_time
    
    if ultimate_goal:
        data["ultimate_goal"] = ultimate_goal
    
    if exercise_routine:
        data["exercise_routine"] = exercise_routine
    
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
    parser = argparse.ArgumentParser(description="Test the update_information cloud function")
    parser.add_argument("--base-url", required=True, help="Base URL of the cloud function")
    parser.add_argument("--patient-id", required=True, help="ID of the patient to update")
    parser.add_argument("--notification-time", help="Notification time in HH:MM format")
    parser.add_argument("--ultimate-goal", help="Patient's ultimate goal")
    parser.add_argument("--exercise-routine", help="Path to JSON file containing exercise routine")
    
    args = parser.parse_args()
    
    # Load exercise routine from file if provided
    exercise_routine = None
    if args.exercise_routine:
        try:
            with open(args.exercise_routine, 'r') as f:
                exercise_routine = json.load(f)
        except Exception as e:
            print(f"Error loading exercise routine: {str(e)}")
            sys.exit(1)
    
    # Test the function
    test_update_information(
        args.base_url,
        args.patient_id,
        args.notification_time,
        args.ultimate_goal,
        exercise_routine
    )

if __name__ == "__main__":
    main() 