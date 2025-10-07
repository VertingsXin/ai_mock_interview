from gpt4all import GPT4All

# Load the model (use your actual model path)
model = GPT4All("Meta-Llama-3-8B-Instruct.Q4_0.gguf")  # or your file if stored locally

def generate_feedback(user_answer: str, model_answer: str) -> str:
    prompt = f"""
You are an instructor evaluating a student's answer against a model answer.

Please provide ONLY the following, exactly in this format, and only in this format, nothing before or after:
[one or two concise sentences about errors, missing points, or misunderstandings]

User answer:
{user_answer}

Model answer:
{model_answer}

Your evaluation:
"""
    full_response = model.generate(prompt, max_tokens=150)
    sentences = text.split('.')
    sentences = [s.strip() for s in sentences if s.strip()]
    return '. '.join(sentences[:2]) + ('.' if len(sentences) >= 2 else '')