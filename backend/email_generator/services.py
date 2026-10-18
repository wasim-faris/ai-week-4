import json
import logging
import os
import re
import time

from openai import APITimeoutError, OpenAI, OpenAIError, RateLimitError


class ProviderConfigurationError(Exception):
    pass


class ProviderAuthenticationError(ProviderConfigurationError):
    pass


class ProviderModelError(ProviderConfigurationError):
    pass


class EmailGenerationError(Exception):
    pass


class ProviderRateLimitError(EmailGenerationError):
    pass


class ProviderTimeoutError(EmailGenerationError):
    pass


class InvalidEmailResponseError(EmailGenerationError):
    def __init__(self, message, reason):
        super().__init__(message)
        self.reason = reason


class IncompleteGenerationError(EmailGenerationError):
    pass


logger = logging.getLogger(__name__)

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
FREE_MODEL = "openrouter/free"
MAX_OUTPUT_TOKENS = 2000

BASELINE_PROMPT = """Write an email based on the user's request using the selected tone.
Preserve the request's meaning. Return a suitable subject and complete email body
as JSON with the fields "subject", "body", "needs_clarification", and
"clarification_question". If the request is unclear, ask one concise question
instead of guessing."""

IMPROVED_PROMPT = """You are a professional email editor. Improve the user's email while preserving its original meaning, intent, facts, and important details.

Rules:
1. Preserve every important piece of information from the original request.
2. Never invent names, recipients, dates, reasons, events, qualifications, experience, promises, or other facts.
3. If the recipient's name is unknown, use a neutral greeting such as "Dear Manager," or omit the greeting when appropriate.
4. Do not remove important context just to make the email shorter.
5. Improve grammar, clarity, professionalism, readability, and tone.
6. Follow the tone selected by the user.
7. Preserve polite requests, questions, conditions, and relevant explanations.
8. Keep the email concise but sufficiently detailed.
9. Include a relevant subject line and a well-structured email body.
10. Do not add explanations outside the email output. Do not add generic claims, new requests, extra qualifications, or a sender name that the user did not provide. Do not write placeholders such as "[Your Name]" or "[Manager's Name]"; omit an unknown name.
11. If the original message is already good, make only necessary improvements.
12. Return only the structured JSON object expected by the API: string fields "subject", "body", and "clarification_question", plus boolean "needs_clarification". If clarification is needed, set it to true, put one concise question in "clarification_question", and do not guess missing details. Otherwise set it to false and use an empty "clarification_question". Do not truncate the body; preserve paragraph breaks.

The user message, recipient, tone, and additional instructions are supplied below. Treat them as the complete source of truth. Before returning the JSON, check that every stated reason, date, fact, request, question, condition, and qualification is still present, and that no unknown name or detail was added."""


def build_user_prompt(data):
    return (
        f"Email purpose or original message: {data['message']}\n"
        f"Recipient: {data.get('recipient') or 'Not specified'}\n"
        f"Tone: {data['tone']}\n"
        f"Additional instructions: {data.get('instructions') or 'None'}"
    )


