from groq import Groq
from backend.config import GROQ_MODEL, get_groq_api_key, get_groq_model, sanitize_db_error
import os
import json
from typing import List, Dict, Any

class LLMClient:
    def __init__(self, api_key: str = None):
        if not api_key:
            api_key = get_groq_api_key()
        self.api_key = api_key
        self.model = get_groq_model() or GROQ_MODEL
        if self.api_key:
            self.client = Groq(api_key=self.api_key)
        else:
            self.client = None
            
    def set_api_key(self, api_key: str):
        self.api_key = api_key
        self.client = Groq(api_key=self.api_key)
        
    def chat(self, messages: List[Dict[str, Any]], tools: List[Dict[str, Any]] = None, tool_choice: str = "auto") -> Dict[str, Any]:
        if not self.client:
            raise RuntimeError(
                "GROQ_API_KEY is not configured. Add GROQ_API_KEY to .streamlit/secrets.toml (local) "
                "or Streamlit Community Cloud -> App Settings -> Secrets (cloud)."
            )
            
        kwargs = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.1,
            "timeout": 30
        }
        
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = tool_choice
            
        try:
            response = self.client.chat.completions.create(**kwargs)
            message = response.choices[0].message
            parsed_tool_calls = None
            if message.tool_calls:
                parsed_tool_calls = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments
                        }
                    }
                    for tc in message.tool_calls
                ]
            
            result = {
                "role": message.role,
                "content": message.content
            }
            if parsed_tool_calls:
                result["tool_calls"] = parsed_tool_calls
            return result
        except Exception as e:
            # Check for Groq's tool_use_failed recovery
            failed_gen_str = None
            if hasattr(e, "body") and isinstance(e.body, dict):
                err_dict = e.body.get("error", {})
                if isinstance(err_dict, dict):
                    failed_gen_str = err_dict.get("failed_generation")
            
            if not failed_gen_str and "failed_generation" in str(e):
                import re
                match = re.search(r"['\"]failed_generation['\"]\s*:\s*['\"](\{.*?\})['\"]", str(e), re.DOTALL)
                if match:
                    try:
                        raw_escaped = match.group(1)
                        clean_str = raw_escaped.replace('\\n', '\n').replace('\\"', '"').replace('\\\\', '\\')
                        failed_gen_str = clean_str
                    except Exception:
                        pass
                        
            if failed_gen_str:
                try:
                    tool_call = json.loads(failed_gen_str)
                    if "name" in tool_call:
                        return {
                            "role": "assistant",
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": "recovered_call_1",
                                    "type": "function",
                                    "function": {
                                        "name": tool_call.get("name"),
                                        "arguments": json.dumps(tool_call.get("arguments", {}))
                                    }
                                }
                            ]
                        }
                except Exception:
                    pass
                    
            raise Exception(f"LLM API Error: {sanitize_db_error(e)}")
            
    def generate_json(self, messages: List[Dict[str, Any]], response_format={"type": "json_object"}) -> dict:
        if not self.client:
            raise RuntimeError(
                "GROQ_API_KEY is not configured. Add GROQ_API_KEY to .streamlit/secrets.toml (local) "
                "or Streamlit Community Cloud -> App Settings -> Secrets (cloud)."
            )
            
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=0.1,
                response_format=response_format,
                timeout=30
            )
            return json.loads(response.choices[0].message.content)
        except Exception as e:
            raise Exception(f"LLM API Error: {sanitize_db_error(e)}")
