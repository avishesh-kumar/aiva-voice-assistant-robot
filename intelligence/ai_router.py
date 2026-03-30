"""
AI Router (Mac Side)
-------------------

Routes user input to the appropriate LLM backend
(Ollama or Gemini) and returns a clean text response.

This module hides all LLM-specific details from the Brain.

Contract (LOCKED):
- Input: user text, intent, context
- Output: assistant text (str)
- No audio, no networking, no side effects
"""

from typing import Optional
import os
import requests
import re
from utils.logger import get_logger
logger = get_logger("ai", "ai.log")

# Try to import the new google.genai SDK
try:
    from google import genai
    GEMINI_AVAILABLE = True
except Exception:
    GEMINI_AVAILABLE = False

from intelligence.intent_classifier import Intent


class AIRouter:
    """
    Central AI decision router.

    Routing rules:
    - CHAT -> Ollama (fast, conversational)
    - QUESTION -> Gemini (knowledge), fallback to Ollama on failure
    - COMMAND -> no LLM call, return empty string
    """

    def __init__(
        self,
        ollama_url: str = "http://localhost:11434/api/generate",
        ollama_model: str = "llama3.2:latest",
        ollama_fast_model: str = "phi:latest",
        gemini_model: str = "models/gemini-2.5-flash",
        temperature: float = 0.4,
    ):
        self.ollama_url = ollama_url
        self.ollama_model = ollama_model
        self.ollama_fast_model = ollama_fast_model
        self.gemini_model = gemini_model
        self.temperature = temperature
        
        # Continuation memory
        self._last_topic: str = ""
        self._last_ai_response: str = ""
        self._last_intent: Optional[Intent] = None


        # Load system prompt for Ollama (if present)
        self._system_prompt = self._load_system_prompt()
        
        # Create session for Ollama requests (connection reuse)
        self._ollama_session = requests.Session()
        self._ollama_session.headers.update({
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        })

        # Initialize Gemini client lazily (new SDK)
        self._gemini_client = None
        if GEMINI_AVAILABLE:
            try:
                api_key = os.environ.get("GOOGLE_API_KEY")
                if api_key:
                    self._gemini_client = genai.Client(api_key=api_key)
                    logger.info("Gemini READY (primary for QUESTION)")
                else:
                    logger.warning("Gemini API key not found")
            except Exception as e:
                logger.error(f"Gemini client init failed: {repr(e)}")
                self._gemini_client = None
        else:
            logger.warning("Google genai library import failed")

    # ------------------------------------------------------------------
    # Bad Response Detector
    # ------------------------------------------------------------------

    def _is_bad_response(self, text: str) -> bool:
        """
        Detect broken or insufficient model output.
        
        Returns True if:
        - text is empty after strip
        - len(text.strip()) < 4
        - text.strip().lower() in ["t", "ok", "okay"]
        - contains "not applicable as the assistant"
        - ends with ":" AND word_count <= 8 (short intro-only answer)
        """
        if not text:
            return True
            
        stripped = text.strip()
        
        # Empty or too short
        if not stripped or len(stripped) < 4:
            return True
            
        # Count words for the colon check
        word_count = len(stripped.split())
            
        # Single-letter or minimal responses
        stripped_lower = stripped.lower()
        if stripped_lower in ["t", "ok", "okay"]:
            return True
            
        # Contains failure phrases
        failure_phrases = (
            "not applicable as the assistant",
            "as a voice assistant i don't have access",
            "i don't have access to specific",
            "i'm sorry, but as a voice assistant",
            "i cannot access specific",
        )

        if any(p in stripped_lower for p in failure_phrases):
            return True
        
        # Very short response with no punctuation (likely broken)
        if word_count <= 2 and not any(punc in stripped for punc in ".!?,;"):
            return True
            
        # Ends with colon AND has 8 or fewer words (short intro-only answer)
        if stripped.endswith(":") and word_count <= 8:
            return True
            
        return False

    # ------------------------------------------------------------------
    # Hesitation Detector (Emotion-Aware, Text-Only)
    # ------------------------------------------------------------------

    def _user_sounds_uncertain(self, text: str) -> bool:
        """
        Detect hesitation or uncertainty in user speech.
        Purely text-based. No state, no memory.
        """
        if not text:
            return False

        t = text.strip().lower()

        hesitation_markers = (
            "uh",
            "umm",
            "um",
            "hmm",
            "not sure",
            "i think",
            "maybe",
            "kind of",
            "sort of",
        )

        # Direct markers
        if any(marker in t for marker in hesitation_markers):
            return True

        # Very short uncertain inputs
        if len(t.split()) <= 2 and t in {"uh","umm","hmm","maybe"}:
            return True
        return False

    def _soften_response(self, response: str) -> str:
        """
        Slightly soften tone for uncertain users.
        Language-only. No behavior change.
        """
        if not response:
            return response

        soft_prefixes = (
            "No worries. ",
            "That’s okay. ",
            "Let me explain it calmly. ",
        )

        # Avoid double-softening
        lowered = response.lower()
        if lowered.startswith(("no worries", "that's okay", "let me")):
            return response

        return soft_prefixes[0] + response

    # ------------------------------------------------------------------
    # Step Number Extractor
    # ------------------------------------------------------------------

    def _extract_step_number(self, text: str) -> Optional[int]:
        """
        Extract step number from text like "step 1", "step 2", "step one", etc.
        
        Returns:
            int (1-10) if found, else None
        """
        if not text:
            return None
            
        normalized = text.strip().lower()
        
        # Check for exact patterns first
        step_patterns = {
            "step 1": 1, "step one": 1,
            "step 2": 2, "step two": 2,
            "step 3": 3, "step three": 3,
            "step 4": 4, "step four": 4,
            "step 5": 5, "step five": 5,
            "step 6": 6, "step six": 6,
            "step 7": 7, "step seven": 7,
            "step 8": 8, "step eight": 8,
            "step 9": 9, "step nine": 9,
            "step 10": 10, "step ten": 10,
        }
        
        # Check for exact matches
        if normalized in step_patterns:
            return step_patterns[normalized]
        
        # Check for patterns like "step 1", "step 2" etc (with optional extra text)
        step_regex = r'^step\s+(\d+|[a-z]+)'
        match = re.match(step_regex, normalized)
        
        if match:
            step_str = match.group(1).strip()
            
            # If it's a digit
            if step_str.isdigit():
                step_num = int(step_str)
                if 1 <= step_num <= 10:
                    return step_num
            
            # If it's a word
            word_to_num = {
                "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
                "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10
            }
            
            if step_str in word_to_num:
                return word_to_num[step_str]
        
        return None

    # ------------------------------------------------------------------
    # More Request Helpers
    # ------------------------------------------------------------------

    def _is_more_request(self, text: str) -> bool:
        """
        Detect if the user is asking for more information on a topic.
        """
        if not text:
            return False
            
        text_lower = text.strip().lower()
        more_indicators = [
            "more",
            "tell me more", 
            "explain more",
            "in detail",
            "elaborate",
            "continue",
            "go on",
            "expand"
        ]
        
        for indicator in more_indicators:
            if indicator in text_lower:
                return True
                
        return False

    def _extract_more_topic(self, text: str) -> str:
        """
        Extract the topic from a "more" request.
        Returns empty string if no specific topic found.
        """
        if not text:
            return ""
            
        text_lower = text.strip().lower()
        
        # Patterns to look for
        patterns = [
            ("more about", 2),
            ("more on", 2),
            ("tell me more about", 4),
            ("explain more about", 4),
            ("in detail about", 3),
            ("more information about", 4),
        ]
        
        for pattern, word_count in patterns:
            if pattern in text_lower:
                # Extract everything after the pattern
                start_idx = text_lower.find(pattern) + len(pattern)
                topic = text_lower[start_idx:].strip()
                
                # Remove trailing question marks and common words
                topic = topic.rstrip("?.")
                topic = topic.lstrip("the ").lstrip("a ").lstrip("an ")
                
                # If topic is just generic words, return empty
                generic_words = ["it", "this", "that", "the", "topic", "subject"]
                if topic in generic_words or len(topic.split()) <= word_count:
                    return ""
                    
                return topic
                
        # Check for "more" followed by a topic (like "more cats")
        if text_lower.startswith("more "):
            words = text_lower.split()
            if len(words) > 1:
                topic = " ".join(words[1:]).rstrip("?.")
                generic_words = ["it", "this", "that", "the", "topic", "subject", "please"]
                if topic not in generic_words and len(topic.split()) <= 5:
                    return topic
                    
        return ""

    # ------------------------------------------------------------------
    # Response Cleaner
    # ------------------------------------------------------------------

    def _clean_response(self, text: str) -> str:
        """
        Clean unwanted patterns from AI response.
        
        Removes:
        - Unwanted introductory phrases
        - Multi-line responses (keeps only first line)
        - Trailing unmatched quotes
        - "User A:" style artifacts
        """
        if not text:
            return ""
            
        # Strip whitespace first
        text = text.strip()
        if not text:
            return ""

        # 🚨 Remove assistant self-introductions at start
        prefix_patterns = [
            r"^(hi[, ]*)?i'?m ava[, ]*",
            r"^(hi[, ]*)?this is ava[, ]*",
            r"^ava here[, ]*",
        ]

        for pattern in prefix_patterns:
            text = re.sub(pattern, "", text, flags=re.IGNORECASE).strip()

            
        # But normalize excessive newlines
        text = re.sub(r"\n{3,}", "\n\n", text).strip()

        # Remove dialogue-style speaker labels
        lines = text.split('\n')
        cleaned_lines = []

        for line in lines:
            stripped = line.strip()

            # Remove lines that start with USER:, AI:, Assistant:
            if re.match(r'^(user|assistant|ai)\s*:', stripped, re.IGNORECASE):
                continue

            cleaned_lines.append(line)

        text = '\n'.join(cleaned_lines)

        # Also remove inline prefixes like "User: ..." or "AI: ..."
        text = re.sub(r'\b(User|AI|Assistant)\s*:\s*', '', text, flags=re.IGNORECASE)

            
        # Convert to lowercase for pattern matching
        text_lower = text.lower()
        
        # Remove content starting from unwanted phrases
        unwanted_phrases = [
            "in the conversation above",
            "consider the following",
            "as an ai",
            "i am an ai",
            "as a voice assistant",
            "ava is a voice assistant",
            "as ava",
            "i am ava",
            "i'm ava",
            "here is",
            "scenario:",
        ]
        
        for phrase in unwanted_phrases:
            if phrase in text_lower:
                # Find the position and cut everything from that point
                pos = text_lower.find(phrase)
                if pos != -1:
                    text = text[:pos].strip()
                    break  # Only remove from the first found phrase
                    
        # Remove trailing unmatched quotes
        if text.startswith('"') and not text.endswith('"'):
            text = text[1:].strip()
        elif text.endswith('"') and not text.startswith('"'):
            text = text[:-1].strip()
            
        return text.strip()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate_response(
        self,
        user_text: str,
        intent: Intent,
        context: Optional[str] = None,
    ) -> str:
        """
        Generate an AI response for the given user input.
        """

        if not user_text:
            return ""

        # Preserve raw input
        original_user_text = user_text.strip()
        normalized_input = original_user_text.lower()

        # Simple greeting shortcut
        if normalized_input in {"hi", "hello", "hey", "hey ava", "hello ava"}:
            return "Hi! How can I help?"

        # --------------------------------------------------
        # SMART CONTINUATION MEMORY
        # --------------------------------------------------

        continuation_triggers = (
            "continue",
            "go on",
            "keep going",
            "continue this",
            "yes continue",
            "yeah continue",
            "tell me more",
            "more",
        )

        is_continuation = normalized_input.strip() in {
            "continue",
            "go on",
            "keep going",
            "yes continue",
            "more",
            "tell me more",
        }

        if is_continuation:
            if self._last_topic:
                user_text = f"Continue explaining in detail: {self._last_topic}"
            elif self._last_ai_response:
                user_text = f"Continue this explanation: {self._last_ai_response}"
            intent = Intent.QUESTION

        # --------------------------------------------------
        # Sentence completion heuristic
        # --------------------------------------------------

        completion_triggers = (
            "complete this sentence",
            "finish this sentence",
            "complete the sentence",
            "finish the sentence",
        )

        if any(t in normalized_input for t in completion_triggers):
            return "Please provide the sentence you want me to complete."

        # --------------------------------------------------
        # COMMAND → No LLM call
        # --------------------------------------------------

        if intent == Intent.COMMAND:
            return ""

        response = ""
        is_more_request = False

        # --------------------------------------------------
        # STEP NUMBER HANDLING
        # --------------------------------------------------

        step_num = self._extract_step_number(original_user_text)

        if step_num is not None:
            intent = Intent.QUESTION
            if self._last_topic:
                user_text = f"Explain Step {step_num} of: {self._last_topic}"
            else:
                user_text = f"Explain Step {step_num} clearly."

        else:
            # --------------------------------------------------
            # "More" request detection
            # --------------------------------------------------
            if not is_continuation and self._is_more_request(original_user_text):
                is_more_request = True

                extracted_topic = self._extract_more_topic(original_user_text)

                if extracted_topic:
                    user_text = f"Explain in more detail about: {extracted_topic}"
                elif self._last_topic:
                    user_text = f"Explain in more detail about: {self._last_topic}"

        # --------------------------------------------------
        # Topic memory update
        # --------------------------------------------------

        if (
            not is_more_request
            and not is_continuation
            and step_num is None
            and intent in (Intent.QUESTION, Intent.CHAT)
            and len(original_user_text.split()) >= 3
        ):
            self._last_topic = original_user_text.strip()

        # --------------------------------------------------
        # Routing
        # --------------------------------------------------

        if intent == Intent.CHAT:
            response = self._call_ollama_with_retry(user_text, intent, context)
            if not response or self._is_bad_response(response):
                response = "I didn't catch that. Please repeat."

        elif intent == Intent.QUESTION:
            response = self._call_gemini(user_text, intent, context)
            if response:
                response = self._clean_response(response)

            if not response or self._is_bad_response(response):
                ollama_response = self._call_ollama_with_retry(
                    user_text, intent, context
                )
                if ollama_response and not self._is_bad_response(ollama_response):
                    response = self._clean_response(ollama_response)
                else:
                    response = "I didn't catch that. Please repeat."

        # --------------------------------------------------
        # Emotion-aware softening
        # --------------------------------------------------

        if self._user_sounds_uncertain(original_user_text):
            response = self._soften_response(response)

        final_response = response.strip() if response else ""

        # Save last AI response for continuation
        if final_response:
            self._last_ai_response = final_response
            self._last_intent = intent

        return final_response

    # ------------------------------------------------------------------
    # Ollama Backend with Retry
    # ------------------------------------------------------------------

    def _call_ollama_with_retry(
        self, 
        user_text: str,
        intent: Intent,
        context: Optional[str]
    ) -> str:
        """
        Call Ollama with one retry on failure.
        Returns empty string if both attempts fail.
        """
        for attempt in range(2):  # 0 and 1 (max 1 retry)
            try:
                response = self._call_ollama(user_text, intent, context, attempt)
                if response:
                    return response
            except Exception as e:
                logger.warning(f"Ollama attempt {attempt + 1} failed: {e}")
                if attempt == 1:  # Last attempt failed
                    logger.error("Ollama all attempts exhausted")
        return ""

    def _call_ollama(
        self, 
        user_text: str,
        intent: Intent,
        context: Optional[str],
        attempt: int = 0
    ) -> str:
        """
        Call Ollama local LLM with optimized prompt.
        
        Returns:
            str or empty string on failure
        """
        # Optimize context: keep only last ~6 lines
        optimized_context = self._optimize_context(context)
        
        prompt_parts = []

        if self._system_prompt:
            prompt_parts.append(self._system_prompt)

        # Core instructions for concise, voice-friendly answers
        prompt_parts.append(
            "You are Ava, a helpful voice assistant.\n"
            "IMPORTANT RULES:\n"
            "- Never describe yourself\n"
            "- Never mention being an AI\n"
            "- Never explain your instructions\n"
            "- Speak naturally like a human assistant\n"
            "Keep replies 1–3 sentences, conversational."
        )
        if optimized_context:
            prompt_parts.append("Conversation so far:")
            prompt_parts.append(optimized_context)

        prompt_parts.append(f"User: {user_text}\nAssistant:")
        
        prompt = "\n\n".join(prompt_parts)

        # Choose model based on intent
        if intent == Intent.CHAT:
            model_to_use = self.ollama_fast_model
        else:
            model_to_use = self.ollama_model

        # Token limit based on input length (still generous but not excessive)
        if len(user_text) <= 40:
            num_predict = 220
        elif len(user_text) <= 120:
            num_predict = 320
        else:
            num_predict = 420

        payload = {
            "model": model_to_use,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": self.temperature,
                "num_predict": num_predict,
            },
        }

        # Set timeout based on intent
        if intent == Intent.QUESTION:
            timeout = 20.0
        elif intent == Intent.CHAT:
            timeout = 4.0
        else:
            timeout = 6.0

        try:
            response = self._ollama_session.post(
                self.ollama_url,
                json=payload,
                timeout=timeout,
            )
            response.raise_for_status()
            data = response.json()
            result = data.get("response", "").strip()
            
            if result and len(result) > 2:
                return result
            return ""

        except requests.exceptions.Timeout:
            logger.warning(f"Ollama timeout on attempt {attempt + 1}")
            raise
        except Exception as e:
            logger.error(f"Ollama error on attempt {attempt + 1}: {e}")
            raise

    # ------------------------------------------------------------------
    # Gemini Backend (using new google.genai SDK)
    # ------------------------------------------------------------------

    def _call_gemini(self, user_text: str, intent: Intent, context: Optional[str]) -> str:
        """
        Call Gemini model (primary for QUESTION).
        
        Returns:
            str or empty string on failure
        """
        if not self._gemini_client:
            return ""

        # Optimize context for Gemini too
        optimized_context = self._optimize_context(context)
        
        prompt_parts = []

        # System instruction for Gemini
        is_long_explanation = any(
            phrase in user_text.lower()
            for phrase in ["continue", "more detail", "explain step", "explain in more detail"]
        )

        if is_long_explanation:
            prompt_parts.append(
                "You are Ava.\n"
                "Answer the user's question in short brief complete senstence.\n"
                "Write some polite and encouraging dialogues at the starting of the answer.\n"
                "Do NOT include 'User:' or 'AI:' in your response.\n"
                "Give only the answer.\n"
            )

        else:
            prompt_parts.append(
            "You are Ava.\n"
            "Answer the user's question directly in brief.\n"
            "Do NOT include 'User:' or 'AI:' in your response.\n"
            "Give only the answer.\n"
        )
            
        if optimized_context:
            prompt_parts.append("Previous conversation context (for reference only):")
            prompt_parts.append(optimized_context)


        prompt_parts.append(user_text)
        
        prompt = "\n\n".join(prompt_parts)

        try:
            max_tokens = 220

            response = self._gemini_client.models.generate_content(
                model=self.gemini_model,
                contents=prompt,
                config={
                    "temperature": self.temperature,
                    "max_output_tokens": max_tokens,
                }
            )
            
            # Extract text from response (defensive handling)
            result = ""
            
            txt = getattr(response, "text", None)
            if isinstance(txt, str) and txt.strip():
                result = txt.strip()
            
            # Fallback to candidates parsing if text is empty
            if not result:
                cands = getattr(response, "candidates", None)
                if isinstance(cands, list) and len(cands) > 0:
                    candidate = cands[0]
                    content = getattr(candidate, "content", None)
                    parts = getattr(content, "parts", None)
                    if isinstance(parts, list):
                        text_parts = []
                        for part in parts:
                            part_text = getattr(part, 'text', '')
                            if isinstance(part_text, str) and part_text.strip():
                                text_parts.append(part_text.strip())
                        if text_parts:
                            result = ' '.join(text_parts).strip()
            
            return result if result else ""

        except Exception as e:
            logger.error(f"Gemini error: {e}")
            return ""

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

    def _optimize_context(self, context: Optional[str]) -> Optional[str]:
        """
        Reduce context size by keeping only last ~6 lines.
        Prevents prompt bloat and improves performance.
        """
        if not context:
            return None
            
        lines = context.strip().split('\n')
        if len(lines) <= 6:
            return context.strip()
            
        # Keep last 6 non-empty lines
        recent_lines = []
        for line in reversed(lines):
            if line.strip():
                recent_lines.append(line.strip())
                if len(recent_lines) >= 6:
                    break
                    
        return '\n'.join(recent_lines)

    def _load_system_prompt(self) -> str:
        """
        Load Ollama system prompt from file if available.

        Expected path:
        ai_models/ollama/system_prompt.txt
        """
        try:
            from pathlib import Path

            path = Path(__file__).parents[1] / "ai_models" / "ollama" / "system_prompt.txt"
            if path.exists():
                return path.read_text().strip()
        except Exception:
            pass

        return ""
