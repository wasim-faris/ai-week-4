import json
import os
from types import SimpleNamespace
from unittest.mock import patch

import httpx
from openai import APITimeoutError, OpenAIError, RateLimitError
from django.test import SimpleTestCase
from rest_framework.test import APIClient
from run_benchmark import TEST_CASES, run_benchmark

from .services import (
    BASELINE_PROMPT,
    FREE_MODEL,
    IMPROVED_PROMPT,
    OPENROUTER_BASE_URL,
    EmailGenerationError,
    IncompleteGenerationError,
    InvalidEmailResponseError,
    ProviderAuthenticationError,
    ProviderConfigurationError,
    ProviderModelError,
    ProviderRateLimitError,
    ProviderTimeoutError,
    generate_email,
    parse_email_response,
)


class GenerateEmailApiTests(SimpleTestCase):
    def setUp(self):
        self.client = APIClient()
        self.payload = {
            "message": "Requesting leave tomorrow for personal work",
            "recipient": "My manager",
            "tone": "Professional",
            "instructions": "Keep it brief",
            "mode": "baseline",
        }

    def test_prompts_prohibit_unsupported_details_and_placeholders(self):
        normalized_prompt = " ".join(IMPROVED_PROMPT.split())
        self.assertIn("preserving its original meaning, intent, facts", normalized_prompt)
        self.assertIn("Preserve every important piece of information", normalized_prompt)
        self.assertIn("Never invent names, recipients, dates, reasons, events, qualifications", normalized_prompt)
        self.assertIn("use a neutral greeting such as \"Dear Manager,\"", normalized_prompt)
        self.assertIn("Do not remove important context", normalized_prompt)
        self.assertIn("Preserve polite requests, questions, conditions", normalized_prompt)
        self.assertIn("Follow the tone selected by the user", normalized_prompt)
        self.assertIn("Do not truncate the body", normalized_prompt)

    def test_benchmark_covers_five_detail_preservation_scenarios(self):
        self.assertEqual(len(TEST_CASES), 5)
        case_messages = {case["name"]: case["message"] for case in TEST_CASES}
        self.assertIn("personal reasons", case_messages["Leave request"])
        self.assertIn("confirm", case_messages["Leave request"])
        self.assertIn("statistics", case_messages["Job application"])
        self.assertIn("Excel and SQL", case_messages["Job application"])
        self.assertIn("May 12 at 2:00 PM", case_messages["Meeting reschedule"])
        self.assertIn("final figures", case_messages["Apology"])
        self.assertIn("completion percentage", case_messages["Project update"])

    @patch("run_benchmark.request_email")
    def test_benchmark_sends_identical_inputs_to_both_modes(self, request_email):
        request_email.return_value = {
            "subject": "A subject",
            "body": "A body",
            "response_time_ms": 1.0,
            "mode": "baseline",
        }

        run_benchmark("http://example.test/api/")

        self.assertEqual(request_email.call_count, 10)
        calls = request_email.call_args_list
        for baseline_call, improved_call in zip(calls[::2], calls[1::2]):
            self.assertEqual(baseline_call.args[1], improved_call.args[1])
            self.assertEqual(baseline_call.args[2], "baseline")
            self.assertEqual(improved_call.args[2], "improved")

    def test_service_reports_missing_openrouter_key(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(ProviderConfigurationError):
                generate_email(self.payload)

    @patch("email_generator.services.OpenAI")
    def test_service_classifies_free_model_rate_limit(self, openai_client):
        response = httpx.Response(
            429,
            request=httpx.Request("POST", "https://openrouter.ai/api/v1/chat/completions"),
        )
        openai_client.return_value.chat.completions.create.side_effect = RateLimitError(
            "free model daily limit reached", response=response, body={}
        )

        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-key"}, clear=True):
            with self.assertRaises(ProviderRateLimitError):
                generate_email(self.payload)

    @patch("email_generator.services.OpenAI")
    def test_service_classifies_provider_timeout(self, openai_client):
        request = httpx.Request("POST", "https://openrouter.ai/api/v1/chat/completions")
        openai_client.return_value.chat.completions.create.side_effect = APITimeoutError(
            request=request
        )

        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-key"}, clear=True):
            with self.assertRaises(ProviderTimeoutError):
                generate_email(self.payload)

    @patch("email_generator.services.OpenAI")
    def test_service_classifies_authentication_error(self, openai_client):
        error = OpenAIError("authentication failed")
        error.status_code = 401
        openai_client.return_value.chat.completions.create.side_effect = error

        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-key"}, clear=True):
            with self.assertRaises(ProviderAuthenticationError):
                generate_email(self.payload)

    @patch("email_generator.services.OpenAI")
    def test_service_classifies_invalid_model_error(self, openai_client):
        error = OpenAIError("model not found")
        error.status_code = 404
        openai_client.return_value.chat.completions.create.side_effect = error

        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-key"}, clear=True):
            with self.assertRaises(ProviderModelError):
                generate_email(self.payload)

    @patch("email_generator.services.time.perf_counter", side_effect=[10.0, 10.25])
    @patch("email_generator.services.OpenAI")
    def test_service_uses_openrouter_free_model(self, openai_client, perf_counter):
        client = openai_client.return_value
        client.chat.completions.create.return_value = SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        content=json.dumps(
                            {
                                "subject": "Leave request",
                                "body": "Hello, I would like to request leave tomorrow.",
                                "needs_clarification": False,
                                "clarification_question": "",
                            }
                        )
                    )
                )
            ]
        )

        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-key"}, clear=True):
            result = generate_email(self.payload)

        openai_client.assert_called_once_with(
            api_key="test-key",
            base_url=OPENROUTER_BASE_URL,
            timeout=45.0,
            max_retries=0,
        )
        request = client.chat.completions.create.call_args.kwargs
        self.assertEqual(request["model"], FREE_MODEL)
        self.assertEqual(request["max_tokens"], 2000)
        self.assertEqual(request["messages"][0]["content"], BASELINE_PROMPT)
        self.assertNotIn("response_format", request)
        self.assertEqual(result["response_time_ms"], 250.0)
        self.assertFalse(result["needs_clarification"])

    @patch("email_generator.services.OpenAI")
    def test_improved_mode_sends_preservation_prompt_and_all_user_fields(self, openai_client):
        client = openai_client.return_value
        client.chat.completions.create.return_value = SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        content=json.dumps(
                            {
                                "subject": "Leave request",
                                "body": "Dear Manager,\n\nI request leave for tomorrow for personal reasons.\n\nPlease confirm if this can be accommodated.\n\nThank you.",
                                "needs_clarification": False,
                                "clarification_question": "",
                            }
                        )
                    )
                )
            ]
        )
        request_payload = {
            **self.payload,
            "message": "Request leave tomorrow for personal reasons and ask for confirmation.",
            "instructions": "Keep the reason and confirmation request.",
            "mode": "improved",
        }

        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-key"}, clear=True):
            result = generate_email(request_payload)

        messages = client.chat.completions.create.call_args.kwargs["messages"]
        self.assertEqual(messages[0]["content"], IMPROVED_PROMPT)
        self.assertIn(request_payload["message"], messages[1]["content"])
        self.assertIn(request_payload["recipient"], messages[1]["content"])
        self.assertIn(request_payload["tone"], messages[1]["content"])
        self.assertIn(request_payload["instructions"], messages[1]["content"])
        self.assertEqual(
            result["body"],
            "Dear Manager,\n\nI request leave for tomorrow for personal reasons.\n\nPlease confirm if this can be accommodated.\n\nThank you.",
        )

    @patch("email_generator.services.OpenAI")
    def test_parser_preserves_complete_multiline_body(self, openai_client):
        complete_body = "Dear Manager,\n\nPersonal reasons\n\nPlease confirm.\n" + "Final detail. " * 500
        client = openai_client.return_value
        client.chat.completions.create.return_value = SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        content=json.dumps(
                            {
                                "subject": "Leave request",
                                "body": complete_body,
                                "needs_clarification": False,
                                "clarification_question": "",
                            }
                        )
                    )
                )
            ]
        )

        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-key"}, clear=True):
            result = generate_email(self.payload)

        self.assertEqual(result["body"], complete_body.strip())

    def test_parser_accepts_fenced_json_with_field_aliases(self):
        body = "Dear Manager,\n\nPlease confirm.\n\nThank you."
        content = "```json\n" + json.dumps(
            {"Subject Line": "Leave request", "Email Body": body}
        ) + "\n```"

        result = parse_email_response(content)

        self.assertEqual(result["subject"], "Leave request")
        self.assertEqual(result["body"], body)
        self.assertFalse(result["needs_clarification"])
        self.assertEqual(result["clarification_question"], "")

    def test_parser_accepts_labelled_email_text_and_keeps_paragraphs(self):
        body = "Dear Manager,\n\nPersonal reasons.\n\nPlease confirm."

        result = parse_email_response(f"Subject: Leave request\n\nBody:\n{body}")

        self.assertEqual(result["subject"], "Leave request")
        self.assertEqual(result["body"], body)

    def test_parser_accepts_subject_value_on_following_line(self):
        result = parse_email_response(
            "Subject:\nLeave request\n\nBody:\nDear Manager.\n\nPlease confirm."
        )

        self.assertEqual(result["subject"], "Leave request")
        self.assertEqual(result["body"], "Dear Manager.\n\nPlease confirm.")

    def test_parser_accepts_multipart_content(self):
        result = parse_email_response(
            [
                {"type": "text", "text": "Subject: Leave request\n\n"},
                {"type": "text", "text": "Body:\nDear Manager.\n\nPlease confirm."},
            ]
        )

        self.assertEqual(result["subject"], "Leave request")
        self.assertEqual(result["body"], "Dear Manager.\n\nPlease confirm.")

    def test_parser_rejects_empty_and_malformed_json(self):
        for content in ("", "   ", "```json\n{not json}\n```"):
            with self.subTest(content=content):
                with self.assertRaises(InvalidEmailResponseError):
                    parse_email_response(content)

    @patch("email_generator.services.OpenAI")
    def test_service_returns_clarification_for_unclear_request(self, openai_client):
        client = openai_client.return_value
        client.chat.completions.create.return_value = SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        content=json.dumps(
                            {
                                "subject": "A little more information",
                                "body": "",
                                "needs_clarification": True,
                                "clarification_question": "Which meeting should I mention?",
                            }
                        )
                    )
                )
            ]
        )

        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-key"}, clear=True):
            result = generate_email(self.payload)

        self.assertTrue(result["needs_clarification"])
        self.assertEqual(
            result["clarification_question"], "Which meeting should I mention?"
        )

    @patch("email_generator.services.OpenAI")
    def test_service_accepts_subject_and_body_without_optional_clarification_fields(self, openai_client):
        client = openai_client.return_value
        client.chat.completions.create.return_value = SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        content=json.dumps({"subject": "Hello", "body": "Hello there."})
                    )
                )
            ]
        )

        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-key"}, clear=True):
            result = generate_email(self.payload)

        self.assertEqual(result["subject"], "Hello")
        self.assertEqual(result["body"], "Hello there.")
        self.assertFalse(result["needs_clarification"])
        self.assertEqual(result["clarification_question"], "")

    @patch("email_generator.services.OpenAI")
    def test_service_rejects_truncated_completion(self, openai_client):
        client = openai_client.return_value
        client.chat.completions.create.return_value = SimpleNamespace(
            choices=[
                SimpleNamespace(
                    finish_reason="length",
                    message=SimpleNamespace(
                        content=json.dumps(
                            {
                                "subject": "Leave request",
                                "body": "The body appears complete but was truncated.",
                                "needs_clarification": False,
                                "clarification_question": "",
                            }
                        )
                    ),
                )
            ]
        )

        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-key"}, clear=True):
            with self.assertRaises(IncompleteGenerationError):
                generate_email(self.payload)

    @patch("email_generator.services.OpenAI")
    def test_service_rejects_empty_provider_content(self, openai_client):
        client = openai_client.return_value
        client.chat.completions.create.return_value = SimpleNamespace(
            choices=[
                SimpleNamespace(
                    finish_reason="stop",
                    message=SimpleNamespace(content=None),
                )
            ]
        )

        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-key"}, clear=True):
            with self.assertRaises(InvalidEmailResponseError):
                generate_email(self.payload)

    @patch("email_generator.services.OpenAI")
    def test_service_rejects_malformed_structured_content(self, openai_client):
        client = openai_client.return_value
        client.chat.completions.create.return_value = SimpleNamespace(
            choices=[
                SimpleNamespace(
                    finish_reason="stop",
                    message=SimpleNamespace(content="```json\n{broken}\n```"),
                )
            ]
        )

        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-key"}, clear=True):
            with self.assertRaises(InvalidEmailResponseError):
                generate_email(self.payload)

    @patch("email_generator.services.OpenAI")
    def test_service_rejects_non_normal_finish_reason(self, openai_client):
        client = openai_client.return_value
        client.chat.completions.create.return_value = SimpleNamespace(
            choices=[
                SimpleNamespace(
                    finish_reason="content_filter",
                    message=SimpleNamespace(content="A complete-looking email."),
                )
            ]
        )

        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-key"}, clear=True):
            with self.assertRaises(IncompleteGenerationError):
                generate_email(self.payload)

    @patch("email_generator.views.generate_email")
    def test_returns_generated_email_and_timing(self, generate_email):
        generate_email.return_value = {
            "subject": "Leave request",
            "body": "Hello, I would like to request leave tomorrow.",
            "mode": "baseline",
            "response_time_ms": 125.5,
            "needs_clarification": False,
            "clarification_question": "",
        }

        response = self.client.post("/api/generate-email/", self.payload, format="json")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["subject"], "Leave request")
        self.assertEqual(response.data["mode"], "baseline")
        self.assertEqual(response.data["response_time_ms"], 125.5)
        self.assertFalse(response.data["needs_clarification"])

    def test_rejects_missing_message(self):
        response = self.client.post(
            "/api/generate-email/", {**self.payload, "message": "  "}, format="json"
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("message", response.data["details"])

    def test_rejects_unknown_mode(self):
        response = self.client.post(
            "/api/generate-email/", {**self.payload, "mode": "creative"}, format="json"
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("mode", response.data["details"])

    @patch("email_generator.views.generate_email", side_effect=ProviderConfigurationError("Missing API key"))
    def test_reports_missing_provider_configuration(self, generate_email):
        response = self.client.post("/api/generate-email/", self.payload, format="json")

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.data["error"], "Missing API key")

    @patch("email_generator.views.generate_email", side_effect=EmailGenerationError("Provider unavailable"))
    def test_reports_provider_failure(self, generate_email):
        response = self.client.post("/api/generate-email/", self.payload, format="json")

        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.data["error"], "Provider unavailable")

    @patch(
        "email_generator.views.generate_email",
        side_effect=ProviderRateLimitError("Daily free quota reached"),
    )
    def test_reports_provider_rate_limit(self, generate_email):
        response = self.client.post("/api/generate-email/", self.payload, format="json")

        self.assertEqual(response.status_code, 429)
        self.assertIn("Daily free quota reached", response.data["error"])

    @patch(
        "email_generator.views.generate_email",
        side_effect=ProviderTimeoutError("Provider timed out"),
    )
    def test_reports_provider_timeout(self, generate_email):
        response = self.client.post("/api/generate-email/", self.payload, format="json")

        self.assertEqual(response.status_code, 504)
        self.assertEqual(response.data["error"], "Provider timed out")

    @patch(
        "email_generator.views.generate_email",
        side_effect=ProviderAuthenticationError("Provider rejected credentials"),
    )
    def test_reports_provider_authentication_error(self, generate_email):
        response = self.client.post("/api/generate-email/", self.payload, format="json")

        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.data["error"], "Provider rejected credentials")

    @patch(
        "email_generator.views.generate_email",
        side_effect=ProviderModelError("Configured model was rejected"),
    )
    def test_reports_provider_model_error(self, generate_email):
        response = self.client.post("/api/generate-email/", self.payload, format="json")

        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.data["error"], "Configured model was rejected")

    # Regression tests
    def test_regression_1_valid_json_containing_subject_and_body(self):
        # Including null clarification_question which previously broke baseline parsing
        raw_json = json.dumps(
            {
                "subject": "Project Kickoff Meeting",
                "body": "Hi everyone,\n\nWe will have our kickoff meeting tomorrow.\n\nBest,\nTeam",
                "needs_clarification": False,
                "clarification_question": None,
            }
        )
        result = parse_email_response(raw_json)
        self.assertEqual(result["subject"], "Project Kickoff Meeting")
        self.assertIn("kickoff meeting tomorrow", result["body"])
        self.assertFalse(result["needs_clarification"])
        self.assertEqual(result["clarification_question"], "")

    def test_regression_2_plain_text_with_subject_label(self):
        plain_text = (
            "Subject: Reschedule Team Sync\n\n"
            "Hi Team,\n\n"
            "Could we please reschedule our sync to Thursday?\n\n"
            "Thanks,\nAlex"
        )
        result = parse_email_response(plain_text)
        self.assertEqual(result["subject"], "Reschedule Team Sync")
        self.assertIn("Could we please reschedule", result["body"])
        self.assertIn("Thanks,\nAlex", result["body"])

    def test_regression_3_body_labels_with_different_capitalization_and_whitespace(self):
        variations = [
            "Subject: Status Update\n\nBODY: All systems are operational.",
            "Subject: Status Update\n\nbody   :   All systems are operational.",
            "Subject: Status Update\n\nEmail Body:\nAll systems are operational.",
            "Subject: Status Update\n\n**Body:**\nAll systems are operational.",
            "Subject: Status Update\n\nBody - All systems are operational.",
            "### Subject: Status Update\n\n### Body:\nAll systems are operational.",
        ]
        for text in variations:
            with self.subTest(text=text):
                result = parse_email_response(text)
                self.assertEqual(result["subject"], "Status Update")
                self.assertEqual(result["body"], "All systems are operational.")

    def test_regression_4_markdown_code_fences_around_valid_structured_output(self):
        # Code fence with language tag
        fenced_json = (
            "```json\n"
            + json.dumps({"subject": "Fenced Subject", "body": "Fenced Body"})
            + "\n```"
        )
        result1 = parse_email_response(fenced_json)
        self.assertEqual(result1["subject"], "Fenced Subject")
        self.assertEqual(result1["body"], "Fenced Body")

        # Code fence with introductory text and trailing remarks
        with_commentary = (
            "Here is the email you requested:\n"
            "```json\n"
            + json.dumps({"subject": "With Commentary", "body": "Body content here."})
            + "\n```\nHope this helps!"
        )
        result2 = parse_email_response(with_commentary)
        self.assertEqual(result2["subject"], "With Commentary")
        self.assertEqual(result2["body"], "Body content here.")

        # Plain text in code fence
        fenced_plain = "```text\nSubject: Plain In Fence\n\nBody:\nPlain text body.\n```"
        result3 = parse_email_response(fenced_plain)
        self.assertEqual(result3["subject"], "Plain In Fence")
        self.assertEqual(result3["body"], "Plain text body.")

    def test_regression_5_empty_content(self):
        for empty_val in ("", "   ", "\n\r\t", None):
            with self.subTest(empty_val=empty_val):
                with self.assertRaises(InvalidEmailResponseError) as ctx:
                    parse_email_response(empty_val)
                self.assertEqual(ctx.exception.reason, "empty_content")

    def test_regression_6_missing_subject_or_body(self):
        cases = [
            json.dumps({"body": "Only body provided"}),
            json.dumps({"subject": "Only subject provided", "body": ""}),
            json.dumps({"subject": None, "body": "Body with null subject"}),
            json.dumps({"subject": "Subject with null body", "body": None}),
            "Subject: Only subject\n\nBody:\n",
        ]
        for case in cases:
            with self.subTest(case=case):
                with self.assertRaises(InvalidEmailResponseError) as ctx:
                    parse_email_response(case)
                self.assertEqual(ctx.exception.reason, "missing_subject_or_body")

    @patch("email_generator.services.OpenAI")
    def test_regression_7_genuinely_truncated_response(self, openai_client):
        client = openai_client.return_value
        client.chat.completions.create.return_value = SimpleNamespace(
            choices=[
                SimpleNamespace(
                    finish_reason="length",
                    message=SimpleNamespace(
                        content='{"subject": "Truncated", "body": "Mid-senten'
                    ),
                )
            ]
        )
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-key"}, clear=True):
            with self.assertRaises(IncompleteGenerationError):
                generate_email(self.payload)

    @patch("email_generator.services.OpenAI")
    def test_regression_8_both_baseline_and_improved_generation_paths(self, openai_client):
        client = openai_client.return_value
        baseline_response = json.dumps(
            {
                "subject": "Baseline Subject",
                "body": "Baseline email body.",
                "needs_clarification": False,
                "clarification_question": None,
            }
        )
        improved_response = json.dumps(
            {
                "subject": "Improved Subject",
                "body": "Improved email body.",
                "needs_clarification": False,
                "clarification_question": "",
            }
        )

        for mode, expected_subj, raw_response, prompt in [
            ("baseline", "Baseline Subject", baseline_response, BASELINE_PROMPT),
            ("improved", "Improved Subject", improved_response, IMPROVED_PROMPT),
        ]:
            client.chat.completions.create.return_value = SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        finish_reason="stop",
                        message=SimpleNamespace(content=raw_response),
                    )
                ]
            )
            with patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-key"}, clear=True):
                result = generate_email({**self.payload, "mode": mode})

            self.assertEqual(result["subject"], expected_subj)
            self.assertEqual(result["mode"], mode)
            self.assertFalse(result["needs_clarification"])
            self.assertIn("response_time_ms", result)
            call_kwargs = client.chat.completions.create.call_args.kwargs
            self.assertEqual(call_kwargs["messages"][0]["content"], prompt)