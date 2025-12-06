"""LLM client for direction detection using Gemini or OpenAI."""

import json
import logging
from pathlib import Path
from typing import Optional

from apartment_tracker.models.schemas import DirectionResult

logger = logging.getLogger(__name__)


class LLMClient:
    """Client for LLM-based analysis using Gemini or OpenAI."""

    def __init__(
        self,
        provider: str = "gemini",
        api_key: Optional[str] = None,
        model: Optional[str] = None,
    ):
        self.provider = provider.lower()
        self.api_key = api_key
        self.model = model or self._default_model()
        self._client = None

    def _default_model(self) -> str:
        """Get the default model for the provider."""
        if self.provider == "gemini":
            return "gemini-1.5-flash"
        elif self.provider == "openai":
            return "gpt-4o-mini"
        else:
            return "gemini-1.5-flash"

    def _ensure_client(self):
        """Initialize the API client if not already done."""
        if self._client is not None:
            return

        if not self.api_key:
            raise ValueError(f"API key required for {self.provider}")

        if self.provider == "gemini":
            try:
                import google.generativeai as genai
                genai.configure(api_key=self.api_key)
                self._client = genai.GenerativeModel(self.model)
            except ImportError:
                raise ImportError("google-generativeai package required. Run: pip install google-generativeai")

        elif self.provider == "openai":
            try:
                from openai import OpenAI
                self._client = OpenAI(api_key=self.api_key)
            except ImportError:
                raise ImportError("openai package required. Run: pip install openai")

        else:
            raise ValueError(f"Unknown provider: {self.provider}")

    async def analyze_direction(
        self,
        floor_plan_image_path: Optional[Path] = None,
        community_map_image_path: Optional[Path] = None,
        unit_number: str = "",
        additional_context: str = "",
    ) -> DirectionResult:
        """Analyze floor plan and community map to determine window direction.

        Args:
            floor_plan_image_path: Path to the floor plan image.
            community_map_image_path: Path to the community map image.
            unit_number: The unit number for context.
            additional_context: Any additional text context.

        Returns:
            DirectionResult with facing_direction, view_type, and confidence.
        """
        self._ensure_client()

        prompt = self._build_direction_prompt(unit_number, additional_context)

        try:
            if self.provider == "gemini":
                return await self._analyze_with_gemini(
                    prompt, floor_plan_image_path, community_map_image_path
                )
            elif self.provider == "openai":
                return await self._analyze_with_openai(
                    prompt, floor_plan_image_path, community_map_image_path
                )
            else:
                return DirectionResult(confidence=0.0)

        except Exception as e:
            logger.error(f"LLM analysis failed: {e}")
            return DirectionResult(confidence=0.0)

    def _build_direction_prompt(self, unit_number: str, additional_context: str) -> str:
        """Build the prompt for direction analysis."""
        return f"""Analyze these apartment images to determine the window direction and view type.

Unit: {unit_number}
{additional_context}

Based on the floor plan and community map:

1. What cardinal direction (N, NE, E, SE, S, SW, W, NW) do the BEDROOM windows primarily face?
   - Look at the floor plan layout and window positions
   - Consider the unit's position on the community map
   - Use any compass indicators visible on the images

2. What is the view type from the bedroom windows?
   - courtyard: faces an internal courtyard or pool area
   - street: faces a street or parking area
   - building: directly faces another building (less desirable)
   - nature: faces trees, park, or open space
   - unknown: cannot determine

3. Rate your confidence (0.0 to 1.0) in this assessment.

Respond ONLY with valid JSON in this exact format:
{{"facing_direction": "SW", "view_type": "courtyard", "confidence": 0.8}}

If you cannot determine the direction, use:
{{"facing_direction": null, "view_type": "unknown", "confidence": 0.0}}
"""

    async def _analyze_with_gemini(
        self,
        prompt: str,
        floor_plan_path: Optional[Path],
        community_map_path: Optional[Path],
    ) -> DirectionResult:
        """Analyze using Google Gemini."""
        import google.generativeai as genai

        parts = [prompt]

        # Add images if provided
        if floor_plan_path and floor_plan_path.exists():
            image_data = floor_plan_path.read_bytes()
            parts.append({
                "mime_type": self._get_mime_type(floor_plan_path),
                "data": image_data
            })

        if community_map_path and community_map_path.exists():
            image_data = community_map_path.read_bytes()
            parts.append({
                "mime_type": self._get_mime_type(community_map_path),
                "data": image_data
            })

        response = self._client.generate_content(parts)

        return self._parse_response(response.text)

    async def _analyze_with_openai(
        self,
        prompt: str,
        floor_plan_path: Optional[Path],
        community_map_path: Optional[Path],
    ) -> DirectionResult:
        """Analyze using OpenAI."""
        import base64

        messages = [{"role": "user", "content": []}]

        # Add text prompt
        messages[0]["content"].append({"type": "text", "text": prompt})

        # Add images if provided
        for path in [floor_plan_path, community_map_path]:
            if path and path.exists():
                image_data = base64.b64encode(path.read_bytes()).decode()
                mime_type = self._get_mime_type(path)
                messages[0]["content"].append({
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:{mime_type};base64,{image_data}"
                    }
                })

        response = self._client.chat.completions.create(
            model=self.model,
            messages=messages,
            max_tokens=500,
        )

        return self._parse_response(response.choices[0].message.content)

    def _get_mime_type(self, path: Path) -> str:
        """Get MIME type from file extension."""
        ext = path.suffix.lower()
        mime_types = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".gif": "image/gif",
            ".webp": "image/webp",
        }
        return mime_types.get(ext, "image/png")

    def _parse_response(self, response_text: str) -> DirectionResult:
        """Parse LLM response into DirectionResult."""
        try:
            # Clean up response - find JSON in the text
            response_text = response_text.strip()

            # Try to extract JSON from markdown code blocks
            if "```" in response_text:
                import re
                json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', response_text, re.DOTALL)
                if json_match:
                    response_text = json_match.group(1)

            # Try to find JSON object
            start = response_text.find('{')
            end = response_text.rfind('}') + 1
            if start >= 0 and end > start:
                json_str = response_text[start:end]
                data = json.loads(json_str)

                return DirectionResult(
                    facing_direction=data.get("facing_direction"),
                    view_type=data.get("view_type", "unknown"),
                    confidence=float(data.get("confidence", 0.0)),
                )

        except (json.JSONDecodeError, KeyError, ValueError) as e:
            logger.warning(f"Failed to parse LLM response: {e}")

        return DirectionResult(confidence=0.0)


async def detect_direction(
    api_key: str,
    provider: str = "gemini",
    floor_plan_path: Optional[Path] = None,
    community_map_path: Optional[Path] = None,
    unit_number: str = "",
) -> DirectionResult:
    """Convenience function for direction detection.

    Args:
        api_key: API key for the LLM provider.
        provider: 'gemini' or 'openai'.
        floor_plan_path: Path to floor plan image.
        community_map_path: Path to community map image.
        unit_number: Unit number for context.

    Returns:
        DirectionResult with facing direction and confidence.
    """
    client = LLMClient(provider=provider, api_key=api_key)
    return await client.analyze_direction(
        floor_plan_image_path=floor_plan_path,
        community_map_image_path=community_map_path,
        unit_number=unit_number,
    )
