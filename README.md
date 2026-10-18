# EmailCraft

EmailCraft is a small learning project that compares two ways of prompting an AI model to draft the same email. Enter one request, generate an original and an improved version, then review both outputs and score them with a manual checklist.

## Project Objectives

- See how explicit prompt instructions affect email structure and instruction-following.
- Keep the original request, recipient, tone, and additional instructions the same for both generations.
- Measure each model call consistently and review the result rather than assuming one prompt always wins.
- Learn a small Django REST Framework API and React application without accounts, storage, or email sending.

## Features

- Required email purpose/message, optional recipient and instructions, and four selectable tones.
- Separate baseline and improved generations with independent loading and error states.
- Subject and body outputs, copy-to-clipboard controls, and provider response time.
- Responsive side-by-side results that stack on smaller screens.
- A four-item manual evaluation checklist and scores out of four for each output.
- Five repeatable real-provider benchmark cases; generated content and timings are saved only after successful API calls.

## Technology Stack

- Backend: Python, Django, Django REST Framework, OpenAI-compatible SDK for OpenRouter, `python-dotenv`, `django-cors-headers`.
- Frontend: JavaScript, React, Vite, Tailwind CSS, Lucide icons, browser Fetch and Clipboard APIs.
- No database is used. Generated emails are not stored by the app.

## Folder Structure

```text
backend/
  config/                  Django settings and application entry points
    __init__.py            Marks config as a Python package
  email_generator/         Request validation, API view, prompts, provider service, tests
    __init__.py            Marks the API app as a Python package
  .env.example             Backend environment variable template
  manage.py                Django command entry point
  requirements.txt         Python dependencies
  run_benchmark.py         Five-case API benchmark runner
  benchmark_results.json   Generated locally by the benchmark; not committed
frontend/
  src/
    components/            Form, result card, and manual comparison checklist
    App.jsx                Page state and backend requests
    index.css              Tailwind import and app styling
    main.jsx               React browser entry point
  .env.example             Frontend API URL template
  index.html               Vite HTML document
  package.json             JavaScript dependencies and commands
  package-lock.json        Locks exact JavaScript dependency versions
  vite.config.js           Vite, React, and Tailwind plugin setup
README.md                  Setup, API, learning notes, and benchmark results
.gitignore                 Local secrets, environments, and generated files
```

### File Responsibilities

| File | Responsibility |
| --- | --- |
| `backend/manage.py` | Starts Django management commands. |
| `backend/config/__init__.py` | Marks Django's configuration folder as a Python package. |
| `backend/config/settings.py` | Loads environment variables and configures Django, REST Framework, and local CORS. |
| `backend/config/urls.py` | Connects the `/api/` route to the email app. |
| `backend/config/wsgi.py`, `backend/config/asgi.py` | Standard Django server entry points. |
| `backend/email_generator/apps.py` | Registers the API app with Django. |
| `backend/email_generator/__init__.py` | Marks the API folder as a Python package. |
| `backend/email_generator/serializers.py` | Validates message, recipient, tone, instructions, and generation mode. |
| `backend/email_generator/services.py` | Holds both prompts, calls the AI provider, checks its response, and measures elapsed time. |
| `backend/email_generator/views.py` | Keeps the HTTP endpoint small: validate, call the service, return a status and JSON. |
| `backend/email_generator/urls.py` | Defines the email-generation endpoint path. |
| `backend/email_generator/tests.py` | Tests validation, successful responses, and provider error responses without making paid API calls. |
| `backend/requirements.txt` | Lists Python packages needed by the backend. |
| `backend/.env.example` | Documents backend environment variables without containing a real key. |
| `backend/run_benchmark.py` | Runs five scenarios against both prompts and writes actual responses and timings to JSON. |
| `frontend/index.html` | Supplies the browser document and React mount point. |
| `frontend/src/main.jsx` | Loads CSS and mounts the React app. |
| `frontend/src/App.jsx` | Owns form, result, error, and checklist state; sends both Fetch requests. |
| `frontend/src/components/EmailForm.jsx` | Renders the input fields and the two generation buttons. |
| `frontend/src/components/EmailResult.jsx` | Renders one generated email, its response time, loading/error state, and Copy action. |
| `frontend/src/components/ComparisonPanel.jsx` | Renders the manual checklist and calculates each score from checked items. |
| `frontend/src/index.css` | Imports Tailwind and defines the responsive page styles. |
| `frontend/package.json` | Lists frontend dependencies and development/build commands. |
| `frontend/package-lock.json` | Records exact dependency versions for repeatable npm installs. |
| `frontend/vite.config.js` | Enables Vite's React and Tailwind plugins. |
| `frontend/.env.example` | Documents the browser-safe API URL. Never put provider keys here. |
| `backend/benchmark_results.json` | Local benchmark output containing real model text, response times, and manual review fields; generated when the benchmark runs and ignored by Git. |
| `.gitignore` | Excludes local environment files, virtual environments, build output, and benchmark results. |

## Prerequisites

- Python 3.10 or newer and `venv`.
- Node.js 20 or newer and npm.
- An API key for an OpenAI-compatible API. The key stays in the backend environment.

## Setup

### Backend

From the project root:

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
```

Set `OPENROUTER_API_KEY` in `backend/.env`. The backend selects OpenRouter's `openrouter/free` model router in code; no model setting is needed. The key is read only by Django and is never sent to React.

Start Django:

```bash
python manage.py runserver
```

The API is available at `http://127.0.0.1:8000/api/generate-email/`.

### Frontend

In a second terminal from the project root:

```bash
cd frontend
npm install
cp .env.example .env
npm run dev
```

