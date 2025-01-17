from typing import List, Dict, Optional, Tuple, Any
import math
from datetime import datetime
from token_utils import (
    count_message_tokens, 
    count_conversation_tokens,
    truncate_content
)
from models.chat import Chat

class ContextManager:
    def __init__(self, model_max_tokens: int):
        self.model_max_tokens = model_max_tokens
        self.context_strategy = "full"  # Default strategy
        self.context_cache = {}
        self.monitor = ContextMonitor()
        
    def get_context(self, messages: List[Dict[str, str]]) -> List[Dict[str, str]]:
        """
        Get optimized context with caching and prioritization
        """
        # Try to get from cache
        cache_key = hash(tuple((m['role'], m['content']) for m in messages))
        if cache_key in self.context_cache:
            return self.context_cache[cache_key]
            
        # Prioritize messages
        prioritized = self.prioritize_messages(messages)
        
        # Apply strategy
        if self.context_strategy == "full":
            context = prioritized
        elif self.context_strategy == "compressed":
            context = self.compress_context(prioritized, self.model_max_tokens)
        else:  # summary
            context = self.summarize_context(prioritized)
        
        # Update cache
        self.context_cache[cache_key] = context
        
        return context
        
    def prioritize_messages(self, messages: List[Dict[str, str]]) -> List[Dict[str, str]]:
        def get_timestamp(msg):
            timestamp = msg.get("metadata", {}).get("timestamp", "")
            try:
                # Convert ISO format timestamp to timestamp number
                if isinstance(timestamp, str):
                    from datetime import datetime
                    return datetime.fromisoformat(timestamp).timestamp()
                return float(timestamp)
            except (ValueError, TypeError):
                return 0.0

        return sorted(
            messages,
            key=lambda msg: (
                -get_timestamp(msg),  # Sort by timestamp descending
                0 if msg["role"] == "user" else 1,  # User messages first
                -self.calculate_importance(msg["content"])  # Important messages first
            )
        )
        
    def update_strategy(self, response_quality: float) -> None:
        """
        Adjust context strategy based on response quality.
        
        Args:
            response_quality: Quality score between 0 and 1
        """
        if response_quality < 0.7:
            self.context_strategy = "full"  # Use full context
        elif response_quality < 0.9:
            self.context_strategy = "compressed"  # Use compressed context
        else:
            self.context_strategy = "summary"  # Use summarized context

    def compress_context(self, messages: List[Dict[str, str]], max_tokens: int) -> List[Dict[str, str]]:
        """Compress context to fit within token limit"""
        compressed = []
        current_tokens = 0
        
        for msg in messages:
            compressed_msg = {
                "role": msg["role"],
                "content": self.smart_truncate(msg["content"], max_tokens - current_tokens)
            }
            
            msg_tokens = count_message_tokens(compressed_msg)
            if current_tokens + msg_tokens > max_tokens:
                break
                
            compressed.append(compressed_msg)
            current_tokens += msg_tokens
            
        return compressed
        
    def summarize_context(self, messages: List[Dict[str, str]]) -> List[Dict[str, str]]:
        """
        Create a summary of the context based on the most important messages.
        """
        # Basic summarization - keep last 5 messages
        summary = []
        for msg in messages[-5:]:
            summary.append({
                "role": msg["role"],
                "content": self.smart_truncate(msg["content"], 100)  # Keep first 100 tokens
            })
        return summary

    def calculate_importance(self, content: str) -> float:
        """Calculate message importance score"""
        # Basic heuristic - could be enhanced
        return min(1.0, len(content) / 1000)
        
