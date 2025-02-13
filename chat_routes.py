@chat_routes.route("/send", methods=["POST"])
@login_required
def handle_chat():
    # ... existing validation code ...
    
    try:
        # Get model info
        model_obj = Chat.get_model(chat_id)
        if not model_obj:
            return jsonify({"error": "No model configured"}), 400
            
        # Set token limits based on model type
        model_type = model_obj.model_type.lower()
        token_limits = {
            'o1': 100000,
            'o1-mini': 50000,
            'o1-preview': 32768
        }
        max_tokens = token_limits.get(model_type, 8192)
        
        # Process message and files
        message = request.form.get("message", "").strip()
        files = request.files.getlist("files[]")
        
        # Special handling for o1 series models
        if model_type in token_limits:
            processed_files = []
            total_tokens = len(tiktoken.encoding_for_model('gpt-4').encode(message))
            
            for file in files:
                if not file or not file.filename:
                    continue
                    
                file_data = process_file_for_o1(file, max_tokens // len(files))
                total_tokens += file_data['token_count']
                
                if total_tokens > max_tokens:
                    return jsonify({
                        "error": f"Combined content exceeds {max_tokens} token limit",
                        "details": "Try uploading fewer or smaller files"
                    }), 400
                    
                processed_files.append(file_data)
            
            # Format content for o1
            formatted_content = format_content_for_o1(message, processed_files, max_tokens)
        else:
            # Handle non-o1 models
            formatted_content = format_standard_content(message, files)
        
        # Add to conversation
        conversation_manager.add_message(
            chat_id=chat_id,
            role="user",
            content=bleach.clean(formatted_content),
            model_max_tokens=max_tokens
        )
        
        # Continue with API call...