Open the Vite URL printed in the terminal (normally `http://localhost:5173`). `VITE_API_URL` can point the browser at a different backend URL. Django CORS permits localhost and 127.0.0.1 on Vite's default port; set `CORS_ALLOWED_ORIGINS` in `backend/.env` when using a different origin.

## API

`POST /api/generate-email/` accepts JSON. The `mode` field must be `baseline` or `improved`.

```json
{
  "message": "Requesting leave for tomorrow due to personal work",
  "recipient": "My manager",
  "tone": "Professional",
  "instructions": "Keep it brief",
  "mode": "improved"
}
```

A successful response contains `subject`, `body`, `mode`, `response_time_ms`, `needs_clarification`, and `clarification_question`. If the model cannot draft accurately from an unclear request, it returns a specific question and the interface suppresses subject/body and Copy rather than presenting a guessed email. The service measures from immediately before the provider request through response parsing, using Python's monotonic performance clock. Invalid inputs return HTTP 400, missing local configuration returns HTTP 503, rejected provider credentials or model settings return HTTP 502, exhausted OpenRouter free quota returns HTTP 429, provider timeouts return HTTP 504, and malformed or incomplete output returns HTTP 502. Each error includes a specific, user-readable `error` message.

## Prompt Comparison

Both modes receive the same request, recipient, tone, and additional instructions. The baseline prompt asks for an email in the selected tone with a subject and body. The improved prompt additionally emphasizes careful instruction-following, consistent tone, preserving facts and intent, not inventing details, consistent structure, concise wording, and readable output. Both ask for JSON and both instruct the model to ask a concise clarification question instead of guessing when the request is unclear. The baseline remains a reasonable prompt, not a deliberately broken straw man.

## Testing Method

Run the backend tests from `backend/` with its virtual environment active:

```bash
python manage.py test email_generator
```

The thirty-one automated tests cover request validation, API/provider errors, OpenRouter configuration, prompt selection and user-field forwarding, clarification behavior, full multiline body preservation, JSON/fenced/labelled/multipart response parsing, empty and malformed output, provider truncation and other incomplete finish reasons, identical benchmark inputs for both modes, and rate-limit/timeout/authentication/model error handling. Provider calls are mocked in these tests, so they do not measure writing quality or live latency.

For a real comparison, start Django with a configured OpenRouter key, then run this from `backend/`:

```bash
python run_benchmark.py
```

This sends the same five detailed inputs to both modes (ten provider requests): a leave request with its reason and confirmation request, a job application with stated qualifications, a reschedule request with the original date, an apology with its context, and a project update with four requested details. It writes actual generated subjects, bodies, clarification responses, backend response times, and per-request API errors to `backend/benchmark_results.json`. It continues after provider failures, so completed responses remain available. The output is git-ignored because it contains request text and model output. Each successful output includes an empty `manual_evaluation` checklist; inspect it and replace each `null` with `true` or `false`. The backend uses a 45-second provider timeout, a 2,000-token output budget, rejects non-complete finish reasons, and supports structured JSON, outer code-fenced JSON, and labelled subject/body output. The browser waits up to 50 seconds. The free router's underlying model can change over time; these timings are not a controlled comparison.

## Before-and-After Results

The latest run recorded three successful responses out of ten; seven calls returned HTTP 502 before provider-specific errors were mapped. A later live request confirmed that OpenRouter's free-model daily quota was exhausted; the endpoint now reports this condition as HTTP 429 with reset/credit guidance. Only the leave-request pair completed, along with the baseline job-application response. The improved leave response preserved the reason and request for confirmation and used a neutral greeting. The baseline response preserved the reason and confirmation request but invented name placeholders. The job-application baseline included the supplied degree and skills but added claims about the applicant's analytical foundation and career goals. This small, provider-limited sample does not establish that the improved prompt is generally better. Manual checklist ratings have not been entered, so scores remain pending.

| Test case | Mode | Actual output excerpt | Manual checklist (4) | Response time |
| --- | --- | --- | --- | --- |
| Leave request | Baseline | Preserved reason and confirmation request, but used `[Manager's Name]` and `[Your Name]` placeholders | Pending human review | 18630.97 ms |
| Leave request | Improved | “Dear Manager, I am writing to request leave for tomorrow due to personal reasons. Please let me know if this can be accommodated. Thank you.” | Pending human review | 3484.28 ms |
| Job application | Baseline | Included the degree and Excel/SQL skills, but added claims about an analytical foundation and career goals | Pending human review | 6011.31 ms |
| Job application | Improved | HTTP 502; no output returned | Not evaluated | Not measured |
| Meeting rescheduling | Baseline and improved | HTTP 502; no output returned | Not evaluated | Not measured |
| Apology | Baseline and improved | HTTP 502; no output returned | Not evaluated | Not measured |
| Project update request | Baseline and improved | HTTP 502; no output returned | Not evaluated | Not measured |

The app does not assume that improved prompting always produces a better result. The on-screen scores show only the user's manual checklist selections, not objective AI accuracy.

## Limitations and Future Improvements

- Output quality depends on the model selected by OpenRouter's free router; prompts do not guarantee factual accuracy.
- Manual evaluation is subjective and should not be treated as an accuracy benchmark.
- The app has no accounts or storage. Refreshing the page clears generated output and checklist selections.
- The benchmark makes ten provider calls. OpenRouter's free router may have availability or rate limits, and the selected free model can change.
- Future work could compare multiple reviewers, add a local response export, or support another provider behind the same small service function.

## Learning Notes

The request path is deliberately short: the React form sends JSON to the Django view; the serializer checks the input; the service selects one named prompt and calls the model; the view returns the result. React stores each mode's result independently so either one can be regenerated without replacing the other. The checklist is browser state only: each score is the count of selected criteria, and it is kept separate from provider output so it cannot be mistaken for an AI confidence score.# ai-week-4
