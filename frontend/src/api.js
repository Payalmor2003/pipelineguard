const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000';
const REQUEST_TIMEOUT_MS = 60_000; // repo analysis can take a while (clone + embed + LLM)

async function handleResponse(res) {
  if (!res.ok) {
    let detail = `Request failed (${res.status})`;
    try {
      const body = await res.json();
      detail = body.detail || detail;
    } catch {
      // response wasn't JSON - keep the generic message
    }
    throw new Error(detail);
  }
  return res.json();
}

async function postJSON(path, body) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
  try {
    const res = await fetch(`${API_BASE}${path}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      signal: controller.signal,
    });
    return await handleResponse(res);
  } catch (err) {
    if (err.name === 'AbortError') {
      throw new Error(
        `Analysis took longer than ${REQUEST_TIMEOUT_MS / 1000}s and was cancelled. ` +
        'Try a smaller repo, or check that the backend is still running.'
      );
    }
    if (err.message === 'Failed to fetch') {
      throw new Error(
        `Could not reach the backend at ${API_BASE}. Is it running ` +
        '(uvicorn app.main:app --reload)? Check the backend terminal for errors too.'
      );
    }
    throw err;
  } finally {
    clearTimeout(timer);
  }
}

export async function analyzeCode(code, filename = 'pasted_code.py') {
  return postJSON('/analyze/code', { code, filename });
}

export async function analyzeRepo(repoUrl) {
  return postJSON('/analyze/repo', { repo_url: repoUrl });
}
