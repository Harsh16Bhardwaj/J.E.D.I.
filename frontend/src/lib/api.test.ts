import assert from "node:assert/strict";
import test, { afterEach } from "node:test";

import {
  apiRequest,
  ApiError,
  errorSummary,
  safeNext,
} from "./api";

const originalFetch = globalThis.fetch;

afterEach(() => {
  globalThis.fetch = originalFetch;
});

test("sends cookies and decodes JSON success", async () => {
  let request: Parameters<typeof fetch> | undefined;
  globalThis.fetch = async (...args) => {
    request = args;
    return Response.json({ id: "user-1", email: "me@example.com" });
  };

  const user = await apiRequest<{ id: string; email: string }>(
    "/api/auth/session",
  );

  assert.equal(user.email, "me@example.com");
  assert.equal(request?.[0], "/svc/ml/api/auth/session");
  assert.equal(request?.[1]?.credentials, "include");
  assert.equal(request?.[1]?.cache, "no-store");
});

test("adds JSON content type only when a body exists", async () => {
  let headers: HeadersInit | undefined;
  globalThis.fetch = async (_input, init) => {
    headers = init?.headers;
    return Response.json({ ok: true });
  };

  await apiRequest("/api/auth/login", {
    method: "POST",
    body: JSON.stringify({ email: "me@example.com", password: "secret" }),
  });

  assert.equal(new Headers(headers).get("content-type"), "application/json");
});

test("accepts a 204 response without parsing a body", async () => {
  globalThis.fetch = async () => new Response(null, { status: 204 });
  assert.equal(
    await apiRequest<void>("/api/auth/logout", { method: "POST" }),
    undefined,
  );
});

test("preserves the backend error contract and request ID", async () => {
  globalThis.fetch = async () =>
    Response.json(
      {
        error: {
          code: "CONFLICT",
          message: "Batch cannot be deleted.",
          requestId: "request-123",
          details: { reason: "protected" },
        },
      },
      { status: 409 },
    );

  await assert.rejects(
    apiRequest("/api/batches/batch-1", { method: "DELETE" }),
    (error: unknown) => {
      assert(error instanceof ApiError);
      assert.equal(error.status, 409);
      assert.equal(error.code, "CONFLICT");
      assert.equal(error.requestId, "request-123");
      assert.deepEqual(error.details, { reason: "protected" });
      return true;
    },
  );
});

test("converts non-JSON and network failures into safe messages", async () => {
  globalThis.fetch = async () =>
    new Response("<h1>proxy failure</h1>", {
      status: 502,
      headers: { "content-type": "text/html" },
    });
  await assert.rejects(apiRequest("/health/ready"), {
    message: "Request failed with status 502.",
  });

  globalThis.fetch = async () => {
    throw new Error("socket contained sensitive diagnostics");
  };
  await assert.rejects(apiRequest("/health/live"), (error: unknown) => {
    assert(error instanceof ApiError);
    assert.equal(error.code, "NETWORK_ERROR");
    assert(!error.message.includes("socket"));
    return true;
  });
});

test("safeNext accepts only local absolute paths", () => {
  assert.equal(safeNext("/batches/batch-1"), "/batches/batch-1");
  assert.equal(safeNext("//malicious.example"), "/dashboard");
  assert.equal(safeNext("https://malicious.example"), "/dashboard");
  assert.equal(safeNext(null), "/dashboard");
  assert.equal(errorSummary(new Error("hidden")), "Something unexpected went wrong.");
});

test("registration sends the invitation only with the account request", async () => {
  let request: Parameters<typeof fetch> | undefined;
  globalThis.fetch = async (...args) => {
    request = args;
    return Response.json(
      {
        id: "member-1",
        email: "friend@example.com",
        group: { id: "group-1", name: "JEDI" },
        isGroupOwner: false,
        onboardingComplete: false,
      },
      { status: 201 },
    );
  };

  await apiRequest("/api/auth/register", {
    method: "POST",
    body: JSON.stringify({
      inviteCode: "7KF2Q",
      email: "friend@example.com",
      password: "strong-password",
    }),
  });

  assert.equal(request?.[0], "/svc/ml/api/auth/register");
  assert.match(String(request?.[1]?.body), /"inviteCode":"7KF2Q"/);
  assert.equal(request?.[1]?.credentials, "include");
});

test("preserves invitation-specific backend errors", async () => {
  globalThis.fetch = async () =>
    Response.json(
      {
        error: {
          code: "INVITE_EXPIRED",
          message: "Invitation code expired.",
          requestId: "invite-request",
        },
      },
      { status: 410 },
    );

  await assert.rejects(
    apiRequest("/api/auth/register", { method: "POST" }),
    (error: unknown) => {
      assert(error instanceof ApiError);
      assert.equal(error.code, "INVITE_EXPIRED");
      assert.equal(error.status, 410);
      assert.equal(error.requestId, "invite-request");
      return true;
    },
  );
});
