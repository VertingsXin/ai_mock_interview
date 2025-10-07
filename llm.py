import os
from dotenv import load_dotenv
from huggingface_hub import InferenceClient

api_key = os.getenv("HF_TOKEN")

client = InferenceClient(
    provider="hf-inference",
    api_key=api_key,
)

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

    completion = client.chat.completions.create(
        model="HuggingFaceTB/SmolLM3-3B",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=150,
    )

    return completion.choices[0].message['content']

