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
                max_tokens=350  # Уменьшили количество токенов для короткого текста
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
                max_tokens=200
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
        system_prompt = """Ты профессиональный копирайтер для коротких сценариев. 
Напиши текст для озвучки видео длиной 50 слов. 
Текст должен быть:
1. Лаконичным и понятным
2. Соответствовать стилю и теме
3. Легко восприниматься на слух
4. Быть естественным и увлекательным
и обязатльно должен быть ТОЛЬКО текст озвучки, без эмодзи, без ковычек и вводных слов по типу "Голос за кадром ..." """
        
        if profile_info:
            system_prompt += f"\n\nУчитывай профиль автора:\n{self._format_profile(profile_info)}"
        
        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt}
        ]

    def _build_improvement_prompt(
        self, 
        profile_info: Optional[Dict[str, Any]]
    ) -> str:
        prompt = "Улучши этот текст для озвучки, сохранив основную идею. Длина должна остаться 50 слов."
        if profile_info:
            prompt += f"\n\nУчитывай профиль автора:\n{self._format_profile(profile_info)}"
        return prompt

    def _format_profile(self, profile_info: Dict[str, Any]) -> str:
        return "\n".join(
            f"{key}: {value}" 
            for key, value in profile_info.items() 
            if value
        )

gpt_service = GPTService()