import assert from "node:assert/strict";
import test from "node:test";

import type { User } from "./api";
import { publicSessionMode } from "./public-session";

const member: User = {
  id: "member-1",
  email: "member@example.com",
  group: { id: "group-1", name: "JEDI" },
  isGroupOwner: false,
  onboardingComplete: true,
};

test("keeps public actions stable while the session is loading", () => {
  assert.equal(publicSessionMode(undefined, true), "loading");
});

test("shows the dashboard action for an authenticated member", () => {
  assert.equal(publicSessionMode(member, false), "authenticated");
  assert.equal(publicSessionMode(member, true), "authenticated");
});

test("falls back to anonymous actions after an absent or failed session", () => {
  assert.equal(publicSessionMode(undefined, false), "anonymous");
});
