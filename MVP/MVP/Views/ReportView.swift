import SwiftUI

struct ReportView: View {
    @Environment(\.presentationMode) private var presentationMode
    @EnvironmentObject private var appState: AppState
    @EnvironmentObject private var voiceManager: VoiceManager
    
    @State private var showingCongrats = true
    @State private var reportData: ExerciseReport?
    @State private var isLoading = true
    
    // Exercise data
    let exercise: Exercise
    let duration: TimeInterval
    let date: Date
    
    init(exercise: Exercise, duration: TimeInterval, date: Date = Date()) {
        self.exercise = exercise
        self.duration = duration
        self.date = date
    }
    
    var body: some View {
        ZStack {
            Color.white.edgesIgnoringSafeArea(.all)
            
            if isLoading {
                ProgressView("Generating your report...")
                    .padding()
            } else {
                ScrollView {
                    VStack(alignment: .leading, spacing: 20) {
                        HeaderSection(exerciseName: exercise.name, date: date)
                        
                        if let report = reportData {
                            FeedbackSection(title: "General Feeling",
                                          content: report.generalFeeling)
                            
                            FeedbackSection(title: "Performance Quality",
                                          content: report.performanceQuality)
                            
                            FeedbackSection(title: "Pain Report",
                                          content: report.painReport)
                            
                            ExerciseStats(duration: duration,
                                        exercise: exercise,
                                        completed: report.completed,
                                        setsCompleted: report.setsCompleted,
                                        repsCompleted: report.repsCompleted)
                            
                            ProgressBoardSection(dayStreak: report.dayStreak)
                            
                            MotivationalMessageSection(message: report.motivationalMessage)
                        } else {
                            // Fallback if no report data is available
                            Text("No detailed report available for this session.")
                                .italic()
                                .foregroundColor(.secondary)
                                .padding()
                            
                            ExerciseStats(duration: duration,
                                        exercise: exercise,
                                        completed: true,
                                        setsCompleted: 3,
                                        repsCompleted: 10)
                        }
                        
                        // Done button
                        Button(action: {
                            presentationMode.wrappedValue.dismiss()
                        }) {
                            Text("Done")
                                .fontWeight(.semibold)
                                .frame(maxWidth: .infinity)
                                .padding()
                                .background(Color.blue)
                                .foregroundColor(.white)
                                .cornerRadius(10)
                        }
                        .padding(.top, 30)
                    }
                    .padding()
                }
            }
            
            if showingCongrats {
                CongratulationsOverlay {
                    withAnimation {
                        showingCongrats = false
                    }
                }
            }
        }
        .onAppear {
            // Generate report from cloud function
            generateExerciseReport()
        }
    }
    
    private func generateExerciseReport() {
        guard let userId = appState.userId else {
            // If we don't have user ID, use placeholder data
            reportData = ExerciseReport.placeholder
            isLoading = false
            return
        }
        
        // Get the exerciseId - no need for optional binding since we're using nil coalescing
        let exerciseId = exercise.firestoreId ?? exercise.id.uuidString
        
        // Get conversation history for context
        let conversationHistory = voiceManager.getConversationHistory()
        
        // Call the cloud function
        generatePTReport(patientId: userId, exerciseId: exerciseId, conversationHistory: conversationHistory) { result in
            DispatchQueue.main.async {
                self.isLoading = false
                
                switch result {
                case .success(let report):
                    self.reportData = report
                    // Save to app state for reference
                    self.appState.setExerciseReport(report)
                    
                case .failure(let error):
                    print("Error generating report: \(error.localizedDescription)")
                    // Use placeholder data
                    self.reportData = ExerciseReport.placeholder
                }
            }
        }
    }

    
    private func generatePTReport(patientId: String, exerciseId: String,
                                conversationHistory: [[String: Any]],
                                completion: @escaping (Result<ExerciseReport, Error>) -> Void) {
        // Create URL for API call
        guard let url = URL(string: "https://us-central1-duoligo-pt-app.cloudfunctions.net/generate_pt_report") else {
            completion(.failure(NSError(domain: "ReportView", code: 1, userInfo: [NSLocalizedDescriptionKey: "Invalid URL"])))
            return
        }
        
        // Create request
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        
        // Create request body
        let requestBody: [String: Any] = [
            "patient_id": patientId,
            "exercise_id": exerciseId,
            "conversation_history": conversationHistory
        ]
        
        // Serialize request body
        do {
            request.httpBody = try JSONSerialization.data(withJSONObject: requestBody)
        } catch {
            completion(.failure(error))
            return
        }
        
        // Make API call
        URLSession.shared.dataTask(with: request) { data, response, error in
            if let error = error {
                completion(.failure(error))
                return
            }
            
            guard let data = data else {
                completion(.failure(NSError(domain: "ReportView", code: 2, userInfo: [NSLocalizedDescriptionKey: "No data received"])))
                return
            }
            
            do {
                // Parse response
                let json = try JSONSerialization.jsonObject(with: data) as? [String: Any]
                
                // Check status
                guard let status = json?["status"] as? String,
                      status == "success",
                      let reportData = json?["report"] as? [String: Any] else {
                    
                    if let errorMessage = json?["error"] as? String {
                        completion(.failure(NSError(domain: "ReportView", code: 3, userInfo: [NSLocalizedDescriptionKey: errorMessage])))
                    } else {
                        completion(.failure(NSError(domain: "ReportView", code: 3, userInfo: [NSLocalizedDescriptionKey: "Invalid response"])))
                    }
                    return
                }
                
                // Create ExerciseReport from report data
                let report = ExerciseReport(
                    id: json?["report_id"] as? String ?? UUID().uuidString,
                    generalFeeling: reportData["general_feeling"] as? String ?? "No data available",
                    performanceQuality: reportData["performance_quality"] as? String ?? "No data available",
                    painReport: reportData["pain_report"] as? String ?? "No data available",
                    completed: reportData["completed"] as? Bool ?? true,
                    setsCompleted: reportData["sets_completed"] as? Int ?? 3,
                    repsCompleted: reportData["reps_completed"] as? Int ?? 10,
                    dayStreak: reportData["day_streak"] as? Int ?? 1,
                    motivationalMessage: reportData["motivational_message"] as? String ??
                        "Great job completing your exercise! Keep it up to continue your progress.",
                    date: Date()
                )
                
                completion(.success(report))
                
            } catch {
                completion(.failure(error))
            }
        }.resume()
    }
}

