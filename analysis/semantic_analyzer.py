from typing import List, Dict, Tuple, Any, Optional
from logging_config import get_logger

logger = get_logger(__name__)

class SemanticAnalyzer:
    def __init__(self):
        self.nlp = None
        self.spacy_available = False
        
        # Try to initialize spaCy if available
        try:
            import spacy
            self.nlp = spacy.load("en_core_web_sm")
            self.spacy_available = True
            logger.info("spaCy initialized successfully")
        except ImportError:
            logger.warning("spaCy not installed - running with basic analysis only")
        except OSError:
            logger.warning("spaCy model not found - running with basic analysis only")
        except Exception as e:
            logger.warning(f"Error initializing spaCy: {str(e)} - running with basic analysis only")

    def process_text(self, text: str) -> Dict[str, Any]:
        """
        Basic entity extraction and placeholder for advanced knowledge-graph steps.
        Falls back to basic analysis if spaCy is not available.
        
        Args:
            text: Input text to analyze
            
        Returns:
            Dict containing entities and graph edges
        """
        if not self.spacy_available:
            return self._basic_analysis(text)
            
        try:
            doc = self.nlp(text)
            
            # Extract named entities
            entities = [(ent.text, ent.label_) for ent in doc.ents]
            
            # Extract basic relationships (subject-verb-object)
            graph_edges = []
            for token in doc:
                if token.dep_ == "ROOT":
                    for child in token.children:
                        if child.dep_ in ["nsubj", "dobj"]:
                            edge = (child.text, token.text, child.dep_)
                            graph_edges.append(edge)
            
            logger.debug("Processed text with %d entities and %d edges", 
                        len(entities), len(graph_edges))
            
            return {
                "entities": entities,
                "graph_edges": graph_edges,
                "doc_length": len(doc),
                "processed_at": "2025-02-13",  # Using the current date from environment
                "analysis_type": "spacy"
            }
            
        except Exception as e:
            logger.error("Error in spaCy analysis: %s", str(e))
            return self._basic_analysis(text)
            
    def _basic_analysis(self, text: str) -> Dict[str, Any]:
        """
        Perform basic text analysis without spaCy.
        """
        try:
            # Simple word-based analysis
            words = text.split()
            
            # Basic entity detection (capitalized words)
            entities = [
                (word, "BASIC_ENTITY") 
                for word in words 
                if word[0].isupper() and len(word) > 1
            ]
            
            # Simple subject-verb detection based on word order
            graph_edges = []
            for i in range(len(words) - 1):
                if words[i][0].isupper() and i + 1 < len(words):
                    graph_edges.append((words[i], words[i + 1], "basic_relation"))
            
            return {
                "entities": entities,
                "graph_edges": graph_edges,
                "doc_length": len(words),
                "processed_at": "2025-02-13",
                "analysis_type": "basic"
            }
            
        except Exception as e:
            logger.error("Error in basic analysis: %s", str(e))
            return {
                "entities": [],
                "graph_edges": [],
                "doc_length": 0,
                "error": str(e),
                "analysis_type": "failed"
            }
