import math
from datetime import datetime
from typing import List, Dict, Optional, Any, TypedDict, Union

from logging_config import get_logger
from token_utils import (
    count_message_tokens,
    count_conversation_tokens,
    truncate_content
)
from models.chat import Chat

logger = get_logger(__name__)


class ContextManager:
    """
    A manager for conversation context handling. Allows different context strategies,
    including full context, compression, and summarization.
    """

    def __init__(self, model_max_tokens: int) -> None:
        """
        Initialize the ContextManager.

        Args:
            model_max_tokens: The maximum number of tokens allowed by the model.
        """
        self.model_max_tokens = model_max_tokens
        self.context_strategy = "full"  # Default strategy
        self.context_cache: Dict[int, List[Dict[str, Any]]] = {}
        self.monitor = ContextMonitor()

    def get_context(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Get an optimized context from the given messages.

        Args:
            messages: A list of messages, where each message is a dict
                      with keys like "role", "content", "metadata", etc.

        Returns:
            The optimized context (subset or modified list of messages).
        """
        # Create a cache key from the messages' role/content pairs
        cache_key = hash(tuple((m["role"], m["content"]) for m in messages))
        if cache_key in self.context_cache:
            self.monitor.track_cache_hit()
            logger.debug("Context cache hit for key %s", cache_key)
            return self.context_cache[cache_key]

        # Prioritize and apply strategy
        prioritized = self.prioritize_messages(messages)
        logger.debug("Messages prioritized. Applying context strategy '%s'", self.context_strategy)

        if self.context_strategy == "full":
            context = prioritized
        elif self.context_strategy == "compressed":
            context = self.compress_context(prioritized, self.model_max_tokens)
        else:  # 'summary'
            context = self.summarize_context(prioritized)

        # Update the cache and track miss
        self.context_cache[cache_key] = context
        self.monitor.track_cache_miss()
        logger.debug("Context cache miss. Key %s stored.", cache_key)

        return context

    def prioritize_messages(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Sort messages by importance, role, and timestamp to prioritize them.

        Args:
            messages: A list of message dictionaries.

        Returns:
            A sorted list of messages in descending order of priority.
        """

        def get_timestamp(msg: Dict[str, Any]) -> float:
            timestamp = msg.get("metadata", {}).get("timestamp", "")
            try:
                if isinstance(timestamp, str):
                    return datetime.fromisoformat(timestamp).timestamp()
                return float(timestamp)
            except (ValueError, TypeError):
                return 0.0

        sorted_messages = sorted(
            messages,
            key=lambda msg: (
                -get_timestamp(msg),  # Sort by timestamp descending
                0 if msg.get("role") == "user" else 1,  # User messages first
                -self.calculate_importance(msg.get("content", "")),  # Important messages first
            ),
        )
        logger.debug("Prioritized %d messages.", len(sorted_messages))
        return sorted_messages

    def update_strategy(self, response_quality: float) -> None:
        """
        Adjust context strategy based on response quality.

        Args:
            response_quality: A float between 0 and 1 indicating model response quality.
        """
        logger.debug("Updating context strategy based on response quality: %f", response_quality)
        if response_quality < 0.7:
            self.context_strategy = "full"
        elif response_quality < 0.9:
            self.context_strategy = "compressed"
        else:
            self.context_strategy = "summary"

    def compress_context(self, messages: List[Dict[str, Any]], max_tokens: int) -> List[Dict[str, Any]]:
        """
        Compress context to fit within the specified token limit.

        Args:
            messages: The messages to compress.
            max_tokens: Maximum tokens allowed in the compressed context.

        Returns:
            The compressed list of messages.
        """
        compressed: List[Dict[str, Any]] = []
        current_tokens = 0

        for msg in messages:
            compressed_msg = {
                "role": msg["role"],
                "content": self.smart_truncate(msg["content"], max_tokens - current_tokens),
            }
            msg_tokens = count_message_tokens(compressed_msg)

            if current_tokens + msg_tokens > max_tokens:
                logger.debug("Reached token limit during compression.")
                break

            compressed.append(compressed_msg)
            current_tokens += msg_tokens

        logger.debug(
            "Compressed %d messages to fit within %d tokens (used %d).",
            len(messages), max_tokens, current_tokens
        )
        return compressed

    def summarize_context(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Create a summary of the context by taking the last few messages.

        Args:
            messages: A list of message dictionaries.

        Returns:
            A summarized list of message dictionaries.
        """
        # Example: keep the last 5 messages
        logger.debug("Summarizing context by keeping the last 5 messages.")
        summary: List[Dict[str, Any]] = []
        for msg in messages[-5:]:
            truncated_content = self.smart_truncate(msg["content"], 100)
            summary.append({
                "role": msg["role"],
                "content": truncated_content,
            })
        return summary

    def calculate_importance(self, content: str) -> float:
        """
        Calculate an approximate importance score for a message content.

        Args:
            content: The message content.

        Returns:
            A float score between 0.0 and 1.0 indicating importance.
        """
        score = min(1.0, len(content) / 1000)
        logger.debug("Calculated importance score %.3f for content of length %d", score, len(content))
        return score

    def smart_truncate(self, content: str, max_tokens: int) -> str:
        """
        Truncate the content in a semi-intelligent way, focusing on 'important' sentences.

        Args:
            content: The original text content to be truncated.
            max_tokens: Maximum tokens allowed for this content.

        Returns:
            A truncated string with ellipses added if it was shortened.
        """
        sentences = content.split('. ')
        important_sentences = [s for s in sentences if self.is_important(s)]
        truncated_list: List[str] = []
        current_tokens = 0

        for sentence in important_sentences:
            sentence_tokens = count_message_tokens({"content": sentence})
            if current_tokens + sentence_tokens > max_tokens:
                logger.debug("smart_truncate reached token limit with sentence: %s", sentence)
                break
            truncated_list.append(sentence)
            current_tokens += sentence_tokens

        if len(truncated_list) < len(important_sentences):
            return ". ".join(truncated_list) + "..."
        return ". ".join(truncated_list)

    def is_important(self, sentence: str) -> bool:
        """
        Basic heuristic to decide if a sentence is 'important'.

        Args:
            sentence: A sentence from the message content.

        Returns:
            True if the sentence contains certain keywords or meets criteria.
        """
        lower_s = sentence.lower()
        # Check for presence of keywords
        keywords = ["important", "key", "critical", "summary"]
        return any(keyword in lower_s for keyword in keywords)


class ContextMonitor:
    """
    Tracks various metrics for context usage and performance, including caching,
    token usage, compression, and response quality.
    """

    class MetricsDict(TypedDict):
        token_usage: List[int]
        cache_hits: int
        cache_misses: int
        compression_ratio: float
        response_quality: List[float]

    def __init__(self) -> None:
        """Initialize the metrics dictionary."""
        self.metrics: ContextMonitor.MetricsDict = {
            "token_usage": [],
            "cache_hits": 0,
            "cache_misses": 0,
            "compression_ratio": 1.0,
            "response_quality": [],
        }

    def track_token_usage(self, tokens: int) -> None:
        """
        Record token usage data. Keeps up to the last 100 entries.
        """
        token_usage = self.metrics["token_usage"]
        if not isinstance(token_usage, list):
            token_usage = []
        token_usage.append(tokens)
        if len(token_usage) > 100:
            self.metrics["token_usage"] = token_usage
            token_usage.pop(0)

    def track_cache_hit(self) -> None:
        """Increment cache hits."""
        self.metrics["cache_hits"] += 1

    def track_cache_miss(self) -> None:
        """Increment cache misses."""
        self.metrics["cache_misses"] += 1

    def track_response_quality(self, quality: float) -> None:
        """
        Track the model's response quality, storing up to the last 100 scores.
        """
        response_quality = self.metrics["response_quality"]
        if not isinstance(response_quality, list):
            response_quality = []
        response_quality.append(quality)
        if len(response_quality) > 100:
            response_quality.pop(0)
        self.metrics["response_quality"] = response_quality

    def optimize_compression(self) -> None:
        """
        Adjust the compression ratio based on the average response quality.
        If quality is low, compress more aggressively; if high, compress less.
        """
        response_quality = self.metrics["response_quality"]
        if not isinstance(response_quality, list) or not response_quality:
            return

        compression_ratio = self.metrics["compression_ratio"]
        if not isinstance(compression_ratio, float):
            return

        if sum(response_quality) / len(response_quality) < 0.7:
            self.metrics["compression_ratio"] *= 0.9  # More aggressive compression
        else:
            self.metrics["compression_ratio"] = min(1.0, self.metrics["compression_ratio"] * 1.1)

    def calculate_optimal_window_size(self, message_count: int) -> int:
        """
        Calculate an optimal context window size based on model limits and message count.

        Args:
            message_count: The number of messages in the conversation.

        Returns:
            An integer indicating the suggested context window size.
        """
        # In a real scenario, you'd have direct access to model_max_tokens
        # or pass it into this method. For demonstration, we approximate:
        base_window = 20000  # Example fallback
        message_factor = min(1.0, message_count / 50)
        window_size = int(base_window * (1 - message_factor))
        logger.debug("Calculated optimal window size %d for %d messages.", window_size, message_count)
        return window_size

    def compress_file_content(self, content: str, max_tokens: int) -> str:
        """
        Special compression for file content.
        Keeps the first 5 and last 5 lines, adds a summary note if truncated.

        Args:
            content: The file content as a string.
            max_tokens: Maximum number of tokens allowed.

        Returns:
            A truncated or fully included file content.
        """
        lines = content.splitlines()
        if len(lines) > 10:
            summary = f"\n\n[File truncated. Original had {len(lines)} lines]"
            keep_lines = lines[:5] + lines[-5:]
            truncated = "\n".join(keep_lines) + summary
            return truncate_content(truncated, max_tokens)
        return truncate_content(content, max_tokens)

    def get_token_trend(self) -> float:
        """
        Calculate the trend in token usage over time.

        Returns:
            A float indicating upward/downward token usage trend.
        """
        usage = self.metrics["token_usage"]
        if not isinstance(usage, list):
            return 0.0

        if len(usage) < 2 or not all(isinstance(x, int) for x in usage):
            return 0.0

        trend = (usage[-1] - usage[0]) / len(usage)
        logger.debug("Calculated token usage trend: %.3f", trend)
        return trend
