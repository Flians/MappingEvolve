# Carefully checked and no issues found
import time
from openai import OpenAI

import logging

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
# Messages will propagate to root logger which handles console and file output


class ModelCalls:
    """Base class for model calls"""

    def __init__(self, api_key=None, base_url=None, model_name=None):
        self.api_key = api_key
        self.base_url = base_url
        self.model_name = model_name
        self.client = None
        # Initialize token usage tracking
        self.total_prompt_tokens = 0
        self.total_completion_tokens = 0
        self.total_tokens = 0
        self.api_calls = 0

    def get_output(self, prompt, max_retries=3, retry_delay=2):
        """
        Abstract method to get model output

        Args:
            prompt (str): The user input prompt
            max_retries (int): Maximum number of retry attempts (default: 3)
            retry_delay (int): Delay between retries in seconds (default: 2)

        Returns:
            str: The model response
        """
        raise NotImplementedError("Subclasses must implement get_output method")

    def get_token_usage(self):
        """
        Get token usage statistics

        Returns:
            dict: Dictionary containing token usage statistics
        """
        return {
            "total_prompt_tokens": self.total_prompt_tokens,
            "total_completion_tokens": self.total_completion_tokens,
            "total_tokens": self.total_tokens,
            "api_calls": self.api_calls,
        }

    def add_token_usage(self, prompt_tokens, completion_tokens):
        """
        Add token usage from an API call

        Args:
            prompt_tokens (int): Number of tokens in the prompt
            completion_tokens (int): Number of tokens in the completion
        """
        self.total_prompt_tokens += prompt_tokens
        self.total_completion_tokens += completion_tokens
        self.total_tokens += prompt_tokens + completion_tokens
        self.api_calls += 1


class DeepSeekModelCalls(ModelCalls):
    """DeepSeek API call implementation"""

    def __init__(self, api_key, base_url, model_name, system_prompt=None):
        super().__init__(api_key, base_url, model_name)
        self.client = OpenAI(api_key=api_key, base_url=base_url)
        self.system_prompt = system_prompt

    def get_output(self, prompt, max_retries=3, retry_delay=2):
        """
        Get output from DeepSeek API with retry logic

        Args:
            prompt (str): The user input prompt
            max_retries (int): Maximum number of retry attempts (default: 3)
            retry_delay (int): Delay between retries in seconds (default: 2)

        Returns:
            str: The chat completion response
        """
        for i in range(max_retries):
            try:
                # Build messages array
                messages = []
                if self.system_prompt:
                    messages.append({"role": "system", "content": self.system_prompt})
                messages.append({"role": "user", "content": prompt})

                # Call the API
                chat_completion = self.client.chat.completions.create(
                    model=self.model_name,
                    messages=messages,
                    max_completion_tokens=8192,
                )

                # Track token usage
                if hasattr(chat_completion, "usage") and chat_completion.usage:
                    self.add_token_usage(chat_completion.usage.prompt_tokens, chat_completion.usage.completion_tokens)
                    logger.debug(f"API call {self.api_calls} completed with {chat_completion.usage.prompt_tokens} prompt tokens and {chat_completion.usage.completion_tokens} completion tokens")

                # Return the response
                return chat_completion.choices[0].message.content
            except Exception as e:
                # Log the error and retry
                logger.error(f"Error calling DeepSeek API (attempt {i+1}/{max_retries}): {e}")
                if i < max_retries - 1:
                    logger.info(f"Retrying in {retry_delay} seconds...")
                    time.sleep(retry_delay)
                else:
                    logger.error("Max retries reached. Raising exception.")
                    # If all retries fail, raise an error
                    raise


class QwenModelCalls(ModelCalls):
    """Qwen API call implementation"""

    def __init__(self, api_key, base_url, model_name, system_prompt=None):
        super().__init__(api_key, base_url, model_name)
        self.client = OpenAI(api_key=api_key, base_url=base_url)
        self.system_prompt = system_prompt

    def get_output(self, prompt, max_retries=3, retry_delay=2):
        """
        Get output from Qwen API with retry logic

        Args:
            prompt (str): The user input prompt
            max_retries (int): Maximum number of retry attempts (default: 3)
            retry_delay (int): Delay between retries in seconds (default: 2)

        Returns:
            str: The chat completion response
        """
        for i in range(max_retries):
            try:
                # Build messages array
                messages = []
                if self.system_prompt:
                    messages.append({"role": "system", "content": self.system_prompt})
                messages.append({"role": "user", "content": prompt})

                # Call the API
                chat_completion = self.client.chat.completions.create(
                    model=self.model_name,
                    messages=messages,
                    max_completion_tokens=8192,
                )

                # Track token usage
                if hasattr(chat_completion, "usage") and chat_completion.usage:
                    self.add_token_usage(chat_completion.usage.prompt_tokens, chat_completion.usage.completion_tokens)
                    logger.debug(f"API call {self.api_calls} completed with {chat_completion.usage.prompt_tokens} prompt tokens and {chat_completion.usage.completion_tokens} completion tokens")

                # Return the response
                return chat_completion.choices[0].message.content
            except Exception as e:
                # Log the error and retry
                logger.error(f"Error calling Qwen API (attempt {i+1}/{max_retries}): {e}")
                if i < max_retries - 1:
                    logger.info(f"Retrying in {retry_delay} seconds...")
                    time.sleep(retry_delay)
                else:
                    logger.error("Max retries reached. Raising exception.")
                    # If all retries fail, raise an error
                    raise