class ContextMonitor:
    def __init__(self):
        self.metrics = {
            "token_usage": [],
            "cache_hits": 0,
            "cache_misses": 0,
            "compression_ratio": 1.0,
            "response_quality": []
        }
        
    def track_token_usage(self, tokens: int):
        self.metrics["token_usage"].append(tokens)
        if len(self.metrics["token_usage"]) > 100:
            self.metrics["token_usage"].pop(0)
            
    def track_cache_hit(self):
        self.metrics["cache_hits"] += 1
        
    def track_cache_miss(self):
        self.metrics["cache_misses"] += 1
        
    def track_response_quality(self, quality: float):
        self.metrics["response_quality"].append(quality)
        if len(self.metrics["response_quality"]) > 100:
            self.metrics["response_quality"].pop(0)
            
    def optimize_compression(self):
        avg_quality = sum(self.metrics["response_quality"]) / len(self.metrics["response_quality"])
        if avg_quality < 0.7:
            self.metrics["compression_ratio"] *= 0.9  # More aggressive compression
        else:
            self.metrics["compression_ratio"] = min(1.0, self.metrics["compression_ratio"] * 1.1)

    def calculate_optimal_window_size(self, message_count: int) -> int:
        """Calculate optimal context window size"""
        base_window = self.model_max_tokens * 0.8
        message_factor = min(1.0, message_count / 50)
        return int(base_window * (1 - message_factor))

    def prioritize_messages(self, messages: List[Dict[str, str]]) -> List[Dict[str, str]]:
        """Prioritize messages based on importance"""
        return sorted(
            messages,
            key=lambda msg: (
                -msg.get("metadata", {}).get("timestamp", 0),
                0 if msg["role"] == "user" else 1,
                -self.calculate_message_importance(msg["content"])
            )
        )

    def compress_context(self, messages: List[Dict[str, str]], target_tokens: int) -> List[Dict[str, str]]:
        """Compress context with special handling for file content."""
        compressed = []
        current_tokens = 0
        
        for msg in messages:
            content = msg["content"]
            metadata = msg.get("metadata", {})
            
            # Special handling for file content
            if metadata.get("file_content"):
                content = self.compress_file_content(content, target_tokens - current_tokens)
            else:
                content = self.smart_truncate(content, target_tokens - current_tokens)
            
            compressed_msg = {
                "role": msg["role"],
                "content": content,
                "metadata": metadata
            }
            
            msg_tokens = count_message_tokens(compressed_msg)
            if current_tokens + msg_tokens > target_tokens:
                break
                
            compressed.append(compressed_msg)
            current_tokens += msg_tokens
            
        return compressed

    def compress_file_content(self, content: str, max_tokens: int) -> str:
        """Special compression for file content."""
        lines = content.splitlines()
        if len(lines) > 10:
            # For large files, keep first and last lines with summary
            summary = f"\n\n[File truncated. Original had {len(lines)} lines]"
            keep_lines = lines[:5] + lines[-5:]
            truncated = "\n".join(keep_lines) + summary
            return truncate_content(truncated, max_tokens)
        return truncate_content(content, max_tokens)

    def smart_truncate(self, content: str, max_tokens: int) -> str:
        """Smart truncation preserving important parts"""
        sentences = content.split('. ')
        important_sentences = [s for s in sentences if self.is_important(s)]
        
        truncated = []
        current_tokens = 0
        
        for sentence in important_sentences:
            sentence_tokens = count_message_tokens({"content": sentence})
            if current_tokens + sentence_tokens > max_tokens:
                break
            truncated.append(sentence)
            current_tokens += sentence_tokens
            
        return ". ".join(truncated) + ("..." if len(truncated) < len(important_sentences) else "")

    def is_important(self, sentence: str) -> bool:
        """Determine if a sentence is important"""
        # Basic heuristic - could be enhanced with NLP
        return any(keyword in sentence.lower() for keyword in ["important", "key", "critical", "summary"])

    def calculate_message_importance(self, content: str) -> float:
        """Calculate message importance score"""
        # Basic heuristic - could be enhanced
        return min(1.0, len(content) / 1000)

    def get_context(self, messages: List[Dict[str, str]], chat_id: str) -> List[Dict[str, str]]:
        """Get optimized context with caching and prioritization"""
        # Try to get from cache
        if chat_id in self.context_cache:
            self.monitor.track_cache_hit()
            return self.context_cache[chat_id]
            
        # Get from database
        messages = Chat.get_messages(chat_id=chat_id)
        
        # Prioritize messages
        prioritized = self.prioritize_messages(messages)
        
        # Compress context
        compressed = self.compress_context(prioritized)
        
        # Update cache
        self.context_manager.context_cache[id(messages)] = compressed
        self.context_manager.monitor.track_cache_miss()
        
        return compressed
        
    def prioritize_messages(self, messages: List[Dict[str, str]]) -> List[Dict[str, str]]:
        def get_timestamp(msg):
            timestamp = msg.get("metadata", {}).get("timestamp", "")
            try:
                # Convert ISO format timestamp to timestamp number
                if isinstance(timestamp, str):
                    from datetime import datetime
                    return datetime.fromisoformat(timestamp).timestamp()
                return float(timestamp)
            except (ValueError, TypeError):
                return 0.0

        return sorted(
            messages,
            key=lambda msg: (
                -get_timestamp(msg),  # Sort by timestamp descending
                0 if msg["role"] == "user" else 1,  # User messages first
                -self.calculate_importance(msg["content"])  # Important messages first
            )
        )

    def summarize_context(self, messages: List[Dict[str, str]]) -> List[Dict[str, str]]:
        """Create a summary of the context"""
        # Basic summarization - could be enhanced
        summary = []
        for msg in messages[-5:]:  # Last 5 messages
            summary.append({
                "role": msg["role"],
                "content": self.smart_truncate(msg["content"], 100)
            })
        return summary

    def update_strategy(self, response_quality: float):
        """Adjust context strategy based on response quality"""
        if response_quality < 0.7:
            self.context_strategy = "full"
        elif response_quality < 0.9:
            self.context_strategy = "compressed"
        else:
            self.context_strategy = "summary"

    def track_token_usage(self, tokens: int):
        """Track token usage with enhanced monitoring"""
        self.context_manager.monitor.track_token_usage(tokens)
        self.context_manager.monitor.optimize_compression()

    def get_token_trend(self) -> float:
        """Get token usage trend"""
        if len(self.metrics["token_usage"]) < 2:
            return 0.0
        return (self.metrics["token_usage"][-1] - self.metrics["token_usage"][0]) / len(self.metrics["token_usage"])

    def optimize_compression(self):
        """Optimize compression ratio based on trends"""
        trend = self.get_token_trend()
        if trend > 0:
            self.metrics["compression_ratio"] *= 0.9
        else:
            self.metrics["compression_ratio"] = min(1.0, self.metrics["compression_ratio"] * 1.1)
