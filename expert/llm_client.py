# # expert/llm_client.py
# import os
# import json
# import logging
# from typing import List, Dict, Any, Optional
#
# logger = logging.getLogger(__name__)
#
#
# class LLMClient:
#     """
#     Client LLM unifiÃ©.
#     - PrioritÃ© : Groq (si GROQ_API_KEY prÃ©sent)
#     - Fallback : OpenAI (si OPENAI_API_KEY prÃ©sent)
#     - Deux helpers: chat_json() et chat_text()
#     """
#
#     def __init__(self, model: Optional[str] = None, temperature: float = 0.2):
#         # Provider auto: groq > openai
#         self.provider = (
#             os.getenv("LLM_PROVIDER")  # optionnel: forcer "groq" ou "openai"
#             or ("groq" if os.getenv("GROQ_API_KEY") else None)
#             or ("openai" if os.getenv("OPENAI_API_KEY") else None)
#         )
#
#         # ModÃ¨le par dÃ©faut: Groq Llama 3.3 70B versatile
#         self.model = model or os.getenv("LLM_MODEL", "llama-3.3-70b-versatile")
#         self.temperature = float(os.getenv("LLM_TEMPERATURE", temperature or 0.2))
#         self.enabled = os.getenv("ENABLE_LLM", "1") == "1" and self.provider is not None
#
#         self._client = None  # SDK client lazy
#         logger.info("LLMClient initialized provider=%s model=%s enabled=%s",
#                     self.provider, self.model, self.enabled)
#
#     # -------------------- Public API --------------------
#
#     def chat_json(self, messages: List[Dict[str, Any]], max_tokens: int = 3000) -> Optional[Dict[str, Any]]:
#         """
#         Demande un **objet JSON**. Si le provider ne force pas le JSON, on
#         tente un json.loads() avec fallback dâ€™extraction.
#         """
#         if not self.enabled:
#             return None
#
#         try:
#             if self.provider == "groq":
#                 from groq import Groq
#                 client = self._client or Groq()
#                 self._client = client
#
#                 resp = client.chat.completions.create(
#                     model=self.model,
#                     temperature=self.temperature,
#                     max_tokens=max_tokens,
#                     # Groq est compatible OpenAI: JSON mode
#                     response_format={"type": "json_object"},
#                     messages=messages,
#                 )
#                 content = (resp.choices[0].message.content or "{}").strip()
#
#             elif self.provider == "openai":
#                 from openai import OpenAI
#                 client = self._client or OpenAI()
#                 self._client = client
#
#                 resp = client.chat.completions.create(
#                     model=self.model,
#                     temperature=self.temperature,
#                     max_tokens=max_tokens,
#                     response_format={"type": "json_object"},
#                     messages=messages,
#                 )
#                 content = (resp.choices[0].message.content or "{}").strip()
#
#             else:
#                 logger.error("No supported provider configured")
#                 return None
#
#             # Tente JSON direct
#             try:
#                 return json.loads(content)
#             except Exception:
#                 # Fallback: extraire un bloc JSON dâ€™un texte
#                 extracted = self._extract_json_block(content)
#                 return json.loads(extracted) if extracted else None
#
#         except Exception as e:
#             logger.exception("LLM chat_json failed: %s", e)
#             return None
#
#     def chat_text(self, messages: List[Dict[str, Any]], max_tokens: int = 1000) -> Optional[str]:
#         """RÃ©ponse texte libre."""
#         if not self.enabled:
#             return None
#
#         try:
#             if self.provider == "groq":
#                 from groq import Groq
#                 client = self._client or Groq()
#                 self._client = client
#
#                 resp = client.chat.completions.create(
#                     model=self.model,
#                     temperature=self.temperature,
#                     max_tokens=max_tokens,
#                     messages=messages,
#                 )
#                 return (resp.choices[0].message.content or "").strip()
#
#             elif self.provider == "openai":
#                 from openai import OpenAI
#                 client = self._client or OpenAI()
#                 self._client = client
#
#                 resp = client.chat.completions.create(
#                     model=self.model,
#                     temperature=self.temperature,
#                     max_tokens=max_tokens,
#                     messages=messages,
#                 )
#                 return (resp.choices[0].message.content or "").strip()
#
#             else:
#                 logger.error("No supported provider configured")
#                 return None
#
#         except Exception as e:
#             logger.exception("LLM chat_text failed: %s", e)
#             return None
#
#     # -------------------- Utils --------------------
#
#     @staticmethod
#     def _extract_json_block(text: str) -> Optional[str]:
#         """
#         Tente d'extraire un objet JSON depuis du texte (ex: ```json {...} ```).
#         Retourne une chaÃ®ne JSON ou None.
#         """
#         if not text:
#             return None
#
#         # Strip fences ```json ... ``` ou ``` ...
#         fences = ("```json", "```")
#         for f in fences:
#             if f in text:
#                 try:
#                     chunk = text.split(f, 1)[1]
#                     chunk = chunk.split("```", 1)[0]
#                     chunk = chunk.strip()
#                     if chunk.startswith("{") and chunk.endswith("}"):
#                         return chunk
#                 except Exception:
#                     pass
#
#         # Recherche naÃ¯ve du 1er bloc {...}
#         start = text.find("{")
#         end = text.rfind("}")
#         if 0 <= start < end:
#             candidate = text[start:end + 1].strip()
#             if candidate:
#                 return candidate
#         return None
#
# ##########

