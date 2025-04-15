# Physical Therapy App Notification System

This document outlines the notification system implementation for the Physical Therapy app, which includes both iOS (Swift) and backend (Python) components.

## Components

### iOS (Swift) Components

1. **NotificationManager.swift**
   - Handles local and remote notifications
   - Manages notification permissions
   - Schedules local notifications
   - Integrates with Firebase Cloud Messaging (FCM)

2. **NotificationSettingsView.swift**
   - User interface for configuring notification preferences
   - Allows users to enable/disable notifications
   - Supports setting notification frequency (daily/weekly)
   - Provides time and day selection for notifications

3. **AppDelegate Updates**
   - Handles FCM token registration
   - Manages notification permissions
   - Processes incoming remote notifications

### Backend (Python) Components

1. **Cloud Functions**
   - `schedule_notification`: Schedules notifications for future delivery
   - `update_fcm_token`: Updates user's FCM token in Firestore
   - `send_exercise_notification`: Sends immediate exercise reminders

2. **Firestore Collections**
   - `notifications`: Stores notification metadata and status
   - `users`: Contains user information including FCM tokens
   - `exercises`: Stores exercise details for personalized notifications

## Features

- **Local Notifications**
  - Daily exercise reminders
  - Weekly progress updates
  - Customizable notification times
  - Exercise-specific reminders

- **Remote Notifications**
  - Firebase Cloud Messaging integration
  - Personalized exercise reminders
  - High-priority notifications for important updates
  - Background notification support

- **User Preferences**
  - Enable/disable notifications
  - Set notification frequency
  - Choose specific days for weekly notifications
  - Customize notification times

## Implementation Details

### iOS Implementation

1. **Notification Permissions**
   - Request user authorization for notifications
   - Handle permission changes
   - Support for both foreground and background notifications

2. **Firebase Integration**
   - FCM token management
   - Remote notification handling
   - Background message processing

3. **User Interface**
   - Intuitive notification settings
   - Real-time preference updates
   - Visual feedback for notification status

### Backend Implementation

1. **Cloud Functions**
   - HTTP endpoints for notification management
   - CORS support for cross-origin requests
   - Error handling and logging
   - Firestore integration for data persistence

2. **Notification Scheduling**
   - Support for immediate and scheduled notifications
   - Exercise-specific content generation
   - Status tracking and updates

3. **Data Management**
   - Firestore document structure
   - Timestamp handling
   - Data serialization

## Setup Instructions

1. **iOS Setup**
   - Add required capabilities in Xcode
   - Configure Info.plist with notification permissions
   - Initialize Firebase in AppDelegate
   - Set up NotificationManager in the app

2. **Backend Setup**
   - Deploy cloud functions to Firebase
   - Configure Firebase Admin SDK
   - Set up Firestore collections
   - Test notification delivery

## Usage

1. **Scheduling Notifications**
   ```swift
   // Schedule a daily notification
   notificationManager.scheduleDailyNotification(at: Date())
   
   // Schedule a weekly notification
   notificationManager.scheduleWeeklyNotification(on: [.monday, .wednesday, .friday], at: Date())
   ```

2. **Updating Preferences**
   ```swift
   // Update notification preferences
   notificationManager.updatePreferences(
       isEnabled: true,
       frequency: .daily,
       time: Date()
   )
   ```

3. **Backend API Calls**
   ```python
   # Schedule a notification
   POST /schedule_notification
   {
       "user_id": "user123",
       "notification_type": "exercise_reminder",
       "scheduled_time": "2024-03-20T10:00:00Z",
       "exercise_id": "exercise123"
   }
   
   # Update FCM token
   POST /update_fcm_token
   {
       "user_id": "user123",
       "fcm_token": "fcm_token_here"
   }
   ```

## Security Considerations

1. **Data Protection**
   - Secure storage of FCM tokens
   - User authentication for API endpoints
   - Data validation and sanitization

2. **Privacy**
   - User consent for notifications
   - Clear notification purposes
   - Option to opt-out

## Troubleshooting

1. **Common Issues**
   - Notification permissions not granted
   - FCM token not registered
   - Background notification delivery
   - Time zone handling

2. **Debugging**
   - Check notification settings
   - Verify FCM token registration
   - Monitor cloud function logs
   - Test notification delivery

## Future Enhancements

1. **Planned Features**
   - AI-generated notification content
   - Advanced scheduling options
   - Notification analytics
   - A/B testing support

2. **Improvements**
   - Enhanced error handling
   - Better time zone support
   - More customization options
   - Performance optimizations 