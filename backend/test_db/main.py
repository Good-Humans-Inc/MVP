import functions_framework

@functions_framework.cloud_event
def monitor_user_changes(cloud_event):
    """Triggered by a Firestore document change."""
    data = cloud_event.data

    old_fields = data.get('oldValue', {}).get('fields', {})
    new_fields = data.get('value', {}).get('fields', {})
    
    old_name = old_fields.get('name', {}).get('stringValue')
    new_name = new_fields.get('name', {}).get('stringValue')

    if old_name != new_name:
        print("🚨 NAME CHANGED")
    else:
        print("ℹ️ No name change detected.")
