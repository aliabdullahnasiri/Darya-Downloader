from typing import Optional

from azure.ai.inference import ChatCompletionsClient
from azure.ai.inference.models import SystemMessage, UserMessage
from azure.core.credentials import AzureKeyCredential

from env import Env


class LlamaChatClient:
    """
    Reusable OOP wrapper for Azure AI Inference ChatCompletionsClient
    """

    def __init__(
        self,
        endpoint: str,
        model: str,
        api_key: Optional[str] = None,
        temperature: float = 0.8,
        top_p: float = 0.1,
        max_tokens: int = 2048,
    ):
        self.endpoint = endpoint
        self.model = model
        self.api_key = api_key or Env.GITHUB_TOKEN

        if not self.api_key:
            raise ValueError("API key not provided. Set GITHUB_TOKEN in environment.")

        self.temperature = temperature
        self.top_p = top_p
        self.max_tokens = max_tokens

        self.client = ChatCompletionsClient(
            endpoint=self.endpoint,
            credential=AzureKeyCredential(self.api_key),
        )

    def chat(self, user_message: str, system_message: str = "") -> str:
        """
        Send a chat request and return response text
        """
        response = self.client.complete(
            messages=[
                SystemMessage(system_message),
                UserMessage(user_message),
            ],
            temperature=self.temperature,
            top_p=self.top_p,
            max_tokens=self.max_tokens,
            model=self.model,
        )

        return response.choices[0].message.content


if __name__ == "__main__":
    chat_client = LlamaChatClient(
        endpoint="https://models.github.ai/inference",
        model="meta/Llama-4-Scout-17B-16E-Instruct",
    )

    reply = chat_client.chat("What is the difference between stack and heap?")
    print(reply)
