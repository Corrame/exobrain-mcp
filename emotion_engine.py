# ============================================================
# Module: Emotion & Decay Engine (emotion_engine.py)
# 
# The decay algorithms and emotional coordinate concepts are heavily inspired by 
# and adapted from P0lar1zzZ's Ombre-Brain project (MIT License).
# Source: https://github.com/P0lar1zzZ/Ombre-Brain
# ============================================================

import math
import os
import re
import json
import logging
from datetime import datetime
from typing import Dict, Any, Optional

logger = logging.getLogger("exobrain.emotion")

class EmotionEngine:
    """
    Handles calculating emotion (Valence/Arousal) from text via LLM
    and calculating memory decay via Ebbinghaus curve.
    """

    def __init__(self):
        # Decay Parameters logic (Adapted for lifelogging UX)
        self.emotion_base = 1.0
        self.arousal_boost = 4.0 # High multiplier for extreme emotions

    def calculate_decay_score(self, metadata: dict) -> float:
        """
        Calculate current activity score for a memory log.
        Formula: Score = (act_count^0.3) * exp(-lambda * days) * (base + arousal * boost)
        """
        try:
            activation_count = max(1, int(metadata.get("activation_count", 1)))
        except (ValueError, TypeError):
            activation_count = 1

        # Days since last activation
        last_active_str = metadata.get("last_active_at", metadata.get("created_at", ""))
        try:
            last_active = datetime.fromisoformat(str(last_active_str).replace('Z', ''))
            days_since = max(0.0, (datetime.now() - last_active).total_seconds() / 86400)
        except (ValueError, TypeError):
            days_since = 1.0  # Default if parsing fails

        # Arousal weight (Exponential boost: extreme arousal gets massive multiplier)
        try:
            arousal = max(0.0, min(1.0, float(metadata.get("arousal", 0.3))))
        except (ValueError, TypeError):
            arousal = 0.3
            
        emotion_weight = self.emotion_base + ((arousal ** 2) * self.arousal_boost)
        importance_base = 5.0 # For raw logs, we assume a standard importance baseline

        # Modern Logarithmic Decay: fast initial drop, long-tail persistence. Never drops to 0.
        # At day 0 = 1.0. At day 90 = 0.5. At day 3 years = 0.33. At day 30 years = 0.25.
        time_decay = 1.0 / math.log10(days_since + 10.0)
        
        # Ensure hard floor so it mathematically never vanishes below 0.1
        time_decay = max(0.1, time_decay)

        # Apply New Decay Formula
        score = (
            importance_base
            * (activation_count ** 0.3)
            * time_decay
            * emotion_weight
        )

        return round(score, 4)

    async def analyze_emotion_api(self, client, model: str, content: str) -> dict:
        """
        Extract domain, valence, and arousal from content using LLM.
        """
        ANALYZE_PROMPT = """你是一个心智与情感分析器。请分析以下文本的主题域与情感成分。

分析规则：
1. domain（主题域）：选最精确的 1~2 个（日常/人际/成长/身心/兴趣/事务/内心/其他）
2. valence（情感效价）：0.0~1.0，0=极度痛苦消极 → 0.5=中立客观 → 1.0=极度幸福积极
3. arousal（情感唤醒度）：0.0~1.0，0=极其平淡的流水账 → 0.5=普通陈述 → 1.0=情绪极度激动、创伤或狂喜

请严格以JSON格式输出：
{
  "domain": ["主题"],
  "valence": 0.5,
  "arousal": 0.3
}
"""
        try:
            response = await client.messages.create(
                model=model,
                max_tokens=150,
                messages=[{
                    "role": "user",
                    "content": f"{ANALYZE_PROMPT}\n\n待分析内容：\n{content[:1000]}"
                }],
            )
            raw = response.content[0].text.strip()
            
            # Simple JSON extraction
            match = re.search(r'\{.*\}', raw, re.DOTALL)
            if match:
                result = json.loads(match.group(0))
                return {
                    "domain": result.get("domain", ["未分类"])[:2],
                    "valence": max(0.0, min(1.0, float(result.get("valence", 0.5)))),
                    "arousal": max(0.0, min(1.0, float(result.get("arousal", 0.3))))
                }
        except Exception as e:
            logger.warning(f"Emotion analysis failed: {e}")
        
        # Fallback values
        return {"domain": ["未分类"], "valence": 0.5, "arousal": 0.3}
