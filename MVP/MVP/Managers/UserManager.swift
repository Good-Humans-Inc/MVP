import Foundation
import Combine

class UserManager: ObservableObject {
    static let shared = UserManager()
    
    // Published properties for user data
    @Published var userId: String? = nil {
        didSet {
            // Save to UserDefaults when changed
            if let id = userId {
                UserDefaults.standard.set(id, forKey: "userId")
                print("✅ UserManager: Saved userId to UserDefaults: \(id)")
            } else {
                UserDefaults.standard.removeObject(forKey: "userId")
                print("✅ UserManager: Removed userId from UserDefaults")
            }
            
            // If we have a user ID, ensure timezone is updated
            if userId != nil {
                NotificationCenter.default.post(name: NSNotification.Name("UserIDAvailable"), object: nil)
            }
        }
    }
    @Published var userName: String = "" {
        didSet {
            UserDefaults.standard.set(userName, forKey: "userName")
            print("✅ UserManager: Saved userName to UserDefaults: \(userName)")
        }
    }
    @Published var userAge: Int = 0 {
        didSet {
            UserDefaults.standard.set(userAge, forKey: "userAge")
            print("✅ UserManager: Saved userAge to UserDefaults: \(userAge)")
        }
    }
    @Published var exerciseRoutine: String = "" {
        didSet {
            UserDefaults.standard.set(exerciseRoutine, forKey: "userExerciseRoutine")
            print("✅ UserManager: Saved exerciseRoutine to UserDefaults: \(exerciseRoutine)")
        }
    }
    @Published var userGoals: String = "" {
        didSet {
            UserDefaults.standard.set(userGoals, forKey: "userGoals")
            print("✅ UserManager: Saved userGoals to UserDefaults: \(userGoals)")
        }
    }
    @Published var painDescription: String = "" {
        didSet {
            UserDefaults.standard.set(painDescription, forKey: "userPainDescription")
            print("✅ UserManager: Saved painDescription to UserDefaults: \(painDescription)")
        }
    }
    @Published var notificationTime: String = "" {
        didSet {
            UserDefaults.standard.set(notificationTime, forKey: "notificationTime")
            print("✅ UserManager: Saved notificationTime to UserDefaults: \(notificationTime)")
        }
    }
    @Published var isDataLoaded: Bool = false
    
    private init() {
        // Load user ID from UserDefaults
        if let savedUserId = UserDefaults.standard.string(forKey: "userId") {
            self.userId = savedUserId
            print("✅ UserManager init: Loaded userId from UserDefaults: \(savedUserId)")
        } else {
            print("⚠️ UserManager init: No userId found in UserDefaults")
        }
        
        // Load user data when initialized
        loadUserData()
        
        // Schedule timezone check for after user data is likely available
        DispatchQueue.main.asyncAfter(deadline: .now() + 1.0) { [weak self] in
            self?.checkAndUpdateTimezoneIfNeeded()
        }
    }
    
    func checkAndUpdateTimezoneIfNeeded() {
        // Get current timezone offset
        let currentOffset = TimeZone.current.secondsFromGMT() / 3600
        let currentOffsetString = String(currentOffset)
        
        // Get last known timezone offset
        let timezoneCacheKey = "lastKnownTimezone"
        let defaults = UserDefaults.standard
        let lastKnownOffset = defaults.string(forKey: timezoneCacheKey)
        
        print("📱 UserManager: Current timezone offset: \(currentOffsetString), Last known: \(lastKnownOffset ?? "none")")
        
        // Check if timezone has changed
        if lastKnownOffset != currentOffsetString {
            print("🕒 UserManager: Timezone has changed from \(lastKnownOffset ?? "unknown") to \(currentOffsetString)")
            
            // Update server when user ID is available
            if let userId = self.userId {
                print("🕒 UserManager: Found user ID for timezone update: \(userId)")
                updateTimezoneOnServer(userId: userId, timezone: currentOffsetString)
                
                // Cache the new timezone
                defaults.set(currentOffsetString, forKey: timezoneCacheKey)
            } else {
                print("❌ UserManager: No user ID available for timezone update")
            }
        }
    }

