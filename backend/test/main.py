import functions_framework
import time
import json

@functions_framework.http
def wait_and_succeed(request):
    """
    HTTP Cloud Function that waits for 10 seconds and then returns a success message.
    """
    # Wait for 10 seconds
    time.sleep(10)

    # Prepare the response
    response_data = {
        'success': True,
        'message': 'Waited for 10 seconds and successfully completed.'
    }
    
    # Set CORS headers to allow requests from any origin
    headers = {
        'Access-Control-Allow-Origin': '*'
    }

    return (json.dumps(response_data), 200, headers)
