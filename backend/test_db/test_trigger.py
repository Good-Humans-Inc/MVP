import firebase_admin
from firebase_admin import credentials
from firebase_admin import firestore
import time

# Initialize Firebase Admin
cred = credentials.ApplicationDefault()
firebase_admin.initialize_app(cred, {
    'projectId': 'pepmvp',
})

# Get Firestore client
db = firestore.Client(project='pepmvp', database='default')

def run_test():
    print("Starting Firestore trigger test...")
    
    # Create a test document
    test_doc_ref = db.collection('users').document('test-trigger-user')
    
    # Step 1: Create document
    print("Step 1: Creating test document...")
    test_doc_ref.set({
        'name': 'Test User',
        'test_field': 'initial value',
        'timestamp': firestore.SERVER_TIMESTAMP
    })
    time.sleep(2)  # Wait for trigger to process
    
    # Step 2: Update document
    print("Step 2: Updating test document...")
    test_doc_ref.update({
        'test_field': 'updated value',
        'timestamp': firestore.SERVER_TIMESTAMP
    })
    time.sleep(2)  # Wait for trigger to process
    
    # Step 3: Delete document
    print("Step 3: Deleting test document...")
    test_doc_ref.delete()
    
    print("Test completed! Check the Cloud Functions logs to verify the triggers.")

if __name__ == "__main__":
    run_test() 