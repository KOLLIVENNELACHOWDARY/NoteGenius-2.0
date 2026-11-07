import spacy
import random
import nltk
from nltk.corpus import wordnet as wn
from nltk.corpus import stopwords
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import string
from collections import Counter
import re

# NLTK data 
try:
    nltk.data.find('corpora/wordnet')
    nltk.data.find('corpora/stopwords')
except LookupError:
    nltk.download('wordnet')
    nltk.download('stopwords')
    nltk.download('omw-1.4')

# Load spaCy model
try:
    nlp = spacy.load("en_core_web_sm")
except OSError:
    print("Please install spaCy English model: python -m spacy download en_core_web_sm")
    exit()

# Initialize stopwords
stop_words = set(stopwords.words('english'))

class MCQGenerator:
    def __init__(self):
        self.nlp = nlp
        self.stop_words = stop_words
        
    def clean_sentences(self, text):
        """Clean and split text into sentences"""
        doc = self.nlp(text)
        sentences = []
        for sent in doc.sents:
            # Remove sentences that are too short or too long
            if 10 <= len(sent.text.strip()) <= 200:
                sentences.append(sent.text.strip())
        return sentences
    
    def important_keywords(self, sent):
        """Extract important keywords using multiple criteria"""
        doc = self.nlp(sent)
        keywords = []
        
        # noun chunks and named entities
        for chunk in doc.noun_chunks:
            if (chunk.root.pos_ in ["NOUN", "PROPN"] and 
                chunk.text.lower() not in self.stop_words and
                len(chunk.text) > 2):
                keywords.append(chunk.text)
        
        # named entities
        for ent in doc.ents:
            if ent.label_ in ["PERSON", "ORG", "GPE", "PRODUCT", "EVENT"]:
                keywords.append(ent.text)
        
        # important adjectives and verbs
        for token in doc:
            if (token.pos_ in ["ADJ", "VERB"] and 
                token.text.lower() not in self.stop_words and
                len(token.text) > 3 and
                not token.is_punct):
                keywords.append(token.text)
        
        return list(set(keywords))
    
    def wordnet_synonyms(self, word, pos_tag=None):
        """Get synonyms using WordNet"""
        synonyms = set()
        
        # Get all synsets for the word
        synsets = wn.synsets(word.lower())
        
        if pos_tag:
            # Filter by part of speech if provided
            pos_map = {'NOUN': 'n', 'VERB': 'v', 'ADJ': 'a', 'ADV': 'r'}
            if pos_tag in pos_map:
                synsets = [s for s in synsets if s.pos() == pos_map[pos_tag]]
        
        for synset in synsets:
            for lemma in synset.lemmas():
                synonym = lemma.name().replace('_', ' ')
                if synonym.lower() != word.lower():
                    synonyms.add(synonym)
        
        return list(synonyms)
    
    def wordnet_antonyms(self, word):
        """Get antonyms using WordNet"""
        antonyms = set()
        
        for synset in wn.synsets(word.lower()):
            for lemma in synset.lemmas():
                if lemma.antonyms():
                    for antonym in lemma.antonyms():
                        antonym_word = antonym.name().replace('_', ' ')
                        antonyms.add(antonym_word)
        
        return list(antonyms)
    
    def wordnet_hyponyms_hypernyms(self, word):
        """Get hyponyms and hypernyms using WordNet"""
        related_words = set()
        
        for synset in wn.synsets(word.lower()):
            # Get hyponyms (more specific terms)
            for hyponym in synset.hyponyms():
                for lemma in hyponym.lemmas():
                    related_words.add(lemma.name().replace('_', ' '))
            
            # Get hypernyms (more general terms)
            for hypernym in synset.hypernyms():
                for lemma in hypernym.lemmas():
                    related_words.add(lemma.name().replace('_', ' '))
        
        return list(related_words)
    
    def enhanced_distractors(self, correct_word, all_sentences, context_sentence, top_n=3):
        """Generate distractors using multiple methods"""
        distractors = set()
        
        # Method 1: WordNet synonyms
        synonyms = self.wordnet_synonyms(correct_word)
        distractors.update(synonyms[:2])
        
        # Method 2: WordNet antonyms
        antonyms = self.wordnet_antonyms(correct_word)
        distractors.update(antonyms[:1])
        
        # Method 3: WordNet hyponyms/hypernyms
        related_words = self.wordnet_hyponyms_hypernyms(correct_word)
        distractors.update(related_words[:2])
        
        # Method 4: TF-IDF based similarity (original method)
        corpus = all_sentences + [correct_word]
        try:
            vectorizer = TfidfVectorizer(stop_words='english', max_features=1000)
            tfidf_matrix = vectorizer.fit_transform(corpus)
            cosine_sim = cosine_similarity(tfidf_matrix[-1], tfidf_matrix[:-1])[0]
            similar_sentences = [all_sentences[i] for i in cosine_sim.argsort()[::-1][:5]]
            
            for sent in similar_sentences:
                keywords = self.get_important_keywords(sent)
                for word in keywords:
                    if (word.lower() != correct_word.lower() and 
                        word not in distractors and
                        len(word) > 2):
                        distractors.add(word)
                        if len(distractors) >= top_n * 2:
                            break
                if len(distractors) >= top_n * 2:
                    break
        except:
            pass
        
        # Method 5: Context-based distractors (same POS from context)
        doc = self.nlp(context_sentence)
        target_pos = None
        for token in doc:
            if correct_word.lower() in token.text.lower():
                target_pos = token.pos_
                break
        
        if target_pos:
            for sent in all_sentences:
                sent_doc = self.nlp(sent)
                for token in sent_doc:
                    if (token.pos_ == target_pos and 
                        token.text.lower() != correct_word.lower() and
                        token.text not in distractors and
                        len(token.text) > 2):
                        distractors.add(token.text)
        
        # Filter and clean distractors
        filtered_distractors = []
        for dist in distractors:
            if (dist.lower() != correct_word.lower() and
                len(dist) > 1 and
                dist not in filtered_distractors and
                not dist.lower() in self.stop_words):
                filtered_distractors.append(dist)
        
        return filtered_distractors[:top_n]
    
    def validate_question(self, question, answer, options):
        """Validate if the question is good quality"""
        # Check if question has blank
        if "_____" not in question:
            return False
        
        # Check if answer is in options
        if answer not in options:
            return False
        
        # Check minimum number of options
        if len(options) < 2:
            return False
        
        # Check if options are not too similar
        unique_options = set(opt.lower() for opt in options)
        if len(unique_options) < len(options) * 0.8:
            return False
        
        return True
    
    def generate_mcqs(self, text, num_questions=5, difficulty='medium'):
        """Generate MCQs with enhanced features"""
        sentences = self.clean_sentences(text)
        questions = []
        used_keywords = set()
        
        # Adjust keyword selection based on difficulty
        min_keyword_length = {'easy': 3, 'medium': 4, 'hard': 5}[difficulty]
        
        for sent in sentences:
            if len(questions) >= num_questions:
                break
                
            keywords = self.important_keywords(sent)
            
            # Filter keywords based on difficulty
            filtered_keywords = [
                kw for kw in keywords 
                if (len(kw) >= min_keyword_length and 
                    kw.lower() not in used_keywords and
                    kw.lower() not in self.stop_words)
            ]
            
            if not filtered_keywords:
                continue
            
            # Choose keyword (prefer nouns and proper nouns)
            keyword = None
            doc = self.nlp(sent)
            for token in doc:
                if (token.text in filtered_keywords and 
                    token.pos_ in ["NOUN", "PROPN"]):
                    keyword = token.text
                    break
            
            if not keyword:
                keyword = random.choice(filtered_keywords)
            
            # Create question
            question = sent.replace(keyword, "_____")
            
            # Generate distractors
            distractors = self.enhanced_distractors(keyword, sentences, sent)
            
            # Ensure we have enough options
            if len(distractors) < 2:
                continue
            
            # Create options
            options = distractors[:3] + [keyword]
            random.shuffle(options)
            
            # Validate question
            if self.validate_question(question, keyword, options):
                questions.append({
                    'question': question,
                    'answer': keyword,
                    'options': options,
                    'difficulty': difficulty,
                    'context': sent
                })
                used_keywords.add(keyword.lower())
        
        return questions
    
    def run_interactive_quiz(self, questions):
        """Run  quiz with scoring"""
        if not questions:
            print("No questions generated. Please check your input text.")
            return
        
        score = 0
        total = len(questions)
      
        print(f"MCQ QUIZ - {total} Questions")
        
        for i, q in enumerate(questions, 1):
            print(f"Question {i}/{total}")
            print(f"Difficulty: {q['difficulty'].upper()}")
            print(f"\n{q['question']}")
            print("\nOptions:")
            
            options_map = {}
            for j, opt in enumerate(q['options']):
                letter = chr(97 + j)  # a, b, c, d
                options_map[letter] = opt
                print(f"  {letter}. {opt}")
            
            while True:
                try:
                    answer = input(f"\nEnter your answer (a-{chr(96 + len(q['options']))}): ").lower().strip()
                    if answer in options_map:
                        break
                    else:
                        print("Invalid option. Please try again.")
                except KeyboardInterrupt:
                    print("\nQuiz interrupted.")
                    return
            
            if options_map[answer] == q['answer']:
                print("✅ Correct!")
                score += 1
            else:
                print("❌ Wrong!")
            
            print(f"✔️ Correct Answer: {q['answer']}")
            
            # Show context if available
            if 'context' in q:
                print(f"📖 Context: {q['context']}")
        
        # Final score
        print(f"\n{'='*50}")
        print(f"QUIZ COMPLETED!")
        print(f"Final Score: {score}/{total} ({score/total*100:.1f}%)")
        print(f"{'='*50}")
        
        if score/total >= 0.8:
            print("🎉 Excellent work!")
        elif score/total >= 0.6:
            print("👍 Good job!")
        else:
            print("📚 Keep studying!")

