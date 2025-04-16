import requests
import base64
import os
from pathlib import Path

def test_analyze_exercise_poses():
    # Cloud Function URL
    FUNCTION_URL = "https://YOUR_REGION-YOUR_PROJECT.cloudfunctions.net/analyze_exercise_poses"
    
    # Test image path - you can use any test image
    TEST_IMAGE_PATH = "test_image.jpg"
    
    # Check if test image exists
    if not Path(TEST_IMAGE_PATH).exists():
        print(f"❌ Test image not found at {TEST_IMAGE_PATH}")
        return
    
    try:
        # Read and encode test image
        with open(TEST_IMAGE_PATH, "rb") as image_file:
            encoded_image = base64.b64encode(image_file.read()).decode('utf-8')
        
        # Create test payload
        payload = {
            "images": [encoded_image] * 8,  # Send the same image 8 times for testing
            "exerciseInfo": {
                "userId": "test_user_123",
                "exerciseId": "test_exercise_456",
                "name": "Wrist Extension",
                "instructions": "Extend your wrist upward while keeping your arm steady"
            }
        }
        
        print("🚀 Sending request to cloud function...")
        
        # Make the request
        response = requests.post(
            FUNCTION_URL,
            json=payload,
            headers={"Content-Type": "application/json"}
        )
        
        # Print response details
        print(f"\nStatus Code: {response.status_code}")
        print("\nResponse Headers:")
        for key, value in response.headers.items():
            print(f"{key}: {value}")
        
        print("\nResponse Body:")
        print(response.json())
        
    except Exception as e:
        print(f"❌ Error: {str(e)}")

if __name__ == "__main__":
    test_analyze_exercise_poses() 