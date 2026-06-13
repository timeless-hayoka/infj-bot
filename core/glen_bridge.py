"""GLEN: Gradient-optimized Low-bit Emulation Network

A fast, local inference bridge using bitsandbytes and PEFT for 4-bit quantization.
Designed specifically for high-speed local inference in DRIFT Fast Mode.
"""

import os
from typing import List, Dict, Optional, Generator, Any
import torch

from drift.core.local_llm import BaseLocalBridge

try:
    from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
except ImportError:
    AutoModelForCausalLM = None
    AutoTokenizer = None
    BitsAndBytesConfig = None

class GLENBridge(BaseLocalBridge):
    def __init__(self, model_name: str = "unsloth/Qwen2.5-1.5B-Instruct"):
        """Initialize the GLEN bridge with 4-bit quantization."""
        self.model_name = model_name
        self.model = None
        self.tokenizer = None
        self.device = "cuda" if torch.cuda.is_available() else "cpu"

    def is_available(self) -> bool:
        if AutoModelForCausalLM is None:
            return False
        return True

    def list_models(self) -> List[str]:
        if not self.is_available():
            return []
        return [self.model_name]

    def _load_model(self):
        """Lazy load the model to save RAM until actually used."""
        if self.model is not None:
            return

        if not self.is_available():
            raise RuntimeError("transformers, bitsandbytes, or peft not installed. GLEN is offline.")

        print(f"Loading GLEN model ({self.model_name}) in 4-bit mode...")
        quantization_config = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_compute_dtype=torch.float16,
            bnb_4bit_use_double_quant=True,
            bnb_4bit_quant_type="nf4"
        )
        
        self.tokenizer = AutoTokenizer.from_pretrained(self.model_name)
        self.model = AutoModelForCausalLM.from_pretrained(
            self.model_name,
            quantization_config=quantization_config,
            device_map="auto"
        )
        print("GLEN 4-bit model loaded successfully.")

    def _format_messages(self, messages: List[Dict[str, str]], system: Optional[str] = None) -> str:
        """Format the conversational messages into a single prompt string."""
        prompt = ""
        if system:
            prompt += f"<|im_start|>system\n{system}<|im_end|>\n"
            
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            prompt += f"<|im_start|>{role}\n{content}<|im_end|>\n"
            
        prompt += "<|im_start|>assistant\n"
        return prompt

    def chat(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        system: Optional[str] = None,
        stream: bool = False,
        temperature: float = 0.7,
    ) -> str:
        """Synchronous chat completion."""
        self._load_model()
        prompt = self._format_messages(messages, system)
        
        inputs = self.tokenizer(prompt, return_tensors="pt").to(self.device)
        
        with torch.no_grad():
            outputs = self.model.generate(
                **inputs,
                max_new_tokens=256,
                temperature=temperature,
                do_sample=temperature > 0,
                pad_token_id=self.tokenizer.eos_token_id
            )
            
        response = self.tokenizer.decode(outputs[0][inputs.input_ids.shape[1]:], skip_special_tokens=True)
        return response

    def chat_stream(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        system: Optional[str] = None,
        temperature: float = 0.7,
    ) -> Generator[str, None, None]:
        """Streaming chat completion using TextIteratorStreamer."""
        from transformers import TextIteratorStreamer
        from threading import Thread

        self._load_model()
        prompt = self._format_messages(messages, system)
        inputs = self.tokenizer(prompt, return_tensors="pt").to(self.device)
        
        streamer = TextIteratorStreamer(self.tokenizer, skip_prompt=True, skip_special_tokens=True)
        
        generation_kwargs = dict(
            **inputs,
            streamer=streamer,
            max_new_tokens=256,
            temperature=temperature,
            do_sample=temperature > 0,
            pad_token_id=self.tokenizer.eos_token_id
        )
        
        thread = Thread(target=self.model.generate, kwargs=generation_kwargs)
        thread.start()
        
        for new_text in streamer:
            yield new_text

    def generate(
        self,
        prompt: str,
        model: Optional[str] = None,
        system: Optional[str] = None,
        stream: bool = False,
        temperature: float = 0.7,
        **kwargs: Any,
    ) -> str:
        """Raw generate completion."""
        self._load_model()
        full_prompt = ""
        if system:
            full_prompt += f"<|im_start|>system\n{system}<|im_end|>\n"
        full_prompt += f"<|im_start|>user\n{prompt}<|im_end|>\n<|im_start|>assistant\n"
        
        inputs = self.tokenizer(full_prompt, return_tensors="pt").to(self.device)
        
        max_tok = kwargs.get("max_tokens") or kwargs.get("max_output_tokens") or 256
        
        with torch.no_grad():
            outputs = self.model.generate(
                **inputs,
                max_new_tokens=int(max_tok),
                temperature=temperature,
                do_sample=temperature > 0,
                pad_token_id=self.tokenizer.eos_token_id
            )
            
        response = self.tokenizer.decode(outputs[0][inputs.input_ids.shape[1]:], skip_special_tokens=True)
        return response

    def generate_stream(
        self,
        prompt: str,
        model: Optional[str] = None,
        system: Optional[str] = None,
        temperature: float = 0.7,
        **kwargs: Any,
    ) -> Generator[str, None, None]:
        """Streaming generate completion."""
        from transformers import TextIteratorStreamer
        from threading import Thread

        self._load_model()
        full_prompt = ""
        if system:
            full_prompt += f"<|im_start|>system\n{system}<|im_end|>\n"
        full_prompt += f"<|im_start|>user\n{prompt}<|im_end|>\n<|im_start|>assistant\n"
        
        inputs = self.tokenizer(full_prompt, return_tensors="pt").to(self.device)
        
        streamer = TextIteratorStreamer(self.tokenizer, skip_prompt=True, skip_special_tokens=True)
        
        max_tok = kwargs.get("max_tokens") or kwargs.get("max_output_tokens") or 256
        
        generation_kwargs = dict(
            **inputs,
            streamer=streamer,
            max_new_tokens=int(max_tok),
            temperature=temperature,
            do_sample=temperature > 0,
            pad_token_id=self.tokenizer.eos_token_id
        )
        
        thread = Thread(target=self.model.generate, kwargs=generation_kwargs)
        thread.start()
        
        for new_text in streamer:
            yield new_text