# Example usage
def main():
    # Initialize generator
    mcq_gen = MCQGenerator()
    
    # Sample text
    input_text = """
    Solids, when heated, emit radiation varying over a wide range of wavelengths. For example: when we heat solid colour, changes continue with a further increase in temperature. This change in colour happens from a lower frequency region to a higher frequency region as the temperature increases. For example, in many cases, it changes from red to blue. An ideal body which can emit and absorb radiation of all frequencies is called a black body. The radiation emitted by such bodies is called black body radiation.

    Thus, we can say that variation of frequency for black body radiation depends on the temperature. At a given temperature, the intensity of radiation is found to increase with an increase in the wavelength of radiation which increases to a maximum value and then decreases with an increase in the wavelength. This phenomenon couldn't be explained with the help of Maxwell's suggestions. Hence, Planck proposed Planck's quantum theory to explain this phenomenon.
    
    Quantum theory revolutionized our understanding of physics. It introduced the concept that energy is quantized, meaning it comes in discrete packets called quanta. This theory helped explain many phenomena that classical physics couldn't, including the photoelectric effect and atomic spectra. The quantum mechanical model of the atom replaced the classical model and provided a more accurate description of atomic behavior.
    """
    
    # Generate MCQs
    print("Generating MCQs...")
    questions = mcq_gen.generate_mcqs(input_text, num_questions=8, difficulty='medium')
    
    if questions:
        print(f"Generated {len(questions)} questions successfully!")
        
        # Option to review questions before quiz
        review = input("\nWould you like to review the questions before starting the quiz? (y/n): ").lower()
        if review == 'y':
            for i, q in enumerate(questions, 1):
                print(f"\n--- Question {i} ---")
                print(f"Q: {q['question']}")
                print(f"Options: {', '.join(q['options'])}")
                print(f"Answer: {q['answer']}")
        
        # Run interactive quiz
        print("\nLet's start the quiz...")
        mcq_gen.run_interactive_quiz(questions)

if __name__ == "__main__":
    main()
