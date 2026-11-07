from transformers import pipeline
import torch

# Auto-detect device: GPU if available, else CPU
device = 0 if torch.cuda.is_available() else -1

# Load the QA pipeline with tinyroberta model
qa_pipeline = pipeline("question-answering", model="deepset/tinyroberta-squad2", device=device)

# Input context (text passage)
context = """
Machine Learning (ML) is a branch of artificial intelligence (AI) that focuses on building systems that can automatically learn and improve from experience without being explicitly programmed. ML involves the development of algorithms that can analyze data, identify patterns, make decisions, and predict outcomes. The three main types of machine learning are supervised learning, where the model is trained using labeled data; unsupervised learning, where the model uncovers hidden patterns from unlabeled data; and reinforcement learning, where an agent learns by interacting with an environment and receiving feedback in the form of rewards or penalties. Machine learning is widely used in various real-world applications such as spam detection, recommendation engines (like those used by Netflix or Amazon), self-driving cars, fraud detection, voice and facial recognition, and medical diagnostics. It relies on statistical techniques, large datasets, and computational power (like GPUs) to perform efficiently. As the volume of data and computing capabilities grow, ML continues to drive innovation across industries like finance, healthcare, education, agriculture, and more, enabling smarter, data-driven decisions.
"""

# List of questions
questions = [
    "What is Machine Learning?",
    "How is Machine Learning related to Artificial Intelligence?",
    "What is the main goal of Machine Learning?",
    "What types of data are used in supervised learning?",

    " What is the difference between supervised and unsupervised learning?",

    "How does reinforcement learning work?",

     "What do ML algorithms do with input data?",
    "what is magnetic field"


]

# Run the QA model for each question
for q in questions:
    result = qa_pipeline(question=q, context=context)
    print(f"Q: {q}")
    print(f"A: {result['answer']}\n")
