var body: some Scene {
    WindowGroup {
        ContentView()
            .environmentObject(appState)
            .environmentObject(cameraManager)
            .environmentObject(visionManager)
            .environmentObject(voiceManager)
            .environmentObject(resourceCoordinator)
            .environmentObject(notificationManager)
            .onAppear {
                // Configure resource coordinator with required managers
                resourceCoordinator.configure(
                    cameraManager: cameraManager,
                    visionManager: visionManager,
                    voiceManager: voiceManager
                )
                
                // Check if notification is authorized before clearing
                if notificationManager.isAuthorized {
                    notificationManager.clearBadge()
                    print("📱 MVPApp appeared - Badge cleared")
                } else {
                    print("📱 MVPApp appeared - Notifications not authorized")
                }
                
                // Print app environment debug info
                printEnvironmentInfo()
            }
    }
} 