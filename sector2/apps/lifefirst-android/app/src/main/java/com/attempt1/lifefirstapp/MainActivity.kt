package com.attempt1.lifefirstapp

import android.os.Bundle
import android.util.Log
import android.view.Menu
import android.view.MenuItem
import androidx.appcompat.app.AppCompatActivity
import androidx.lifecycle.lifecycleScope // NEW: Import for coroutines
import androidx.navigation.Navigation
import androidx.navigation.fragment.NavHostFragment
import androidx.navigation.ui.AppBarConfiguration
import androidx.navigation.ui.NavigationUI
import com.attempt1.lifefirstapp.databinding.ActivityMainBinding
// REMOVED: No longer importing from a 'network' sub-package
import com.google.android.material.snackbar.Snackbar
import com.google.firebase.analytics.FirebaseAnalytics
import com.google.firebase.auth.FirebaseAuth
import com.google.firebase.firestore.FirebaseFirestore
import dagger.hilt.android.AndroidEntryPoint
import kotlinx.coroutines.launch // NEW: Import for launching a coroutine
import javax.inject.Inject

@AndroidEntryPoint
class MainActivity : AppCompatActivity() {

    private lateinit var binding: ActivityMainBinding
    private lateinit var appBarConfiguration: AppBarConfiguration

    @Inject
    lateinit var auth: FirebaseAuth
    @Inject
    lateinit var firestore: FirebaseFirestore
    @Inject
    lateinit var firebaseAnalytics: FirebaseAnalytics

    // REMOVED: The old instance variable for the AI client is no longer needed.
    // private lateinit var aiClient: FamilyAIClient

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityMainBinding.inflate(layoutInflater)
        setContentView(binding.root)

        setSupportActionBar(binding.appBarMain.toolbar)

        // ... (Your existing UI and Navigation code remains the same) ...
        binding.appBarMain.fab?.setOnClickListener { view ->
            Snackbar.make(view, "Replace with your own action", Snackbar.LENGTH_LONG)
                .setAction("Action", null).setAnchorView(R.id.fab).show()
        }
        val navHostFragment =
            supportFragmentManager.findFragmentById(R.id.nav_host_fragment_content_main) as NavHostFragment
        val navController = navHostFragment.navController
        binding.navView?.let {
            appBarConfiguration = AppBarConfiguration.Builder(
                R.id.nav_transform, R.id.nav_reflow, R.id.nav_slideshow, R.id.nav_settings
            ).setOpenableLayout(binding.drawerLayout).build()
            NavigationUI.setupActionBarWithNavController(this, navController, appBarConfiguration)
            NavigationUI.setupWithNavController(it, navController)
        }
        binding.appBarMain.contentMain.bottomNavView?.let {
            NavigationUI.setupWithNavController(it, navController)
        }
        // ... (End of unchanged code) ...


        // --- AI CHAT SETUP ---
        // REMOVED: The old initialization is gone.
        val contentMainBinding = binding.appBarMain.contentMain
        contentMainBinding.askAIButton?.setOnClickListener {
            val message = contentMainBinding.messageEditText!!.text.toString()
            if (message.isNotEmpty()) {
                // Call the new, corrected function
                sendMessageToAI(message)
            }
        }
    }

    // --- NEW: Modern Coroutine-based AI Call ---
    private fun sendMessageToAI(message: String) {
        val contentMainBinding = binding.appBarMain.contentMain
        contentMainBinding.aiResponseTextView!!.text = "Asking AI..."
        contentMainBinding.messageEditText!!.text.clear()

        // Launch a coroutine that is automatically managed by the Activity's lifecycle
        lifecycleScope.launch {
            try {
                // Access the singleton client directly and call the suspend function
                val response = FamilyAiClient.model.generateContent(message)

                // Update the UI with the successful response
                contentMainBinding.aiResponseTextView!!.text = response.text
                Log.d("AI_RESPONSE", "Success: ${response.text}")

            } catch (e: Exception) {
                // If anything goes wrong, catch the error and display it
                contentMainBinding.aiResponseTextView!!.text = "Error: ${e.localizedMessage}"
                Log.e("AI_RESPONSE", "Error: ", e)
            }
        }
    }

    // --- YOUR ORIGINAL MENU FUNCTIONS (Unchanged) ---
    override fun onCreateOptionsMenu(menu: Menu): Boolean { /* ... */ return true }
    override fun onOptionsItemSelected(item: MenuItem): Boolean { /* ... */ return super.onOptionsItemSelected(item) }
    override fun onSupportNavigateUp(): Boolean { /* ... */ return super.onSupportNavigateUp() }
}