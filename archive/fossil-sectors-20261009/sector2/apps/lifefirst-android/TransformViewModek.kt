package com.attempt1.lifefirstapp.ui.transform // Make sure this package is correct

import android.os.Bundle
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.TextView
import androidx.compose.ui.semantics.text
import androidx.fragment.app.Fragment
import androidx.fragment.app.viewModels // IMPORTANT: For by viewModels()
import androidx.lifecycle.observe
import com.attempt1.lifefirstapp.databinding.FragmentTransformBinding
import dagger.hilt.android.AndroidEntryPoint // IMPORTANT: For Hilt

@AndroidEntryPoint // Tells Hilt this Fragment can receive injected dependencies
class TransformFragment : Fragment() {

    private var _binding: FragmentTransformBinding? = null
    // This property is only valid between onCreateView and onDestroyView.
    private val binding get() = _binding!!

    // Hilt-aware way to get the ViewModel
    // This replaces: ViewModelProvider(this).get(TransformViewModel::class.java)
    private val transformViewModel: TransformViewModel by viewModels()

    override fun onCreateView(
        inflater: LayoutInflater,
        container: ViewGroup?,
        savedInstanceState: Bundle?
    ): View {
        _binding = FragmentTransformBinding.inflate(inflater, container, false)
        val root: View = binding.root

        val textView: TextView = binding.textTransform // Assuming you have a TextView with id text_transform
        transformViewModel.text.observe(viewLifecycleOwner) {
            textView.text = it
        }
        return root
    }

    override fun onDestroyView() {
        super.onDestroyView()
        _binding = null // Important to avoid memory leaks with View Binding
    }
}
