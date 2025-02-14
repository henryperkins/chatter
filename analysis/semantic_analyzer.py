import spacy
from typing import List, Dict, Tuple, Any
from logging_config import get_logger

logger = get_logger(__name__)

class SemanticAnalyzer:
    def __init__(self):
        try:
            import spacy
        except ImportError as e:
            logger.critical("spaCy is not installed. Please install with 'pip install spacy'")
            raise RuntimeError("spaCy required - see logs for details") from e

        # Load a lightweight English model
        try:
            self.nlp = spacy.load("en_core_web_sm")
        except OSError as e:
            logger.error("spaCy model 'en_core_web_sm' not found. First activate AND USE your virtual environment:")
            logger.error("1. source venv/bin/activate")
            logger.error("2. python -m spacy download en_core_web_sm")
            logger.error("3. Verify with: python -c 'import spacy; spacy.load(\"en_core_web_sm\")'")
            raise RuntimeError("Missing spaCy model - follow venv installation steps above") from e

    def process_text(self, text: str) -> Dict[str, Any]:
        """
        Basic entity extraction and placeholder for advanced knowledge-graph steps.
        
        Args:
            text: Input text to analyze
            
        Returns:
            Dict containing entities and graph edges
        """
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
                "processed_at": "2025-02-13"  # Using the current date from environment
            }
            
        except Exception as e:
            logger.error("Error processing text: %s", str(e))
            return {"entities": [], "graph_edges": [], "error": str(e)}
