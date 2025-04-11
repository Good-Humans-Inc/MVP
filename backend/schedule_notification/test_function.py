#!/usr/bin/env python3
"""
Test script for the schedule_notification cloud function.
This script simulates HTTP requests to the function for testing purposes.
"""

import json
import argparse
import requests
import sys
from datetime import datetime, timedelta

def test_schedule_notification(base_url, patient_id, notification_type, scheduled_time=None, exercise_id=None):
    """
    Test the schedule_notification cloud function with the provided parameters.
    
    Args:
        base_url (str): Base URL of the cloud function
        patient_id (str): ID of the patient to notify
        notification_type (str): Type of notification (e.g., 'exercise_reminder')
        scheduled_time (str, optional): Scheduled time in ISO 8601 format
        exercise_id (str, optional): ID of the exercise to remind about
    
    Returns:
        dict: Response from the cloud function
    """
    url = f"{base_url}/schedule_notification"
    
    # If scheduled_time is not provided, default to 5 minutes from now
    if not scheduled_time:
        scheduled_time = (datetime.now() + timedelta(minutes=5)).isoformat() + 'Z'
    
    # Prepare request data
    data = {
        "patient_id": patient_id,
        "notification_type": notification_type,
        "scheduled_time": scheduled_time
    }
    
    if exercise_id:
        data["exercise_id"] = exercise_id
    
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
    parser = argparse.ArgumentParser(description="Test the schedule_notification cloud function")
    parser.add_argument("--base-url", required=True, help="Base URL of the cloud function")
    parser.add_argument("--patient-id", required=True, help="ID of the patient to notify")
    parser.add_argument("--notification-type", default="exercise_reminder", help="Type of notification")
    parser.add_argument("--scheduled-time", help="Scheduled time in ISO 8601 format (default: 5 minutes from now)")
    parser.add_argument("--exercise-id", help="ID of the exercise to remind about")
    
    args = parser.parse_args()
    
    # Test the function
    test_schedule_notification(
        args.base_url,
        args.patient_id,
        args.notification_type,
        args.scheduled_time,
        args.exercise_id
    )

if __name__ == "__main__":
    main() 