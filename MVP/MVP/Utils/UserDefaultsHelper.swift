import Foundation

/// A utility class for working with UserDefaults
class UserDefaultsHelper {
    
    /// Prints all keys and values stored in UserDefaults
    static func printAllUserDefaults() {
        print("\n📱 USER DEFAULTS CONTENTS:")
        print("==========================")
        
        let defaults = UserDefaults.standard
        let dictionary = defaults.dictionaryRepresentation()
        
        if dictionary.isEmpty {
            print("UserDefaults is empty")
        } else {
            for (key, value) in dictionary {
                print("🔑 Key: \(key)")
                print("   Value: \(value)")
                print("   Type: \(type(of: value))")
                print("--------------------------")
            }
        }
        
        print("==========================\n")
    }
    
    /// Prints a specific key and its value from UserDefaults
    /// - Parameter key: The key to look up
    static func printValue(forKey key: String) {
        let defaults = UserDefaults.standard
        
        if defaults.object(forKey: key) != nil {
            let value = defaults.object(forKey: key)!
            print("\n🔍 USER DEFAULTS VALUE FOR KEY: \(key)")
            print("==========================")
            print("Value: \(value)")
            print("Type: \(type(of: value))")
            print("==========================\n")
        } else {
            print("\n❌ No value found for key: \(key)")
            print("==========================\n")
        }
    }
    
    /// Checks if a specific key exists in UserDefaults
    /// - Parameter key: The key to check
    /// - Returns: True if the key exists, false otherwise
    static func keyExists(_ key: String) -> Bool {
        return UserDefaults.standard.object(forKey: key) != nil
    }
    
    /// Gets all keys in UserDefaults
    /// - Returns: An array of all keys
    static func getAllKeys() -> [String] {
        return Array(UserDefaults.standard.dictionaryRepresentation().keys)
    }
    
    /// Removes all entries from UserDefaults (use with caution!)
    static func clearAllUserDefaults() {
        let defaults = UserDefaults.standard
        let dictionary = defaults.dictionaryRepresentation()
        
        for key in dictionary.keys {
            defaults.removeObject(forKey: key)
        }
        
        print("🧹 Cleared all UserDefaults entries")
    }
} 