// MARK: - Supporting Views
struct HeaderSection: View {
    let exerciseName: String
    let date: Date
    
    var body: some View {
        VStack(alignment: .leading) {
            Text("\(exerciseName) Report")
                .font(.title)
                .bold()
            Text(date.formatted())
                .foregroundColor(.secondary)
        }
    }
}

struct FeedbackSection: View {
    let title: String
    let content: String
    
    var body: some View {
        VStack(alignment: .leading, spacing: 5) {
            Text(title)
                .font(.headline)
            Text(content)
                .padding(.vertical, 5)
            Divider()
        }
    }
}

struct ExerciseStats: View {
    let duration: TimeInterval
    let exercise: Exercise
    let completed: Bool
    let setsCompleted: Int
    let repsCompleted: Int
    
    var formattedDuration: String {
        let minutes = Int(duration) / 60
        let seconds = Int(duration) % 60
        return "\(minutes)m \(seconds)s"
    }
    
    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Exercise Statistics")
                .font(.headline)
            
            HStack(spacing: 20) {
                StatItem(title: "Duration", value: formattedDuration)
                StatItem(title: "Sets", value: "\(setsCompleted)")
                StatItem(title: "Reps", value: "\(repsCompleted)")
            }
            
            HStack {
                Text("Completion:")
                Text(completed ? "Completed" : "Partial")
                    .foregroundColor(completed ? .green : .orange)
                    .fontWeight(.semibold)
            }
            .padding(.top, 4)
            
            Divider()
        }
    }
}

struct StatItem: View {
    let title: String
    let value: String
    
    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(title)
                .font(.caption)
                .foregroundColor(.secondary)
            Text(value)
                .font(.system(.body, design: .rounded))
                .fontWeight(.medium)
        }
    }
}

struct ProgressBoardSection: View {
    let dayStreak: Int
    
    var body: some View {
        VStack(alignment: .leading, spacing: 15) {
            Text("Progress Board")
                .font(.headline)
            
            HStack {
                VStack {
                    Text("\(dayStreak)")
                        .font(.largeTitle)
                        .fontWeight(.bold)
                        .foregroundColor(.blue)
                    Text("Day Streak")
                        .foregroundColor(.secondary)
                }
                .frame(maxWidth: .infinity)
                
                VStack {
                    Image(systemName: "flame.fill")
                        .resizable()
                        .aspectRatio(contentMode: .fit)
                        .frame(width: 40, height: 40)
                        .foregroundColor(.orange)
                    Text("Consistency")
                        .foregroundColor(.secondary)
                }
                .frame(maxWidth: .infinity)
                
                VStack {
                    Text("🏔️")
                        .font(.largeTitle)
                    Text("Goal Tracking")
                        .foregroundColor(.secondary)
                }
                .frame(maxWidth: .infinity)
            }
            Divider()
        }
    }
}

struct MotivationalMessageSection: View {
    let message: String
    
    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("Today's Motivation")
                .font(.headline)
            Text(message)
                .foregroundColor(.secondary)
                .italic()
            Divider()
        }
    }
}

struct CongratulationsOverlay: View {
    let onComplete: () -> Void
    
    var body: some View {
        ZStack {
            Color.black.opacity(0.8)
                .edgesIgnoringSafeArea(.all)
            
            VStack {
                // You can implement a simple animation here
                Image(systemName: "checkmark.circle.fill")
                    .resizable()
                    .scaledToFit()
                    .frame(width: 100, height: 100)
                    .foregroundColor(.green)
                    .scaleEffect(1.5)
                    .opacity(0.9)
                
                Text("Fantastic Work!")
                    .font(.title)
                    .foregroundColor(.white)
                    .padding()
                
                Text("Your exercise is complete!")
                    .font(.title3)
                    .foregroundColor(.white.opacity(0.8))
            }
        }
        .onAppear {
            DispatchQueue.main.asyncAfter(deadline: .now() + 2.5) {
                onComplete()
            }
        }
    }
}
