import argparse
import http.client
import json
import os
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


TEST_CASES = [
    {
        "name": "Leave request",
        "message": "Request leave for tomorrow due to personal reasons and politely ask my manager to confirm whether it can be accommodated.",
        "recipient": "My manager",
        "tone": "Professional",
        "instructions": "Keep it brief",
    },
    {
        "name": "Job application",
        "message": "Apply for a junior data analyst position. Mention my bachelor's degree in statistics, proficiency in Excel and SQL, and my interest in the role.",
        "recipient": "Hiring manager",
        "tone": "Formal",
        "instructions": "Do not add experience or qualifications I did not provide",
    },
    {
        "name": "Meeting reschedule",
        "message": "Ask to reschedule our meeting planned for May 12 at 2:00 PM because I have a conflict.",
        "recipient": "Project team",
        "tone": "Friendly",
        "instructions": "Do not suggest a specific replacement date",
    },
    {
        "name": "Apology",
        "message": "Apologize for sending the project report late because I was waiting for the final figures from the operations team.",
        "recipient": "My colleague",
        "tone": "Professional",
        "instructions": "Keep the apology sincere and concise",
    },
    {
        "name": "Project update",
        "message": "Ask the project team for the current completion percentage, progress against the launch timeline, outstanding blockers, and the owner and expected date for each blocker.",
        "recipient": "Project team",
        "tone": "Casual",
        "instructions": "Ask about progress and any blockers",
    },
]

CRITERIA = ["instructions", "tone", "structure", "meaning"]


def request_email(api_url, email_input, mode):
    request_data = {**email_input, "mode": mode}
    request = urllib.request.Request(
        api_url,
        data=json.dumps(request_data).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=100) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        details = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"API returned HTTP {error.code}: {details}") from error
    except urllib.error.URLError as error:
        raise RuntimeError(f"Could not reach the API: {error.reason}") from error
    except TimeoutError as error:
        raise RuntimeError("The API did not respond within 100 seconds.") from error
    except http.client.RemoteDisconnected as error:
        raise RuntimeError("The API connection closed before returning a response.") from error


def run_benchmark(api_url):
    results = []
    for test_case in TEST_CASES:
        email_input = {key: value for key, value in test_case.items() if key != "name"}
        case_result = {"name": test_case["name"], "input": email_input}
        for mode in ("baseline", "improved"):
            try:
                generated = request_email(api_url, email_input, mode)
                case_result[mode] = {
                    **generated,
                    "manual_evaluation": {criterion: None for criterion in CRITERIA},
                }
            except RuntimeError as error:
                case_result[mode] = {"error": str(error)}
        results.append(case_result)

    return {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "api_url": api_url,
        "method": "response_time_ms returned by the Django service",
        "results": results,
    }


def main():
    parser = argparse.ArgumentParser(description="Run five real email prompt comparisons.")
    parser.add_argument(
        "--output",
        default="benchmark_results.json",
        help="Where to write generated outputs and timings (default: benchmark_results.json)",
    )
    args = parser.parse_args()
    api_url = os.environ.get(
        "EMAIL_API_URL", "http://127.0.0.1:8000/api/generate-email/"
    )

    try:
        results = run_benchmark(api_url)
    except RuntimeError as error:
        raise SystemExit(f"Benchmark stopped without writing partial results: {error}") from error

    output_path = Path(args.output)
    output_path.write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    completed = sum(
        "subject" in result[mode]
        for result in results["results"]
        for mode in ("baseline", "improved")
    )
    print(f"Recorded {completed}/10 successful responses in {output_path.resolve()}")
    print("Review each generated email and replace its null manual_evaluation values with true or false.")


if __name__ == "__main__":
    main()