import os
import json
import hashlib
from datetime import datetime
from loguru import logger
from openai import OpenAI
from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert

from src.data.store import DataStore, LLMCache

class LLMClient:
    def __init__(self, store: DataStore, model: str = "gpt-5-mini", temperature: float = 1.0):
        self.store = store
        self.db = store.get_session()
        self.model = model
        self.temperature = temperature
        
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            logger.warning("OPENAI_API_KEY not found in environment. LLM calls will fail if not cached.")
            self.client = None
        else:
            self.client = OpenAI(api_key=api_key)

    def _get_cache_key(self, role: str, input_json: str, prompt_version: str) -> str:
        # Key = hash(role + model + input + prompt_version)
        raw = f"{role}:{self.model}:{input_json}:{prompt_version}"
        return hashlib.sha256(raw.encode('utf-8')).hexdigest()

    def get_cached_response(self, cache_key: str) -> dict | None:
        stmt = select(LLMCache).where(LLMCache.cache_key == cache_key)
        row = self.db.execute(stmt).scalar_one_or_none()
        if row:
            try:
                return json.loads(row.output_json)
            except:
                return None
        return None

    def save_cache(self, cache_key: str, role: str, input_json: str, output_json: str, status: str):
        record = {
            'cache_key': cache_key,
            'role': role,
            'input_json': input_json,
            'output_json': output_json,
            'validation_status': status,
            'created_at': datetime.utcnow().isoformat()
        }
        stmt = insert(LLMCache).values(record)
        stmt = stmt.on_conflict_do_update(
            index_elements=['cache_key'],
            set_={
                'output_json': stmt.excluded.output_json,
                'validation_status': stmt.excluded.validation_status,
                'created_at': stmt.excluded.created_at
            }
        )
        self.db.execute(stmt)
        self.db.commit()

    def call_completion(self, 
                        role: str, 
                        system_prompt: str, 
                        user_prompt: str, 
                        input_data: dict, 
                        response_format = None,
                        prompt_version: str = "v1") -> dict | None:
        
        input_json = json.dumps(input_data, sort_keys=True)
        cache_key = self._get_cache_key(role, input_json, prompt_version)
        
        # Check cache
        cached = self.get_cached_response(cache_key)
        if cached:
            logger.info(f"LLM Cache Hit for {role}")
            return cached

        if not self.client:
            logger.error("OpenAI client not initialized. Cannot call LLM.")
            return None

        try:
            logger.info(f"Calling OpenAI {self.model} for {role}...")
            
            # OpenAI beta features for structured output if supported, or just JSON mode
            # Use JSON mode via response_format={"type": "json_object"}
            
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ]
            
            create_kwargs = {
                "model": self.model,
                "messages": messages,
                "response_format": response_format if response_format else {"type": "json_object"},
            }

            if not self.model.startswith("gpt-5"):
                create_kwargs["temperature"] = self.temperature

            completion = self.client.chat.completions.create(**create_kwargs)
            
            content = completion.choices[0].message.content
            if not content:
                logger.error("Empty response from LLM")
                return None
                
            parsed = json.loads(content)
            
            # Save to cache (status='raw' until validated by service)
            self.save_cache(cache_key, role, input_json, content, "raw")
            
            return parsed

        except Exception as e:
            logger.error(f"LLM Call failed: {e}")
            return None
