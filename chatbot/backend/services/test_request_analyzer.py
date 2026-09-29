from chatbot.backend.services.request_analyzer import analyze_request

test_messages = [
    "What is machine learning?",
    "Generate a 2-page PDF report about AI in healthcare",
    "Can you explain what a CSV file is?",
    "Make me a CSV with 10 rows of sample data",
    "Create a DOCX summarizing our meeting notes",
]

for msg in test_messages:
    print(msg, "->", analyze_request(msg))
