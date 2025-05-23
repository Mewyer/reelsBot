import openai
from openai import AsyncOpenAI, APIError
from config import config
from typing import Optional, Dict, Any
import logging
import backoff

logger = logging.getLogger(__name__)

class GPTService:
    def __init__(self):
        self.client = AsyncOpenAI(
            api_key=config.OPENAI_API_KEY,
            base_url=config.OPENAI_BASE_URL,
            timeout=config.REQUEST_TIMEOUT
        )
        self.model = config.GPT_MODEL

    @backoff.on_exception(
        backoff.expo,
        (APIError, Exception),
        max_tries=3,
        logger=logger
    )
    async def generate_script(
        self, 
        prompt: str, 
        profile_info: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Generate video script using OpenAI API with retry logic
        """
        messages = self._build_messages(prompt, profile_info)
        
        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=0.7,
                max_tokens=1000
            )
            return response.choices[0].message.content
        except APIError as e:
            logger.error(f"OpenAI API error: {e}")
            raise Exception(f"OpenAI API error: {e}")
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            raise Exception(f"Script generation failed: {e}")

    async def improve_script(
        self,
        script: str,
        feedback: str,
        profile_info: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Improve existing script based on feedback
        """
        messages = [
            {
                "role": "system",
                "content": self._build_improvement_prompt(profile_info)
            },
            {
                "role": "user",
                "content": f"Current script:\n{script}\n\nFeedback:\n{feedback}"
            }
        ]
        
        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=0.5,
                max_tokens=1000
            )
            return response.choices[0].message.content
        except Exception as e:
            logger.error(f"Script improvement failed: {e}")
            raise Exception(f"Script improvement failed: {e}")

    def _build_messages(
        self,
        prompt: str,
        profile_info: Optional[Dict[str, Any]]
    ) -> list[Dict[str, str]]:
        system_prompt = """You are a professional scriptwriter for short videos (Reels/TikTok).
Create dynamic, engaging scripts (30-60 seconds) with:
1. Visual description
2. Voiceover text
3. Editing recommendations"""
        
        if profile_info:
            system_prompt += f"\n\nUser profile:\n{self._format_profile(profile_info)}"
        
        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt}
        ]

    def _build_improvement_prompt(
        self, 
        profile_info: Optional[Dict[str, Any]]
    ) -> str:
        prompt = "Improve this script based on feedback while maintaining original intent."
        if profile_info:
            prompt += f"\n\nConsider user profile:\n{self._format_profile(profile_info)}"
        return prompt

    def _format_profile(self, profile_info: Dict[str, Any]) -> str:
        return "\n".join(
            f"{key}: {value}" 
            for key, value in profile_info.items() 
            if value
        )

gpt_service = GPTService()