# expert/llm_client.py
# -*- coding: utf-8 -*-
import os
import re
import json
import time
import math
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Tuple

logger = logging.getLogger(__name__)

# Mémoire de process : fenêtre de rate-limit par provider
_RATE_LIMIT_UNTIL: Dict[str, float] = {}  # {"groq": epoch_seconds, "openai": epoch_seconds}


def _now_ts() -> float:
    return time.time()


def _is_rate_limited(provider: str) -> bool:
    until = _RATE_LIMIT_UNTIL.get(provider, 0.0)
    return _now_ts() < until


def _remember_rate_limit(provider: str, seconds: float) -> None:
    seconds = max(5.0, float(seconds))  # garde un minimum
    until = _now_ts() + seconds
    _RATE_LIMIT_UNTIL[provider] = until
    dt_until = datetime.fromtimestamp(until)
    logger.warning("Rate limit cached until %s for provider=%s", dt_until, provider)


def _parse_retry_after_seconds(msg: str) -> float:
    """
    Exemples rencontrés dans vos logs :
      "Please try again in 18m17.498s."
      "Please try again in 19m14.390999999s."
    On accepte aussi "... in 42s."
    """
    if not msg:
        return 60.0
    # 18m17.498s
    m = re.search(r'(\d+)m(\d+(?:\.\d+)?)s', msg)
    if m:
        minutes = int(m.group(1))
        seconds = float(m.group(2))
        return minutes * 60.0 + seconds
    # 42.5s
    m = re.search(r'(\d+(?:\.\d+)?)s', msg)
    if m:
        return float(m.group(1))
    # valeur par défaut
    return 60.0


def _extract_json_block(text: str) -> Optional[str]:
    """
    Tente d'extraire un objet JSON depuis du texte (```json ... ``` ou ``` ... ```),
    sinon prend le 1er bloc {...}.
    """
    if not text:
        return None
    # fences ```json ... ``` puis ``` ... ```
    for fence in ("```json", "```"):
        if fence in text:
            try:
                chunk = text.split(fence, 1)[1]
                chunk = chunk.split("```", 1)[0]
                chunk = chunk.strip()
                if chunk.startswith("{") and chunk.endswith("}"):
                    return chunk
            except Exception:
                pass
    # recherche naïve { ... }
    start = text.find("{")
    end = text.rfind("}")
    if 0 <= start < end:
        candidate = text[start:end + 1].strip()
        if candidate:
            return candidate
    return None


