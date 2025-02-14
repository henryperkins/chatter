"""Knowledge graph management for semantic relationship tracking."""

from typing import Any, Dict, List, Optional, Set, Tuple
import spacy
from spacy.tokens import Doc
from logging_config import get_logger

logger = get_logger(__name__)

class KnowledgeGraph:
    """Manages entity relationships and semantic connections."""
    
    def __init__(self):
        """Initialize the knowledge graph with spaCy model."""
        self.nlp = None
        self.spacy_available = False
        
        try:
            import spacy
            # Use system-installed model path
            self.nlp = spacy.load("/usr/lib/python3/dist-packages/en_core_web_sm")
            self.spacy_available = True
            logger.info("spaCy initialized successfully for knowledge graph")
        except OSError as e:
            logger.error("Could not load spaCy model from system path: %s", str(e))
            self.nlp = None
            self.spacy_available = False
            logger.warning("Knowledge graph will operate in basic mode")
            
        self.entities: Dict[str, Set[str]] = {}
        self.relationships: List[Tuple[str, str, str]] = []
        self.context_cache: Dict[str, List[Dict[str, Any]]] = {}

    def process_text(self, text: str) -> Dict[str, List[Dict[str, str]] | List[Tuple[str, str, str]]]:
        """Extract entities and relationships from text."""
        if not self.spacy_available or self.nlp is None:
            # Basic processing when spaCy is not available
            words = text.split()
            # Basic entity detection (capitalized words)
            basic_entities = [
                {"text": word, "type": "BASIC_ENTITY"}
                for word in words
                if word[0].isupper() and len(word) > 1
            ]
            # Simple relationship detection based on word order
            basic_relationships = [
                (words[i], words[i + 1], "basic_relation")
                for i in range(len(words) - 1)
                if words[i][0].isupper()
            ]
            return {
                "entities": basic_entities,
                "relationships": basic_relationships
            }
            
        doc = self.nlp(text)
        
        # Extract named entities
        for ent in doc.ents:
            if ent.label_ not in self.entities:
                self.entities[ent.label_] = set()
            self.entities[ent.label_].add(ent.text)
            
        # Extract relationships (subject-verb-object)
        for token in doc:
            if token.dep_ == "ROOT":
                for child in token.children:
                    if child.dep_ in ["nsubj", "dobj"]:
                        self.relationships.append((
                            child.text,
                            token.text,
                            child.dep_
                        ))

        return {
            "entities": [{"text": e, "type": t} 
                        for t in self.entities 
                        for e in self.entities[t]],
            "relationships": self.relationships
        }

    def get_related_context(self, text: str, max_items: int = 5) -> List[Dict[str, str]]:
        """Get semantically related context items."""
        if not self.spacy_available or self.nlp is None:
            # Basic context matching when spaCy is not available
            words = set(text.lower().split())
            related_context = []
            
            for cache_key, context in self.context_cache.items():
                cache_words = set(cache_key.lower().split())
                if words & cache_words:  # If there's word overlap
                    related_context.extend(context)
                if len(related_context) >= max_items:
                    break
            return related_context[:max_items]
            
        doc = self.nlp(text)
        related_context = []
        
        # Find entities in the query
        query_entities = {ent.text for ent in doc.ents}
        
        # Get cached context with matching entities
        for cache_key, context in self.context_cache.items():
            cache_doc = self.nlp(cache_key)
            cache_entities = {ent.text for ent in cache_doc.ents}
            
            # If there's entity overlap, include this context
            if query_entities & cache_entities:
                related_context.extend(context)
                
            if len(related_context) >= max_items:
                break
                
        return related_context[:max_items]

    def add_to_context(self, text: str, metadata: Optional[Dict] = None) -> None:
        """Add text to the context cache with optional metadata."""
        if not metadata:
            metadata = {}
            
        if self.spacy_available and self.nlp is not None:
            doc = self.nlp(text)
            context_item = {
                "text": text,
                "entities": [ent.text for ent in doc.ents],
                **metadata
            }
        else:
            # Basic entity extraction when spaCy is not available
            words = text.split()
            basic_entities = [
                word for word in words
                if word[0].isupper() and len(word) > 1
            ]
            context_item = {
                "text": text,
                "entities": basic_entities,
                **metadata
            }
        
        # Use text as cache key
        if text not in self.context_cache:
            self.context_cache[text] = []
        self.context_cache[text].append(context_item)
