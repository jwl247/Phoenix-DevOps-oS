package com.attempt1.lifefirstapp

// Import the necessary classes from the Gemini SDK and your app's BuildConfig
import com.google.ai.client.generativeai.GenerativeModel
import com.attempt1.lifefirstapp.BuildConfig // This gives access to your API key

/**
 * A Singleton object to provide a central, app-wide instance of the GenerativeModel.
 * This is the recommended approach to avoid creating a new client for every API call.
 */
object FamilyAiClient {

    // This is the core object that will interact with the Gemini API.
    val model: GenerativeModel by lazy {
        GenerativeModel(
            // Specify the model you want to use. "gemini-1.5-flash-latest" is a fast and capable choice.
            modelName = "gemini-1.5-flash-latest",

            // This safely retrieves the API key you defined in your build.gradle file.
            // It will only work if you have successfully synced your Gradle files after adding it.
            apiKey = BuildConfig.GEMINI_API_KEY
        )
    }
}