from litellm import completion
from typing import List, Dict, Any

class LLMClient:
    def __init__(self):
        pass

    def generate(self, prompt: str, model: str = "gpt-3.5-turbo") -> str:
        messages = [{"role": "user", "content": prompt}]
        
        response = completion(
            model=model,
            messages=messages
        )
        return response.choices[0].message.content
