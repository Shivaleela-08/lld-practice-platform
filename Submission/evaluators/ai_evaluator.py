"""
AI evaluator for judgement-heavy LLD rubric dimensions.

Uses Gemini through the REST API. If Gemini is unavailable, the evaluator
returns an error result so deterministic evaluation can still provide useful
feedback.
"""

import json
import os
import urllib.request
from typing import List

from dotenv import load_dotenv

from domain.models import (
    AI_DIMENSIONS,
    DimensionScore,
    EvaluationResult,
    EvaluatorKind,
    Problem,
    Submission,
)
from evaluators.base import Evaluator


load_dotenv()

GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta/"
    "models/gemini-flash-latest:generateContent"
)

MODEL = "gemini-flash-latest"

SYSTEM_PROMPT = """You are an expert Low-Level Design interviewer evaluating
a learner's LLD solution.

Evaluate the solution against the supplied rubric.

There can be multiple valid designs. Do not require the learner to match one
specific reference solution. Judge the quality of reasoning, responsibilities,
coupling, cohesion, abstraction, extensibility, interfaces, edge cases and
explanation.

Return ONLY valid JSON in this exact format:

{
  "dimensions": [
    {
      "criterion": "<rubric dimension>",
      "score": <integer from 1 to 5>,
      "evidence": "<specific evidence from submission>",
      "concern": "<specific concern or null>",
      "suggestion": "<specific improvement or null>"
    }
  ],
  "confidence": <number from 0 to 1>
}
"""


class AIEvaluator(Evaluator):

    def __init__(self, api_key: str = None):
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY")

    def evaluate(
        self,
        problem: Problem,
        submission: Submission
    ) -> EvaluationResult:

        if not self.api_key:
            return EvaluationResult.create(
                submission_id=submission.id,
                kind=EvaluatorKind.AI,
                scores=[],
                confidence=0.0,
                error="GEMINI_API_KEY is not configured.",
            )

        user_prompt = self._build_prompt(problem, submission)

        payload = {
            "system_instruction": {
                "parts": [
                    {
                        "text": SYSTEM_PROMPT
                    }
                ]
            },
            "contents": [
                {
                    "parts": [
                        {
                            "text": user_prompt
                        }
                    ]
                }
            ],
            "generationConfig": {
                "temperature": 0.2,
                "maxOutputTokens": 1500,
                "responseMimeType": "application/json",
            },
        }

        request = urllib.request.Request(
            GEMINI_URL,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "x-goog-api-key": self.api_key,
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                body = json.loads(
                    response.read().decode("utf-8")
                )

            raw_text = self._extract_text(body)
            parsed = self._parse_json(raw_text)

            scores: List[DimensionScore] = []

            for dimension in parsed.get("dimensions", []):

                criterion = dimension.get("criterion")

                if criterion not in AI_DIMENSIONS:
                    continue

                score = int(dimension.get("score", 3))
                score = max(1, min(5, score))

                scores.append(
                    DimensionScore(
                        criterion=criterion,
                        score=score,
                        evidence=dimension.get("evidence", ""),
                        concern=dimension.get("concern"),
                        suggestion=dimension.get("suggestion"),
                    )
                )

            confidence = float(
                parsed.get("confidence", 0.7)
            )

            confidence = max(
                0.0,
                min(1.0, confidence)
            )

            return EvaluationResult.create(
                submission_id=submission.id,
                kind=EvaluatorKind.AI,
                scores=scores,
                confidence=confidence,
            )

        except Exception as exc:

            return EvaluationResult.create(
                submission_id=submission.id,
                kind=EvaluatorKind.AI,
                scores=[],
                confidence=0.0,
                error=f"AI evaluator call failed: {exc}",
            )

    def _build_prompt(
        self,
        problem: Problem,
        submission: Submission
    ) -> str:

        requirements = "\n".join(
            f"- {requirement}"
            for requirement in problem.requirements
        )

        return (
            f"Problem: {problem.title}\n\n"
            f"Context: {problem.summary}\n\n"
            f"Requirements:\n{requirements}\n\n"
            f"Rubric dimensions:\n{AI_DIMENSIONS}\n\n"
            f"Learner submission "
            f"({submission.format.value}):\n"
            f"{submission.content}"
        )

    @staticmethod
    def _extract_text(body: dict) -> str:

        candidates = body.get("candidates", [])

        if not candidates:
            raise RuntimeError(
                "Gemini returned no candidates."
            )

        parts = (
            candidates[0]
            .get("content", {})
            .get("parts", [])
        )

        text = "".join(
            part.get("text", "")
            for part in parts
            if part.get("text")
        )

        if not text:
            raise RuntimeError(
                "Gemini returned an empty response."
            )

        return text

    @staticmethod
    def _parse_json(raw_text: str) -> dict:

        raw_text = raw_text.strip()

        if raw_text.startswith("```"):
            lines = raw_text.splitlines()

            if lines and lines[0].startswith("```"):
                lines = lines[1:]

            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]

            raw_text = "\n".join(lines).strip()

        try:
            return json.loads(raw_text)

        except json.JSONDecodeError as exc:
            raise RuntimeError(
                f"AI evaluator returned invalid JSON: {exc}"
            ) from exc