I'll help you analyze and improve the file handling for Azure OpenAI models, particularly focusing on o1 series models. Let's look at how to optimize the file content processing and formatting.

First, let's analyze the current flow:

1. Files are uploaded and validated in `handle_chat()`
2. File contents are processed through `process_uploaded_files()`
3. The contents are combined with the message in a simple concatenation

Here's how we can improve this to better handle file contents for o1 series models:

1. First, let's create a new helper function to format file contents properly:

```python
def format_file_contents_for_o1(files_data: List[Dict[str, str]], message: str = "") -> str:
    """
    Format file contents in a way that's optimized for o1 series models.
    
    Args:
        files_data: List of dictionaries containing file info and content
        message: Optional user message to include
    
    Returns:
        Formatted string combining message and file contents
    """
    formatted_content = []
    
    # Add user message if present
    if message.strip():
        formatted_content.append(f"User Message: {message.strip()}\n")
    
    # Add file contents with clear section markers
    if files_data:
        formatted_content.append("\n=== Uploaded Files Content ===\n")
        
        for idx, file_data in enumerate(files_data, 1):
            filename = file_data.get('filename', f'File {idx}')
            content = file_data.get('content', '').strip()
            mime_type = file_data.get('mime_type', 'text/plain')
            
            # Add file metadata header
            formatted_content.append(f"\n--- File {idx}: {filename} ({mime_type}) ---\n")
            
            # Format content based on type
            if mime_type.startswith('text/'):
                # For text files, add line numbers and clear section markers
                lines = content.split('\n')
                formatted_lines = [f"{i+1:4d} | {line}" for i, line in enumerate(lines)]
                formatted_content.append('\n'.join(formatted_lines))
            else:
                # For other types, just add the content with a type indicator
                formatted_content.append(f"[Content Type: {mime_type}]\n{content}")
                
            formatted_content.append("\n" + "-" * 50 + "\n")
    
    # Add a clear end marker
    formatted_content.append("\n=== End of Files ===\n")
    
    return "\n".join(formatted_content)
```

2. Now, let's modify the `process_uploaded_files()` function to better handle text extraction and tokenization:

```python
def process_uploaded_files(files: List[Any]) -> Tuple[List[Dict], List[Dict], int, List[Dict]]:
    """
    Process uploaded files with improved text extraction and tokenization.
    
    Returns:
        Tuple containing:
        - List of included files
        - List of excluded files
        - Total tokens
        - Processed file contents
    """
    included_files = []
    excluded_files = []
    total_tokens = 0
    file_contents = []
    
    for file in files:
        if not file or not file.filename:
            continue
            
        try:
            # Get file content and mime type
            content = file.read()
            file.seek(0)
            
            # Detect mime type
            try:
                import magic
                mime_type = magic.from_buffer(content, mime=True)
            except ImportError:
                mime_type = file.content_type or 'application/octet-stream'
            
            # Process based on mime type
            if mime_type.startswith('text/'):
                # For text files, decode content
                try:
                    text_content = content.decode('utf-8')
                except UnicodeDecodeError:
                    text_content = content.decode('latin-1')
            else:
                # For non-text files, attempt extraction if supported
                text_content = extract_text_from_file(file, mime_type)
            
            # Tokenize content
            try:
                encoding = tiktoken.encoding_for_model('gpt-4')
                tokens = encoding.encode(text_content)
                token_count = len(tokens)
            except Exception as e:
                logger.warning(f"Tokenization failed: {e}")
                token_count = len(text_content.split())
            
            # Add to included files if within limits
            if token_count <= MAX_INPUT_TOKENS:
                included_files.append({
                    'filename': file.filename,
                    'size': len(content),
                    'mime_type': mime_type,
                    'token_count': token_count
                })
                
                file_contents.append({
                    'filename': file.filename,
                    'content': text_content,
                    'mime_type': mime_type,
                    'token_count': token_count
                })
                
                total_tokens += token_count
            else:
                excluded_files.append({
                    'filename': file.filename,
                    'reason': f'Token count ({token_count}) exceeds limit'
                })
                
        except Exception as e:
            excluded_files.append({
                'filename': file.filename,
                'reason': str(e)
            })
            
    return included_files, excluded_files, total_tokens, file_contents
```

3. Finally, let's modify the relevant part of the `handle_chat()` function to use these improvements:

```python
# In handle_chat()
# Replace the existing file handling code with:

if files_list and any(f.filename for f in files_list):
    included_files, excluded_files, total_tokens, file_contents = process_uploaded_files(files_list)
    
    if excluded_files:
        return jsonify({
            "error": "Some files could not be processed",
            "details": excluded_files,
        }), 400
        
    # Format content specifically for o1 series models if needed
    if model_obj.model_type.lower() in ['o1', 'o1-mini', 'o1-preview']:
        combined_message = format_file_contents_for_o1(file_contents, message)
    else:
        # Use simpler format for other models
        combined_message = message + "\n\n" + "\n\n".join(
            f"[{fc['filename']}]\n{fc['content']}" 
            for fc in file_contents
        )
```

These changes provide several improvements:

1. Better content structuring with clear section markers and metadata
2. Improved text extraction and mime type detection
3. Proper tokenization using the model's encoding
4. Special formatting for o1 series models
5. Better error handling and validation
6. Clear separation between files with line numbers and section markers
7. Proper handling of different content types

The formatted output will be more digestible for o1 series models because:

1. It has clear structure and section markers
2. File contents are properly separated and labeled
3. Line numbers help with referencing specific parts
4. Metadata is clearly marked and separated from content
5. The format is consistent and predictable

This formatting helps the model better understand the structure of the input and makes it easier to reference specific parts of files in its responses.

Remember to also update your token limits and validation based on the specific o1 model variant you're using, as they have different token limits:

- o1: 100,000 tokens
- o1-mini: 50,000 tokens
- o1-preview: 32,768 tokens