class LLMClient:
    """
    Client LLM unifié avec fallback & circuit-breaker rate-limit.

    Priorité providers (configurable) :
      - env LLM_PROVIDER_PRIORITY="groq,openai" (défaut)
      - on ne retient que les providers dont la clé API est dispo

    Modèles (configurables) :
      - GROQ:  env LLM_MODEL_GROQ   (défaut: "llama-3.3-70b-versatile")
      - OpenAI:env LLM_MODEL_OPENAI (défaut: "gpt-4o-mini")
      - env LLM_MODEL prioritaire si vous voulez le même nom pour les deux.

    Activation :
      - env ENABLE_LLM="1" (défaut 1) pour activer/désactiver globalement
    """

    def __init__(self, model: Optional[str] = None, temperature: float = 0.2):
        # Ordre des providers souhaité
        raw_priority = os.getenv("LLM_PROVIDER_PRIORITY", "groq,openai")
        wanted = [p.strip().lower() for p in raw_priority.split(",") if p.strip()]

        # Filtre selon clés présentes
        available = []
        if os.getenv("GROQ_API_KEY"):
            available.append("groq")
        if os.getenv("OPENAI_API_KEY"):
            available.append("openai")

        # Liste finale dans l'ordre souhaité
        self.providers: List[str] = [p for p in wanted if p in available]
        if not self.providers:
            # fallback si rien détecté
            self.providers = available

        # Modèles
        self.model_any = model or os.getenv("LLM_MODEL")  # option globale (si même nom pour 2 providers)
        self.model_groq = os.getenv("LLM_MODEL_GROQ", "llama-3.3-70b-versatile")
        self.model_openai = os.getenv("LLM_MODEL_OPENAI", "gpt-4o-mini")

        self.temperature = float(os.getenv("LLM_TEMPERATURE", temperature or 0.2))
        self.enabled = os.getenv("ENABLE_LLM", "1") == "1" and len(self.providers) > 0

        # clients paresseux
        self._groq_client = None
        self._openai_client = None

        logger.info(
            "LLMClient initialized providers=%s model_any=%s model_groq=%s model_openai=%s enabled=%s",
            self.providers, self.model_any, self.model_groq, self.model_openai, self.enabled
        )

    # -------------------- Public API --------------------

    def chat_json(self, messages: List[Dict[str, Any]], max_tokens: int = 3000) -> Optional[Dict[str, Any]]:
        """
        Demande un **objet JSON**. Force le JSON mode quand disponible,
        sinon tente une extraction de bloc JSON.
        """
        if not self.enabled:
            logger.warning("LLM disabled: returning None for chat_json")
            return None

        for provider in self.providers:
            if _is_rate_limited(provider):
                logger.warning("Rate limit active for %s, using fallback", provider)
                continue

            try:
                content = self._call_provider(
                    provider=provider,
                    messages=messages,
                    max_tokens=max_tokens,
                    want_json=True
                )
                if not content:
                    continue
                # JSON strict
                try:
                    return json.loads(content)
                except Exception:
                    extracted = _extract_json_block(content)
                    if extracted:
                        return json.loads(extracted)
                    logger.error("Provider %s returned non-JSON content and no JSON block could be extracted.", provider)
            except RateLimitCaught as rl:
                _remember_rate_limit(provider, rl.retry_after_seconds)
                # on passe au provider suivant
            except Exception as e:
                logger.exception("Provider %s failed in chat_json: %s", provider, e)
                # on essaie le provider suivant

        return None

    def chat_text(self, messages: List[Dict[str, Any]], max_tokens: int = 1000) -> Optional[str]:
        """Réponse texte libre, avec fallback providers et backoff sur rate-limit."""
        if not self.enabled:
            logger.warning("LLM disabled: returning None for chat_text")
            return None

        for provider in self.providers:
            if _is_rate_limited(provider):
                logger.warning("Rate limit active for %s, using fallback", provider)
                continue

            try:
                content = self._call_provider(
                    provider=provider,
                    messages=messages,
                    max_tokens=max_tokens,
                    want_json=False
                )
                if content is not None:
                    return content.strip()
            except RateLimitCaught as rl:
                _remember_rate_limit(provider, rl.retry_after_seconds)
            except Exception as e:
                logger.exception("Provider %s failed in chat_text: %s", provider, e)

        return None

    # -------------------- Core call --------------------

    def _call_provider(
        self,
        provider: str,
        messages: List[Dict[str, Any]],
        max_tokens: int,
        want_json: bool,
        retries: int = 2,
        base_sleep: float = 0.75,
    ) -> Optional[str]:
        """
        Appelle le provider avec quelques retries/backoff (non-bloquants).
        Lève RateLimitCaught en cas de 429 afin que l'appelant gère le circuit-breaker.
        """
        provider = provider.lower()
        attempt = 0
        last_exc: Optional[Exception] = None

        while attempt <= retries:
            attempt += 1
            try:
                if provider == "groq":
                    return self._call_groq(messages, max_tokens, want_json)
                elif provider == "openai":
                    return self._call_openai(messages, max_tokens, want_json)
                else:
                    raise RuntimeError(f"Unsupported provider: {provider}")
            except RateLimitCaught:
                raise  # L'appelant gère la mise en cache et le fallback
            except ImportError as e:
                logger.error("SDK missing for provider=%s: %s", provider, e)
                return None
            except Exception as e:
                last_exc = e
                # backoff simple (pas sur rate-limit, déjà géré)
                if attempt <= retries:
                    sleep_s = base_sleep * (2 ** (attempt - 1))  # 0.75, 1.5, 3.0...
                    time.sleep(sleep_s)

        if last_exc:
            raise last_exc
        return None

    # -------------------- Providers --------------------

    def _call_groq(self, messages: List[Dict[str, Any]], max_tokens: int, want_json: bool) -> Optional[str]:
        from groq import Groq
        from groq import RateLimitError as GroqRateLimitError

        if self._groq_client is None:
            self._groq_client = Groq()

        model = self.model_any or self.model_groq

        try:
            kwargs = dict(
                model=model,
                temperature=self.temperature,
                max_tokens=max_tokens,
                messages=messages,
            )
            if want_json:
                kwargs["response_format"] = {"type": "json_object"}

            resp = self._groq_client.chat.completions.create(**kwargs)
            return (resp.choices[0].message.content or "").strip()

        except GroqRateLimitError as e:
            # Message standardisé Groq dans vos logs
            msg = getattr(e, "message", "") or str(e)
            retry = _parse_retry_after_seconds(msg)
            logger.error("Rate limit reached: %s", msg)
            raise RateLimitCaught(retry_after_seconds=retry)
        except Exception as e:
            # Autres erreurs Groq : on remonte, le caller gèrera les retries
            raise

    def _call_openai(self, messages: List[Dict[str, Any]], max_tokens: int, want_json: bool) -> Optional[str]:
        # Compat "openai" SDK v1 (chat.completions)
        from openai import OpenAI
        from openai import RateLimitError as OpenAIRateLimitError

        if self._openai_client is None:
            self._openai_client = OpenAI()

        model = self.model_any or self.model_openai

        try:
            kwargs = dict(
                model=model,
                temperature=self.temperature,
                max_tokens=max_tokens,
                messages=messages,
            )
            if want_json:
                kwargs["response_format"] = {"type": "json_object"}

            resp = self._openai_client.chat.completions.create(**kwargs)
            return (resp.choices[0].message.content or "").strip()

        except OpenAIRateLimitError as e:
            # OpenAI fournit généralement un Retry-After header, mais via SDK ce n’est pas garanti.
            msg = getattr(e, "message", "") or str(e)
            retry = _parse_retry_after_seconds(msg)
            logger.error("OpenAI rate limit reached: %s", msg)
            raise RateLimitCaught(retry_after_seconds=retry)
        except Exception as e:
            raise


class RateLimitCaught(RuntimeError):
    def __init__(self, retry_after_seconds: float):
        super().__init__(f"Rate limited. Retry after {retry_after_seconds:.1f}s")
        self.retry_after_seconds = retry_after_seconds