    func updateTimezoneOnServer(userId: String, timezone: String) {
        guard let url = URL(string: "https://us-central1-pepmvp.cloudfunctions.net/update_timezone") else {
            print("❌ UserManager: Invalid URL for timezone update")
            return
        }
        
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        
        let body: [String: String] = [
            "user_id": userId,
            "timezone": timezone
        ]
        
        print("🕒 UserManager: Updating timezone on server: \(body)")
        
        guard let jsonData = try? JSONSerialization.data(withJSONObject: body) else {
            print("❌ UserManager: Failed to serialize timezone update request")
            return
        }
        
        request.httpBody = jsonData
        
        URLSession.shared.dataTask(with: request) { data, response, error in
            if let error = error {
                print("❌ UserManager: Error updating timezone: \(error.localizedDescription)")
                return
            }
            
            if let httpResponse = response as? HTTPURLResponse {
                print("🕒 UserManager: Timezone update response status: \(httpResponse.statusCode)")
                
                if let data = data, let responseString = String(data: data, encoding: .utf8) {
                    print("🕒 UserManager: Timezone update response: \(responseString)")
                }
                
                if httpResponse.statusCode == 200 {
                    print("✅ UserManager: Timezone updated successfully")
                } else {
                    print("❌ UserManager: Timezone update failed with status: \(httpResponse.statusCode)")
                }
            }
        }.resume()
    }
    
    func loadUserData() {
        print("🔄 UserManager loadUserData: Loading user data")
        guard let userId = self.userId else {
            print("❌ UserManager loadUserData: No user ID found in UserManager")
            return
        }
        
        // Call the cloud function to get user data
        guard let url = URL(string: "https://us-central1-pepmvp.cloudfunctions.net/get_user_data") else {
            print("❌ UserManager loadUserData: Invalid get user data URL")
            return
        }
        
        var request = URLRequest(url: url)
        request.httpMethod = "GET"
        request.addValue("application/json", forHTTPHeaderField: "Content-Type")
        
        // Add user ID as query parameter
        let urlWithParams = url.appendingQueryParameters(["user_id": userId])
        request.url = urlWithParams
        
        // Make API call
        let task = URLSession.shared.dataTask(with: request) { [weak self] data, response, error in
            guard let self = self else { return }
            
            if let error = error {
                print("❌ UserManager loadUserData: Get user data error: \(error.localizedDescription)")
                return
            }
            
            guard let data = data else {
                print("❌ UserManager loadUserData: No data received from get user data API")
                return
            }
            
            do {
                // Parse response
                if let json = try JSONSerialization.jsonObject(with: data) as? [String: Any],
                   let userData = json["user_data"] as? [String: Any] {
                    
                    // Update on main thread
                    DispatchQueue.main.async {
                        // Update properties - didSet observers will handle saving to UserDefaults
                        self.userName = userData["user_name"] as? String ?? ""
                        self.userAge = userData["user_age"] as? Int ?? -1
                        self.exerciseRoutine = userData["exercise_routine"] as? String ?? ""
                        self.userGoals = userData["user_goals"] as? String ?? ""
                        self.painDescription = userData["pain_description"] as? String ?? ""
                        self.notificationTime = userData["notification_time"] as? String ?? ""
                        self.isDataLoaded = true
                        
                        print("✅ UserManager loadUserData: User data loaded successfully")
                    }
                } else {
                    print("❌ UserManager loadUserData: Invalid user data response format")
                }
            } catch {
                print("❌ UserManager loadUserData: Failed to parse user data response: \(error)")
            }
        }
        
        task.resume()
    }
}

// Helper extension for URL query parameters
extension URL {
    func appendingQueryParameters(_ parameters: [String: String]) -> URL {
        var components = URLComponents(url: self, resolvingAgainstBaseURL: true)!
        components.queryItems = parameters.map { URLQueryItem(name: $0.key, value: $0.value) }
        return components.url!
    }
} 