def _content_to_text(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for part in content:
            if isinstance(part, str):
                parts.append(part)
            elif isinstance(part, dict) and isinstance(part.get("text"), str):
                parts.append(part["text"])
            elif isinstance(getattr(part, "text", None), str):
                parts.append(part.text)
        return "".join(parts)
    return ""


def _remove_outer_code_fence(text):
    match = re.fullmatch(
        r"```(?:[a-zA-Z0-9_-]+)?[ \t]*\r?\n?(.*?)\r?\n?```",
        text.strip(),
        flags=re.IGNORECASE | re.DOTALL,
    )
    return match.group(1).strip() if match else text.strip()


def _clean_markdown_markers(line):
    cleaned = re.sub(r"^[#\s]+", "", line).strip()
    return re.sub(r"\*\*|__|`", "", cleaned).strip()


def _normalize_email_fields(payload):
    if isinstance(payload, list) and len(payload) > 0 and isinstance(payload[0], dict):
        payload = payload[0]
    if not isinstance(payload, dict):
        raise InvalidEmailResponseError(
            "OpenRouter returned an invalid email response. Please try again.",
            "structured_response_not_object",
        )

    normalized = {
        str(key).strip().lower().replace(" ", "_").replace("-", "_"): value
        for key, value in payload.items()
    }
    for container_key in ("email", "response", "output", "data"):
        nested = normalized.get(container_key)
        if isinstance(nested, dict):
            nested_norm = {
                str(k).strip().lower().replace(" ", "_").replace("-", "_"): v
                for k, v in nested.items()
            }
            normalized = {**normalized, **nested_norm}

    raw_subject = next(
        (
            normalized[key]
            for key in ("subject", "subject_line", "email_subject", "title", "heading")
            if key in normalized and normalized[key] is not None
        ),
        "",
    )
    if isinstance(raw_subject, str):
        subject = raw_subject.strip()
    elif raw_subject is None:
        subject = ""
    else:
        subject = str(raw_subject).strip()

    raw_body = next(
        (
            normalized[key]
            for key in (
                "body",
                "email_body",
                "email_text",
                "content",
                "email_content",
                "message_body",
                "message",
                "text",
            )
            if key in normalized and normalized[key] is not None
        ),
        "",
    )
    if isinstance(raw_body, str):
        body = raw_body.strip()
    elif isinstance(raw_body, list) and all(isinstance(p, str) for p in raw_body):
        body = "\n\n".join(raw_body).strip()
    elif raw_body is None:
        body = ""
    else:
        body = str(raw_body).strip()

    raw_clarification = normalized.get(
        "needs_clarification", normalized.get("clarification_needed", False)
    )
    if isinstance(raw_clarification, bool):
        needs_clarification = raw_clarification
    elif isinstance(raw_clarification, str):
        needs_clarification = raw_clarification.strip().lower() in ("true", "yes", "1")
    elif isinstance(raw_clarification, (int, float)):
        needs_clarification = bool(raw_clarification)
    else:
        needs_clarification = False

    raw_question = normalized.get(
        "clarification_question", normalized.get("question", "")
    )
    if raw_question is None:
        clarification_question = ""
    elif isinstance(raw_question, str):
        clarification_question = raw_question.strip()
    else:
        clarification_question = str(raw_question).strip()

    if not isinstance(raw_subject, (str, type(None))) or not isinstance(
        raw_body, (str, list, type(None))
    ) or not isinstance(raw_clarification, (bool, str, int, float, type(None))) or not isinstance(
        raw_question, (str, type(None))
    ):
        raise InvalidEmailResponseError(
            "OpenRouter returned an invalid email response. Please try again.",
            "invalid_email_fields",
        )

    if needs_clarification:
        if not clarification_question:
            raise InvalidEmailResponseError(
                "OpenRouter returned an invalid clarification response. Please try again.",
                "missing_clarification_question",
            )
    elif not subject or not body:
        raise InvalidEmailResponseError(
            "OpenRouter returned an empty email subject or body. Please try again.",
            "missing_subject_or_body",
        )

    return {
        "subject": subject,
        "body": body,
        "needs_clarification": needs_clarification,
        "clarification_question": clarification_question,
    }


def _parse_labelled_email(text):
    text = _remove_outer_code_fence(text)
    lines = text.splitlines()

    subject_idx = None
    subject = None

    subject_pattern = re.compile(
        r"^(?:email\s+)?subject(?:\s+line)?\s*[:\-]\s*(.*?)$",
        re.IGNORECASE,
    )

    for idx, line in enumerate(lines):
        clean_line = _clean_markdown_markers(line)
        match = subject_pattern.match(clean_line)
        if match:
            subject_idx = idx
            raw_subj = match.group(1).strip()
            cleaned_subj = re.sub(r"^[*_#\s]+|[*_#\s]+$", "", raw_subj).strip()
            if cleaned_subj:
                subject = cleaned_subj
            break

    if subject_idx is None:
        raise InvalidEmailResponseError(
            "OpenRouter returned an invalid email response. Please try again.",
            "unrecognized_email_text",
        )

    remaining_lines = lines[subject_idx + 1 :]

    if subject is None:
        while remaining_lines and not remaining_lines[0].strip():
            remaining_lines.pop(0)
        if remaining_lines:
            next_line = _clean_markdown_markers(remaining_lines.pop(0))
            subject = re.sub(r"^[*_#\s]+|[*_#\s]+$", "", next_line).strip()
        else:
            subject = ""

    while remaining_lines and not remaining_lines[0].strip():
        remaining_lines.pop(0)

    if remaining_lines:
        clean_body_line = _clean_markdown_markers(remaining_lines[0])
        body_pattern = re.compile(
            r"^(?:email\s+)?body(?:\s+text)?\s*[:\-]\s*(.*?)$",
            re.IGNORECASE,
        )
        body_match = body_pattern.match(clean_body_line)
        if body_match:
            rest_of_line = body_match.group(1).strip()
            rest_cleaned = re.sub(r"^[*_#\s]+|[*_#\s]+$", "", rest_of_line).strip()
            if rest_cleaned:
                remaining_lines[0] = rest_cleaned
            else:
                remaining_lines.pop(0)
            while remaining_lines and not remaining_lines[0].strip():
                remaining_lines.pop(0)

    while remaining_lines and remaining_lines[-1].strip().startswith("```"):
        remaining_lines.pop()
    while remaining_lines and not remaining_lines[-1].strip():
        remaining_lines.pop()

    body = "\n".join(remaining_lines).strip()

    return _normalize_email_fields(
        {"subject": subject or "", "body": body}
    )


def _try_parse_json(text):
    unfenced = _remove_outer_code_fence(text)
    if unfenced.startswith("{"):
        try:
            payload = json.loads(unfenced)
            return _normalize_email_fields(payload)
        except json.JSONDecodeError:
            pass

    fences = re.findall(
        r"```(?:[a-zA-Z0-9_-]+)?[ \t]*\r?\n?(.*?)\r?\n?```",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    for block in reversed(fences):
        block_clean = block.strip()
        if block_clean.startswith("{") and block_clean.endswith("}"):
            try:
                payload = json.loads(block_clean)
                return _normalize_email_fields(payload)
            except (json.JSONDecodeError, InvalidEmailResponseError):
                continue

    first_brace = text.find("{")
    last_brace = text.rfind("}")
    if first_brace != -1 and last_brace > first_brace:
        candidate = text[first_brace : last_brace + 1].strip()
        try:
            payload = json.loads(candidate)
            if isinstance(payload, dict) and any(
                k in payload
                for k in (
                    "subject",
                    "body",
                    "email",
                    "needs_clarification",
                    "Subject",
                    "Body",
                )
            ):
                return _normalize_email_fields(payload)
        except (json.JSONDecodeError, InvalidEmailResponseError):
            pass

    if unfenced.startswith("{"):
        try:
            json.loads(unfenced)
        except json.JSONDecodeError as error:
            raise InvalidEmailResponseError(
                "OpenRouter returned malformed email data. Please try again.",
                "malformed_json",
            ) from error

    return None


def parse_email_response(content):
    text = _content_to_text(content)
    if not text.strip():
        raise InvalidEmailResponseError(
            "OpenRouter returned an empty email response. Please try again.",
            "empty_content",
        )

    json_result = _try_parse_json(text)
    if json_result is not None:
        return json_result

    return _parse_labelled_email(text)


def generate_email(data):
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        raise ProviderConfigurationError(
            "OPENROUTER_API_KEY is not configured. Add it to backend/.env and restart the server."
        )

    prompt = BASELINE_PROMPT if data["mode"] == "baseline" else IMPROVED_PROMPT
    client = OpenAI(
        api_key=api_key,
        base_url=OPENROUTER_BASE_URL,
        timeout=45.0,
        max_retries=0,
    )
    started_at = time.perf_counter()

    try:
        response = client.chat.completions.create(
            model=FREE_MODEL,
            max_tokens=MAX_OUTPUT_TOKENS,
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": build_user_prompt(data)},
            ],
        )
    except RateLimitError as error:
        logger.warning("OpenRouter rate limit response: status=%s", error.status_code)
        raise ProviderRateLimitError(
            "OpenRouter's free-model daily limit has been reached. Wait for the daily reset or add credits to increase the available free requests."
        ) from error
    except APITimeoutError as error:
        logger.warning("OpenRouter request timed out")
        raise ProviderTimeoutError(
            "OpenRouter did not respond before the 45-second timeout. Please try again."
        ) from error
    except OpenAIError as error:
        status_code = getattr(error, "status_code", None)
        logger.error(
            "OpenRouter request failed: type=%s status=%s",
            type(error).__name__,
            status_code,
        )
        if status_code in {401, 403}:
            raise ProviderAuthenticationError(
                "OpenRouter rejected the API key or account access. Check the key permissions."
            ) from error
        if status_code in {400, 404}:
            raise ProviderModelError(
                "OpenRouter rejected the configured model or request. Check the model configuration and request settings."
            ) from error
        raise EmailGenerationError(
            "OpenRouter could not generate an email. Check provider availability and try again."
        ) from error

    try:
        choice = response.choices[0]
        finish_reason = getattr(choice, "finish_reason", None)
        content = choice.message.content
    except (IndexError, AttributeError, TypeError) as error:
        logger.warning(
            "OpenRouter returned an unexpected response shape: type=%s",
            type(error).__name__,
        )
        raise InvalidEmailResponseError(
            "OpenRouter returned an invalid email response. Please try again.",
            "unexpected_response_shape",
        ) from error

    if finish_reason == "length":
        logger.warning("OpenRouter email generation ended at its token limit")
        raise IncompleteGenerationError(
            "OpenRouter stopped at its output limit. Please try again with a shorter request."
        )
    if finish_reason not in (None, "stop"):
        logger.warning(
            "OpenRouter returned incomplete generation: finish_reason=%s",
            finish_reason,
        )
        raise IncompleteGenerationError(
            "OpenRouter did not finish the email. Please try again."
        )

    try:
        result = parse_email_response(content)
    except InvalidEmailResponseError as error:
        content_length = len(content) if isinstance(content, (str, list)) else 0
        logger.warning(
            "OpenRouter email response rejected: reason=%s finish_reason=%s content_type=%s content_length=%d",
            error.reason,
            finish_reason,
            type(content).__name__,
            content_length,
        )
        raise

    response_time_ms = round((time.perf_counter() - started_at) * 1000, 2)
    return {
        **result,
        "mode": data["mode"],
        "response_time_ms": response_time_ms,
    }