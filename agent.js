/**
 * bunq Voice Agent — LLM that understands user input and calls the right bunq API.
 * Covers all available bunq API endpoints.
 *
 * Usage:
 *   npm install
 *   node agent.js
 *
 * Requires:
 *   - .env with BUNQ_API_KEY and ANTHROPIC_API_KEY filled in
 *   - .bunq-session.json  (created by running: node test_local_api.js)
 */

import Anthropic from "@anthropic-ai/sdk";
import { readFileSync, existsSync } from "fs";
import { createSign } from "crypto";
import * as readline from "readline";

// =============================================================================
// CONFIG
// =============================================================================

const BUNQ_BASE = "https://public-api.sandbox.bunq.com/v1";
const SESSION_FILE = ".bunq-session.json";

function loadEnv() {
  if (!existsSync(".env")) return {};
  return Object.fromEntries(
    readFileSync(".env", "utf8")
      .split("\n")
      .filter((l) => l.includes("=") && !l.startsWith("#"))
      .map((l) => {
        const [k, ...rest] = l.split("=");
        return [k.trim(), rest.join("=").trim()];
      })
  );
}

const env = loadEnv();
const ANTHROPIC_API_KEY = env.ANTHROPIC_API_KEY || process.env.ANTHROPIC_API_KEY;
const LLM_MODEL = env.LLM_MODEL || "claude-sonnet-4-6";

// =============================================================================
// BUNQ HTTP CLIENT
// =============================================================================

function loadSession() {
  if (!existsSync(SESSION_FILE))
    throw new Error("No session found. Run: node test_local_api.js first.");
  const state = JSON.parse(readFileSync(SESSION_FILE, "utf8"));
  if (!state.sessionToken || !state.userId)
    throw new Error("Invalid session file. Run: node test_local_api.js first.");
  return state;
}

let reqCount = 0;

function sign(body, privateKey) {
  const s = createSign("SHA256");
  s.update(body);
  return s.sign(privateKey, "base64");
}

async function bunq(method, path, body, sessionToken, privateKey) {
  const bodyStr = body ? JSON.stringify(body) : "";
  const res = await fetch(`${BUNQ_BASE}${path}`, {
    method,
    headers: {
      "Cache-Control": "no-cache",
      "User-Agent": "bunq-voice-agent/1.0",
      "X-Bunq-Client-Request-Id": `agent-${++reqCount}-${Date.now()}`,
      "X-Bunq-Geolocation": "0 0 0 0 000",
      "X-Bunq-Language": "en_US",
      "X-Bunq-Region": "en_US",
      "X-Bunq-Client-Authentication": sessionToken,
      ...(bodyStr ? { "Content-Type": "application/json" } : {}),
      ...(privateKey && bodyStr ? { "X-Bunq-Client-Signature": sign(bodyStr, privateKey) } : {}),
    },
    ...(bodyStr ? { body: bodyStr } : {}),
  });
  const json = await res.json();
  if (res.status < 200 || res.status >= 300) {
    const msg = json?.Error?.[0]?.error_description || JSON.stringify(json);
    throw new Error(`bunq ${method} ${path} → ${res.status}: ${msg}`);
  }
  return json;
}

// Shorthand helpers
const get  = (path, ctx) => bunq("GET",    path, null, ctx.sessionToken);
const post = (path, body, ctx) => bunq("POST",   path, body, ctx.sessionToken, ctx.privateKey);
const put  = (path, body, ctx) => bunq("PUT",    path, body, ctx.sessionToken, ctx.privateKey);
const del  = (path, ctx) => bunq("DELETE", path, null, ctx.sessionToken);

// =============================================================================
// TOOL IMPLEMENTATIONS
// =============================================================================

// ── USER ─────────────────────────────────────────────────────────────────────

async function getUserProfile(ctx) {
  const res = await get(`/user`, ctx);
  const u = res.Response?.find((r) => r.UserPerson || r.UserCompany);
  const user = u?.UserPerson || u?.UserCompany;
  return {
    id: user?.id,
    name: user?.display_name || user?.name,
    email: user?.alias?.find((a) => a.type === "EMAIL")?.value,
    phone: user?.alias?.find((a) => a.type === "PHONE_NUMBER")?.value,
    status: user?.status,
    plan: user?.billing_contract?.[0]?.BillingContractSubscription?.subscription_type,
  };
}

// ── MONETARY ACCOUNTS ─────────────────────────────────────────────────────────

function fmtAccount(acct) {
  return {
    id: acct.id,
    description: acct.description,
    balance: `${acct.balance?.value} ${acct.balance?.currency}`,
    iban: acct.alias?.find((a) => a.type === "IBAN")?.value,
    status: acct.status,
    type: acct.MonetaryAccountType || "bank",
  };
}

async function getBalance(ctx) {
  const res = await get(`/user/${ctx.userId}/monetary-account`, ctx);
  return (res.Response || [])
    .map((r) => r.MonetaryAccountBank || r.MonetaryAccountSavings || r.MonetaryAccountJoint)
    .filter(Boolean)
    .map(fmtAccount);
}

async function getAccount(ctx, { account_id }) {
  const res = await get(`/user/${ctx.userId}/monetary-account/${account_id}`, ctx);
  const acct = res.Response?.[0];
  const a = acct?.MonetaryAccountBank || acct?.MonetaryAccountSavings;
  return a ? fmtAccount(a) : null;
}

async function listSavingsAccounts(ctx) {
  const res = await get(`/user/${ctx.userId}/monetary-account-savings`, ctx);
  return (res.Response || []).map((r) => r.MonetaryAccountSavings).filter(Boolean).map(fmtAccount);
}

async function listJointAccounts(ctx) {
  const res = await get(`/user/${ctx.userId}/monetary-account-joint`, ctx);
  return (res.Response || []).map((r) => r.MonetaryAccountJoint).filter(Boolean).map(fmtAccount);
}

async function createAccount(ctx, { description }) {
  const res = await post(
    `/user/${ctx.userId}/monetary-account-bank`,
    { currency: "EUR", description },
    ctx
  );
  return { created: true, id: res.Response?.[0]?.Id?.id, description };
}

async function updateAccount(ctx, { account_id, description, close }) {
  const body = {};
  if (description) body.description = description;
  if (close) body.status = "CANCELLED";
  await put(`/user/${ctx.userId}/monetary-account-bank/${account_id}`, body, ctx);
  return { updated: true, account_id, changes: body };
}

// ── PAYMENTS ──────────────────────────────────────────────────────────────────

function fmtPayment(p) {
  return {
    id: p.id,
    amount: `${p.amount?.value} ${p.amount?.currency}`,
    description: p.description,
    type: p.type,
    counterparty: p.counterparty_alias?.display_name,
    counterparty_iban: p.counterparty_alias?.value,
    balance_after: p.balance_after_mutation
      ? `${p.balance_after_mutation.value} ${p.balance_after_mutation.currency}`
      : undefined,
    created: p.created,
  };
}

async function listPayments(ctx, { count = 10, account_id } = {}) {
  const id = account_id || ctx.accountId;
  const res = await get(`/user/${ctx.userId}/monetary-account/${id}/payment?count=${count}`, ctx);
  return (res.Response || []).map((r) => r.Payment).filter(Boolean).map(fmtPayment);
}

async function getPayment(ctx, { payment_id, account_id }) {
  const id = account_id || ctx.accountId;
  const res = await get(`/user/${ctx.userId}/monetary-account/${id}/payment/${payment_id}`, ctx);
  const p = res.Response?.[0]?.Payment;
  return p ? fmtPayment(p) : null;
}

async function sendPayment(ctx, { amount, recipient_email, description }) {
  const res = await post(
    `/user/${ctx.userId}/monetary-account/${ctx.accountId}/payment`,
    {
      amount: { value: amount, currency: "EUR" },
      counterparty_alias: { type: "EMAIL", value: recipient_email, name: recipient_email },
      description,
    },
    ctx
  );
  return { sent: true, payment_id: res.Response?.[0]?.Id?.id, amount, recipient_email };
}

async function sendPaymentBatch(ctx, { payments }) {
  // payments = [{ amount, recipient_email, description }]
  const res = await post(
    `/user/${ctx.userId}/monetary-account/${ctx.accountId}/payment-batch`,
    {
      payments: payments.map((p) => ({
        amount: { value: p.amount, currency: "EUR" },
        counterparty_alias: { type: "EMAIL", value: p.recipient_email, name: p.recipient_email },
        description: p.description,
      })),
    },
    ctx
  );
  return { sent: true, batch_id: res.Response?.[0]?.Id?.id, count: payments.length };
}

// ── DRAFT PAYMENTS ────────────────────────────────────────────────────────────

async function createDraftPayment(ctx, { amount, recipient_email, description }) {
  const res = await post(
    `/user/${ctx.userId}/monetary-account/${ctx.accountId}/draft-payment`,
    {
      number_of_required_accepts: 1,
      entries: [
        {
          amount: { value: amount, currency: "EUR" },
          counterparty_alias: { type: "EMAIL", value: recipient_email, name: recipient_email },
          description,
        },
      ],
    },
    ctx
  );
  const d = res.Response?.[0]?.DraftPayment;
  return { draft_id: d?.id, status: d?.status, amount, recipient_email, description };
}

async function listDraftPayments(ctx) {
  const res = await get(
    `/user/${ctx.userId}/monetary-account/${ctx.accountId}/draft-payment`,
    ctx
  );
  return (res.Response || []).map((r) => r.DraftPayment).filter(Boolean).map((d) => ({
    id: d.id,
    status: d.status,
    entries: d.entries?.map((e) => ({
      amount: `${e.amount?.value} ${e.amount?.currency}`,
      recipient: e.counterparty_alias?.display_name,
      description: e.description,
    })),
  }));
}

async function getDraftPayment(ctx, { draft_id }) {
  const res = await get(
    `/user/${ctx.userId}/monetary-account/${ctx.accountId}/draft-payment/${draft_id}`,
    ctx
  );
  const d = res.Response?.[0]?.DraftPayment;
  return d ? { id: d.id, status: d.status, entries: d.entries } : null;
}

async function confirmDraftPayment(ctx, { draft_id }) {
  await put(
    `/user/${ctx.userId}/monetary-account/${ctx.accountId}/draft-payment/${draft_id}`,
    { status: "ACCEPTED" },
    ctx
  );
  return { confirmed: true, draft_id };
}

async function cancelDraftPayment(ctx, { draft_id }) {
  await put(
    `/user/${ctx.userId}/monetary-account/${ctx.accountId}/draft-payment/${draft_id}`,
    { status: "CANCELLED" },
    ctx
  );
  return { cancelled: true, draft_id };
}

// ── SCHEDULED PAYMENTS ────────────────────────────────────────────────────────

async function createScheduledPayment(ctx, { amount, recipient_email, description, start_date, recurrence }) {
  const res = await post(
    `/user/${ctx.userId}/monetary-account/${ctx.accountId}/schedule-payment`,
    {
      payment: {
        amount: { value: amount, currency: "EUR" },
        counterparty_alias: { type: "EMAIL", value: recipient_email, name: recipient_email },
        description,
      },
      schedule: {
        time_start: start_date,
        recurrence_unit: recurrence.toUpperCase(), // ONCE | DAILY | WEEKLY | MONTHLY | YEARLY
        recurrence_size: 1,
      },
    },
    ctx
  );
  return { created: true, schedule_id: res.Response?.[0]?.Id?.id, amount, recurrence };
}

async function listScheduledPayments(ctx) {
  const res = await get(
    `/user/${ctx.userId}/monetary-account/${ctx.accountId}/schedule-payment`,
    ctx
  );
  return (res.Response || []).map((r) => r.SchedulePayment).filter(Boolean).map((s) => ({
    id: s.id,
    status: s.status,
    payment: s.payment,
    schedule: s.schedule,
  }));
}

async function cancelScheduledPayment(ctx, { schedule_id }) {
  await put(
    `/user/${ctx.userId}/monetary-account/${ctx.accountId}/schedule-payment/${schedule_id}`,
    { status: "CANCELLED" },
    ctx
  );
  return { cancelled: true, schedule_id };
}

// ── REQUEST INQUIRIES (outgoing — you ask someone to pay you) ─────────────────

async function requestMoney(ctx, { amount, recipient_email, description }) {
  const res = await post(
    `/user/${ctx.userId}/monetary-account/${ctx.accountId}/request-inquiry`,
    {
      amount_inquired: { value: amount, currency: "EUR" },
      counterparty_alias: { type: "EMAIL", value: recipient_email, name: recipient_email },
      description,
      allow_bunqme: true,
    },
    ctx
  );
  const r = res.Response?.[0]?.RequestInquiry;
  return { request_id: r?.id, status: r?.status, amount, recipient_email };
}

async function listRequestInquiries(ctx) {
  const res = await get(
    `/user/${ctx.userId}/monetary-account/${ctx.accountId}/request-inquiry`,
    ctx
  );
  return (res.Response || []).map((r) => r.RequestInquiry).filter(Boolean).map((r) => ({
    id: r.id,
    status: r.status,
    amount: `${r.amount_inquired?.value} ${r.amount_inquired?.currency}`,
    description: r.description,
    counterparty: r.counterparty_alias?.display_name,
  }));
}

async function getRequestInquiry(ctx, { request_id }) {
  const res = await get(
    `/user/${ctx.userId}/monetary-account/${ctx.accountId}/request-inquiry/${request_id}`,
    ctx
  );
  return res.Response?.[0]?.RequestInquiry || null;
}

async function revokeRequestInquiry(ctx, { request_id }) {
  await put(
    `/user/${ctx.userId}/monetary-account/${ctx.accountId}/request-inquiry/${request_id}`,
    { status: "REVOKED" },
    ctx
  );
  return { revoked: true, request_id };
}

async function createRequestInquiryBatch(ctx, { recipients }) {
  // recipients = [{ email, amount, description }]
  const res = await post(
    `/user/${ctx.userId}/monetary-account/${ctx.accountId}/request-inquiry-batch`,
    {
      request_inquiries: recipients.map((r) => ({
        amount_inquired: { value: r.amount, currency: "EUR" },
        counterparty_alias: { type: "EMAIL", value: r.email, name: r.email },
        description: r.description,
        allow_bunqme: true,
      })),
      total_amount_inquired: {
        value: recipients.reduce((s, r) => (s + parseFloat(r.amount)), 0).toFixed(2),
        currency: "EUR",
      },
    },
    ctx
  );
  return { created: true, count: recipients.length };
}

// ── REQUEST RESPONSES (incoming — someone asks YOU to pay them) ───────────────

async function listRequestResponses(ctx) {
  const res = await get(
    `/user/${ctx.userId}/monetary-account/${ctx.accountId}/request-response`,
    ctx
  );
  return (res.Response || []).map((r) => r.RequestResponse).filter(Boolean).map((r) => ({
    id: r.id,
    status: r.status,
    amount: `${r.amount_inquired?.value} ${r.amount_inquired?.currency}`,
    description: r.description,
    from: r.counterparty_alias?.display_name,
  }));
}

async function acceptRequest(ctx, { request_response_id, amount }) {
  const res = await put(
    `/user/${ctx.userId}/monetary-account/${ctx.accountId}/request-response/${request_response_id}`,
    {
      amount_responded: { value: amount, currency: "EUR" },
      status: "ACCEPTED",
    },
    ctx
  );
  return { accepted: true, request_response_id };
}

async function rejectRequest(ctx, { request_response_id }) {
  await put(
    `/user/${ctx.userId}/monetary-account/${ctx.accountId}/request-response/${request_response_id}`,
    { status: "REJECTED" },
    ctx
  );
  return { rejected: true, request_response_id };
}

// ── CARDS ─────────────────────────────────────────────────────────────────────

function fmtCard(c) {
  return {
    id: c.id,
    type: c.type,
    status: c.status,
    second_line: c.second_line,
    card_limit: c.card_limit ? `${c.card_limit.value} ${c.card_limit.currency}` : null,
    card_limit_atm: c.card_limit_atm ? `${c.card_limit_atm.value} ${c.card_limit_atm.currency}` : null,
  };
}

async function listCards(ctx) {
  const res = await get(`/user/${ctx.userId}/card`, ctx);
  return (res.Response || []).map((r) => r.CardDebit || r.Card).filter(Boolean).map(fmtCard);
}

async function getCard(ctx, { card_id }) {
  const res = await get(`/user/${ctx.userId}/card/${card_id}`, ctx);
  const c = res.Response?.[0]?.CardDebit || res.Response?.[0]?.Card;
  return c ? fmtCard(c) : null;
}

async function updateCard(ctx, { card_id, status, spending_limit_eur, atm_limit_eur }) {
  const body = {};
  if (status) body.status = status;
  if (spending_limit_eur) body.card_limit = { value: spending_limit_eur, currency: "EUR" };
  if (atm_limit_eur) body.card_limit_atm = { value: atm_limit_eur, currency: "EUR" };
  await put(`/user/${ctx.userId}/card/${card_id}`, body, ctx);
  return { updated: true, card_id, changes: body };
}

async function listCardTransactions(ctx, { account_id, count = 25 } = {}) {
  const id = account_id || ctx.accountId;
  const res = await get(
    `/user/${ctx.userId}/monetary-account/${id}/mastercard-action?count=${count}`,
    ctx
  );
  return (res.Response || []).map((r) => r.MasterCardAction).filter(Boolean).map((m) => ({
    id: m.id,
    amount: `${m.amount_local?.value} ${m.amount_local?.currency}`,
    description: m.description,
    merchant: m.merchant_name,
    city: m.city,
    status: m.authorisation_status,
    created: m.created,
  }));
}

async function listCardNames(ctx) {
  const res = await get(`/user/${ctx.userId}/card-name`, ctx);
  return (res.Response || []).map((r) => r.CardName?.possible_card_name_array).flat().filter(Boolean);
}

// ── BUNQ.ME TABS ──────────────────────────────────────────────────────────────

async function createBunqmeTab(ctx, { amount, description, redirect_url }) {
  const body = {
    status: "OPENED",
    bunqme_tab_entry: {
      amount_inquired: { value: amount, currency: "EUR" },
      description,
      ...(redirect_url ? { redirect_url } : {}),
    },
  };
  const res = await post(
    `/user/${ctx.userId}/monetary-account/${ctx.accountId}/bunqme-tab`,
    body,
    ctx
  );
  const tab = res.Response?.[0]?.BunqMeTab;
  return {
    tab_id: tab?.id,
    share_url: tab?.bunqme_tab_entry?.bunqme_url,
    amount,
    description,
  };
}

async function getBunqmeTab(ctx, { tab_id }) {
  const res = await get(
    `/user/${ctx.userId}/monetary-account/${ctx.accountId}/bunqme-tab/${tab_id}`,
    ctx
  );
  const tab = res.Response?.[0]?.BunqMeTab;
  return tab
    ? {
        id: tab.id,
        status: tab.status,
        amount: `${tab.bunqme_tab_entry?.amount_inquired?.value} ${tab.bunqme_tab_entry?.amount_inquired?.currency}`,
        description: tab.bunqme_tab_entry?.description,
        share_url: tab.bunqme_tab_entry?.bunqme_url,
      }
    : null;
}

async function listBunqmeTabs(ctx) {
  const res = await get(
    `/user/${ctx.userId}/monetary-account/${ctx.accountId}/bunqme-tab`,
    ctx
  );
  return (res.Response || []).map((r) => r.BunqMeTab).filter(Boolean).map((t) => ({
    id: t.id,
    status: t.status,
    amount: `${t.bunqme_tab_entry?.amount_inquired?.value} ${t.bunqme_tab_entry?.amount_inquired?.currency}`,
    description: t.bunqme_tab_entry?.description,
  }));
}

async function cancelBunqmeTab(ctx, { tab_id }) {
  await put(
    `/user/${ctx.userId}/monetary-account/${ctx.accountId}/bunqme-tab/${tab_id}`,
    { status: "CANCELLED" },
    ctx
  );
  return { cancelled: true, tab_id };
}

// ── WEBHOOKS ──────────────────────────────────────────────────────────────────

async function listWebhooks(ctx) {
  const res = await get(`/user/${ctx.userId}/notification-filter-url`, ctx);
  return (res.Response || []).map((r) => r.NotificationFilterUrl).filter(Boolean);
}

async function setWebhooks(ctx, { webhook_url, categories }) {
  // categories: array of strings e.g. ["PAYMENT", "MUTATION"]
  await post(
    `/user/${ctx.userId}/notification-filter-url`,
    {
      notification_filters: categories.map((c) => ({
        category: c,
        notification_target: webhook_url,
      })),
    },
    ctx
  );
  return { registered: true, webhook_url, categories };
}

async function clearWebhooks(ctx) {
  await post(`/user/${ctx.userId}/notification-filter-url`, { notification_filters: [] }, ctx);
  return { cleared: true };
}

async function listWebhookFailures(ctx) {
  const res = await get(`/user/${ctx.userId}/notification-filter-failure`, ctx);
  return (res.Response || []).map((r) => r.NotificationFilterFailure).filter(Boolean);
}

async function retryWebhookFailure(ctx, { failure_id }) {
  await post(
    `/user/${ctx.userId}/notification-filter-failure`,
    { notification_filter_failed_ids: String(failure_id) },
    ctx
  );
  return { retried: true, failure_id };
}

// ── OAUTH ─────────────────────────────────────────────────────────────────────

async function listOauthClients(ctx) {
  const res = await get(`/user/${ctx.userId}/oauth-client`, ctx);
  return (res.Response || []).map((r) => r.OauthClient).filter(Boolean).map((c) => ({
    id: c.id,
    status: c.status,
    client_id: c.client_id,
  }));
}

async function createOauthClient(ctx) {
  const res = await post(`/user/${ctx.userId}/oauth-client`, { status: "ACTIVE" }, ctx);
  const c = res.Response?.[0]?.OauthClient;
  return { id: c?.id, client_id: c?.client_id, client_secret: c?.client_secret };
}

// ── EVENTS ────────────────────────────────────────────────────────────────────

async function getEvents(ctx, { count = 25 } = {}) {
  const res = await get(`/user/${ctx.userId}/event?count=${count}`, ctx);
  return (res.Response || []).map((r) => r.Event).filter(Boolean).map((e) => ({
    id: e.id,
    type: e.type,
    action: e.action,
    created: e.created,
  }));
}

// ── SANDBOX ───────────────────────────────────────────────────────────────────

async function sandboxTopup(ctx, { amount = "500.00" } = {}) {
  const res = await post(
    `/user/${ctx.userId}/monetary-account/${ctx.accountId}/request-inquiry`,
    {
      amount_inquired: { value: amount, currency: "EUR" },
      counterparty_alias: { type: "EMAIL", value: "sugardaddy@bunq.com", name: "Sugar Daddy" },
      description: "Sandbox top-up",
      allow_bunqme: false,
    },
    ctx
  );
  return { topped_up: true, amount };
}

// =============================================================================
// TOOL DEFINITIONS  (what Claude sees)
// =============================================================================

const TOOLS = [
  // ── USER ───────────────────────────────────────────────────────────────────
  {
    name: "get_user_profile",
    description: "Get the user's profile: name, email, phone, subscription plan, and account status.",
    input_schema: { type: "object", properties: {}, required: [] },
  },

  // ── MONETARY ACCOUNTS ──────────────────────────────────────────────────────
  {
    name: "get_balance",
    description:
      "Get all bank accounts with their current balances and IBANs. Use for 'what's my balance', 'how much do I have', 'show me my accounts'.",
    input_schema: { type: "object", properties: {}, required: [] },
  },
  {
    name: "get_account",
    description: "Get details of a specific account by its ID.",
    input_schema: {
      type: "object",
      properties: {
        account_id: { type: "number", description: "The monetary account ID" },
      },
      required: ["account_id"],
    },
  },
  {
    name: "list_savings_accounts",
    description: "List savings and auto-save accounts only.",
    input_schema: { type: "object", properties: {}, required: [] },
  },
  {
    name: "list_joint_accounts",
    description: "List joint accounts shared with another user.",
    input_schema: { type: "object", properties: {}, required: [] },
  },
  {
    name: "create_account",
    description: "Create a new checking account.",
    input_schema: {
      type: "object",
      properties: {
        description: { type: "string", description: "Name/description for the new account" },
      },
      required: ["description"],
    },
  },
  {
    name: "update_account",
    description: "Rename an account or close it.",
    input_schema: {
      type: "object",
      properties: {
        account_id: { type: "number", description: "Account ID to update" },
        description: { type: "string", description: "New account name" },
        close: { type: "boolean", description: "Set true to close/cancel the account" },
      },
      required: ["account_id"],
    },
  },

  // ── PAYMENTS ───────────────────────────────────────────────────────────────
  {
    name: "list_payments",
    description:
      "List recent payments and transactions. Use for 'show recent transactions', 'what did I spend', 'payment history'.",
    input_schema: {
      type: "object",
      properties: {
        count: { type: "number", description: "How many payments to retrieve (default 10, max 200)" },
        account_id: { type: "number", description: "Account ID (uses default account if omitted)" },
      },
      required: [],
    },
  },
  {
    name: "get_payment",
    description: "Get the full details of a single payment by its ID.",
    input_schema: {
      type: "object",
      properties: {
        payment_id: { type: "number", description: "Payment ID" },
        account_id: { type: "number", description: "Account ID (uses default if omitted)" },
      },
      required: ["payment_id"],
    },
  },
  {
    name: "send_payment",
    description:
      "Send an immediate payment. WARNING: money moves instantly. " +
      "For voice flows prefer create_draft_payment + confirm_draft_payment instead. " +
      "Only use this for trusted, pre-confirmed transactions.",
    input_schema: {
      type: "object",
      properties: {
        amount: { type: "string", description: "Amount in EUR e.g. '10.00'" },
        recipient_email: { type: "string", description: "Recipient email address" },
        description: { type: "string", description: "Payment description" },
      },
      required: ["amount", "recipient_email", "description"],
    },
  },
  {
    name: "send_payment_batch",
    description: "Send multiple payments at once in a single batch.",
    input_schema: {
      type: "object",
      properties: {
        payments: {
          type: "array",
          description: "List of payments to send",
          items: {
            type: "object",
            properties: {
              amount: { type: "string", description: "Amount in EUR" },
              recipient_email: { type: "string" },
              description: { type: "string" },
            },
            required: ["amount", "recipient_email", "description"],
          },
        },
      },
      required: ["payments"],
    },
  },

  // ── DRAFT PAYMENTS ─────────────────────────────────────────────────────────
  {
    name: "create_draft_payment",
    description:
      "Create a draft payment. Money does NOT move yet — user must confirm. " +
      "ALWAYS use this first when a user wants to send money. Show them the details, then confirm.",
    input_schema: {
      type: "object",
      properties: {
        amount: { type: "string", description: "Amount in EUR e.g. '25.00'" },
        recipient_email: { type: "string", description: "Recipient email address" },
        description: { type: "string", description: "Payment description" },
      },
      required: ["amount", "recipient_email", "description"],
    },
  },
  {
    name: "list_draft_payments",
    description: "List all pending draft payments waiting to be confirmed or cancelled.",
    input_schema: { type: "object", properties: {}, required: [] },
  },
  {
    name: "get_draft_payment",
    description: "Get details of a specific draft payment.",
    input_schema: {
      type: "object",
      properties: {
        draft_id: { type: "number", description: "Draft payment ID" },
      },
      required: ["draft_id"],
    },
  },
  {
    name: "confirm_draft_payment",
    description:
      "Confirm a draft payment — this SENDS the money immediately. " +
      "Only call after the user explicitly says yes.",
    input_schema: {
      type: "object",
      properties: {
        draft_id: { type: "number", description: "Draft payment ID to confirm" },
      },
      required: ["draft_id"],
    },
  },
  {
    name: "cancel_draft_payment",
    description: "Cancel a draft payment. Use when the user says no or changes their mind.",
    input_schema: {
      type: "object",
      properties: {
        draft_id: { type: "number", description: "Draft payment ID to cancel" },
      },
      required: ["draft_id"],
    },
  },

  // ── SCHEDULED PAYMENTS ─────────────────────────────────────────────────────
  {
    name: "create_scheduled_payment",
    description: "Set up a recurring or one-time future payment.",
    input_schema: {
      type: "object",
      properties: {
        amount: { type: "string", description: "Amount in EUR e.g. '50.00'" },
        recipient_email: { type: "string" },
        description: { type: "string" },
        start_date: {
          type: "string",
          description: "ISO 8601 datetime when the payment starts e.g. '2026-05-01T09:00:00'",
        },
        recurrence: {
          type: "string",
          enum: ["ONCE", "DAILY", "WEEKLY", "MONTHLY", "YEARLY"],
          description: "How often the payment repeats",
        },
      },
      required: ["amount", "recipient_email", "description", "start_date", "recurrence"],
    },
  },
  {
    name: "list_scheduled_payments",
    description: "List all active scheduled/recurring payments.",
    input_schema: { type: "object", properties: {}, required: [] },
  },
  {
    name: "cancel_scheduled_payment",
    description: "Cancel a scheduled or recurring payment.",
    input_schema: {
      type: "object",
      properties: {
        schedule_id: { type: "number", description: "Scheduled payment ID" },
      },
      required: ["schedule_id"],
    },
  },

  // ── REQUEST INQUIRIES ──────────────────────────────────────────────────────
  {
    name: "request_money",
    description:
      "Ask someone to pay you. They get a notification and can pay via bunq or a payment link. " +
      "Use for 'request money from', 'ask X to pay me', 'send an invoice to'.",
    input_schema: {
      type: "object",
      properties: {
        amount: { type: "string", description: "Amount to request in EUR" },
        recipient_email: { type: "string", description: "Email of person to request from" },
        description: { type: "string", description: "What the money is for" },
      },
      required: ["amount", "recipient_email", "description"],
    },
  },
  {
    name: "list_request_inquiries",
    description: "List payment requests you've sent to others (outgoing requests).",
    input_schema: { type: "object", properties: {}, required: [] },
  },
  {
    name: "get_request_inquiry",
    description: "Get the status of a specific outgoing payment request.",
    input_schema: {
      type: "object",
      properties: {
        request_id: { type: "number", description: "Request inquiry ID" },
      },
      required: ["request_id"],
    },
  },
  {
    name: "revoke_request_inquiry",
    description: "Cancel an outgoing payment request before the recipient responds.",
    input_schema: {
      type: "object",
      properties: {
        request_id: { type: "number", description: "Request inquiry ID to revoke" },
      },
      required: ["request_id"],
    },
  },
  {
    name: "create_request_inquiry_batch",
    description: "Send the same payment request to multiple people at once (e.g. split a bill).",
    input_schema: {
      type: "object",
      properties: {
        recipients: {
          type: "array",
          description: "List of people to request money from",
          items: {
            type: "object",
            properties: {
              email: { type: "string" },
              amount: { type: "string", description: "Amount in EUR" },
              description: { type: "string" },
            },
            required: ["email", "amount", "description"],
          },
        },
      },
      required: ["recipients"],
    },
  },

  // ── REQUEST RESPONSES ──────────────────────────────────────────────────────
  {
    name: "list_request_responses",
    description:
      "List incoming payment requests others have sent to you (things you need to accept or decline).",
    input_schema: { type: "object", properties: {}, required: [] },
  },
  {
    name: "accept_request",
    description: "Accept and pay an incoming payment request.",
    input_schema: {
      type: "object",
      properties: {
        request_response_id: { type: "number", description: "Request response ID" },
        amount: { type: "string", description: "Amount to pay in EUR" },
      },
      required: ["request_response_id", "amount"],
    },
  },
  {
    name: "reject_request",
    description: "Decline an incoming payment request.",
    input_schema: {
      type: "object",
      properties: {
        request_response_id: { type: "number", description: "Request response ID to reject" },
      },
      required: ["request_response_id"],
    },
  },

  // ── CARDS ──────────────────────────────────────────────────────────────────
  {
    name: "list_cards",
    description: "List all cards (debit, credit) with their status and limits.",
    input_schema: { type: "object", properties: {}, required: [] },
  },
  {
    name: "get_card",
    description: "Get details of a specific card.",
    input_schema: {
      type: "object",
      properties: {
        card_id: { type: "number", description: "Card ID" },
      },
      required: ["card_id"],
    },
  },
  {
    name: "update_card",
    description:
      "Block, unblock, or update spending/ATM limits on a card. " +
      "status 'BLOCKED' = freeze, 'ACTIVE' = unfreeze.",
    input_schema: {
      type: "object",
      properties: {
        card_id: { type: "number", description: "Card ID from list_cards" },
        status: { type: "string", enum: ["ACTIVE", "BLOCKED"], description: "New card status" },
        spending_limit_eur: { type: "string", description: "New spending limit e.g. '500.00'" },
        atm_limit_eur: { type: "string", description: "New ATM withdrawal limit e.g. '200.00'" },
      },
      required: ["card_id"],
    },
  },
  {
    name: "list_card_transactions",
    description:
      "List card-specific transactions with merchant details (name, city, approval status). " +
      "More detail than list_payments for card purchases.",
    input_schema: {
      type: "object",
      properties: {
        count: { type: "number", description: "Number of transactions (default 25)" },
        account_id: { type: "number", description: "Account ID (uses default if omitted)" },
      },
      required: [],
    },
  },
  {
    name: "list_card_names",
    description: "List the names allowed to appear on a new card order (based on verified identity).",
    input_schema: { type: "object", properties: {}, required: [] },
  },

  // ── BUNQ.ME TABS ───────────────────────────────────────────────────────────
  {
    name: "create_bunqme_tab",
    description:
      "Create a shareable payment link (bunq.me). Anyone can pay it — no bunq account needed. " +
      "Use for 'create a payment link', 'make a link so someone can pay me'.",
    input_schema: {
      type: "object",
      properties: {
        amount: { type: "string", description: "Amount to request in EUR" },
        description: { type: "string", description: "What the payment is for" },
        redirect_url: { type: "string", description: "URL to redirect to after payment (optional)" },
      },
      required: ["amount", "description"],
    },
  },
  {
    name: "get_bunqme_tab",
    description: "Check if a bunq.me payment link has been paid.",
    input_schema: {
      type: "object",
      properties: {
        tab_id: { type: "number", description: "Tab ID" },
      },
      required: ["tab_id"],
    },
  },
  {
    name: "list_bunqme_tabs",
    description: "List all bunq.me payment links (open and closed).",
    input_schema: { type: "object", properties: {}, required: [] },
  },
  {
    name: "cancel_bunqme_tab",
    description: "Cancel an open bunq.me payment link.",
    input_schema: {
      type: "object",
      properties: {
        tab_id: { type: "number", description: "Tab ID to cancel" },
      },
      required: ["tab_id"],
    },
  },

  // ── WEBHOOKS ───────────────────────────────────────────────────────────────
  {
    name: "list_webhooks",
    description: "List currently registered webhook URLs for real-time event notifications.",
    input_schema: { type: "object", properties: {}, required: [] },
  },
  {
    name: "set_webhooks",
    description:
      "Register a webhook URL to receive real-time event notifications. " +
      "Available categories: PAYMENT, MUTATION, CARD_TRANSACTION_SUCCESSFUL, CARD_TRANSACTION_FAILED, " +
      "REQUEST, DRAFT_PAYMENT, SCHEDULE_RESULT, BUNQME_TAB, IDEAL, SOFORT, BILLING, CHAT.",
    input_schema: {
      type: "object",
      properties: {
        webhook_url: { type: "string", description: "Public HTTPS URL to receive webhooks" },
        categories: {
          type: "array",
          items: { type: "string" },
          description: "Event categories to subscribe to",
        },
      },
      required: ["webhook_url", "categories"],
    },
  },
  {
    name: "clear_webhooks",
    description: "Remove all registered webhook URLs.",
    input_schema: { type: "object", properties: {}, required: [] },
  },
  {
    name: "list_webhook_failures",
    description: "List webhook deliveries that failed after all retries (for debugging).",
    input_schema: { type: "object", properties: {}, required: [] },
  },
  {
    name: "retry_webhook_failure",
    description: "Retry a specific failed webhook delivery.",
    input_schema: {
      type: "object",
      properties: {
        failure_id: { type: "number", description: "Failed webhook delivery ID" },
      },
      required: ["failure_id"],
    },
  },

  // ── OAUTH ──────────────────────────────────────────────────────────────────
  {
    name: "list_oauth_clients",
    description: "List OAuth applications registered on this account.",
    input_schema: { type: "object", properties: {}, required: [] },
  },
  {
    name: "create_oauth_client",
    description:
      "Create a new OAuth application (needed to let other bunq users authorize your app).",
    input_schema: { type: "object", properties: {}, required: [] },
  },

  // ── EVENTS ─────────────────────────────────────────────────────────────────
  {
    name: "get_events",
    description:
      "Get the unified activity feed combining all account events. " +
      "Use for general questions about recent activity.",
    input_schema: {
      type: "object",
      properties: {
        count: { type: "number", description: "Number of events (default 25)" },
      },
      required: [],
    },
  },

  // ── SANDBOX ────────────────────────────────────────────────────────────────
  {
    name: "sandbox_topup",
    description: "Add test money to the sandbox account (sandbox only). Requests from sugardaddy@bunq.com.",
    input_schema: {
      type: "object",
      properties: {
        amount: { type: "string", description: "Amount to add in EUR (max 500.00 per call)" },
      },
      required: [],
    },
  },
];

// =============================================================================
// TOOL DISPATCHER
// =============================================================================

async function runTool(name, input, ctx) {
  switch (name) {
    // User
    case "get_user_profile":        return getUserProfile(ctx);
    // Accounts
    case "get_balance":             return getBalance(ctx);
    case "get_account":             return getAccount(ctx, input);
    case "list_savings_accounts":   return listSavingsAccounts(ctx);
    case "list_joint_accounts":     return listJointAccounts(ctx);
    case "create_account":          return createAccount(ctx, input);
    case "update_account":          return updateAccount(ctx, input);
    // Payments
    case "list_payments":           return listPayments(ctx, input);
    case "get_payment":             return getPayment(ctx, input);
    case "send_payment":            return sendPayment(ctx, input);
    case "send_payment_batch":      return sendPaymentBatch(ctx, input);
    // Drafts
    case "create_draft_payment":    return createDraftPayment(ctx, input);
    case "list_draft_payments":     return listDraftPayments(ctx);
    case "get_draft_payment":       return getDraftPayment(ctx, input);
    case "confirm_draft_payment":   return confirmDraftPayment(ctx, input);
    case "cancel_draft_payment":    return cancelDraftPayment(ctx, input);
    // Scheduled
    case "create_scheduled_payment": return createScheduledPayment(ctx, input);
    case "list_scheduled_payments":  return listScheduledPayments(ctx);
    case "cancel_scheduled_payment": return cancelScheduledPayment(ctx, input);
    // Request inquiries
    case "request_money":           return requestMoney(ctx, input);
    case "list_request_inquiries":  return listRequestInquiries(ctx);
    case "get_request_inquiry":     return getRequestInquiry(ctx, input);
    case "revoke_request_inquiry":  return revokeRequestInquiry(ctx, input);
    case "create_request_inquiry_batch": return createRequestInquiryBatch(ctx, input);
    // Request responses
    case "list_request_responses":  return listRequestResponses(ctx);
    case "accept_request":          return acceptRequest(ctx, input);
    case "reject_request":          return rejectRequest(ctx, input);
    // Cards
    case "list_cards":              return listCards(ctx);
    case "get_card":                return getCard(ctx, input);
    case "update_card":             return updateCard(ctx, input);
    case "list_card_transactions":  return listCardTransactions(ctx, input);
    case "list_card_names":         return listCardNames(ctx);
    // bunq.me
    case "create_bunqme_tab":       return createBunqmeTab(ctx, input);
    case "get_bunqme_tab":          return getBunqmeTab(ctx, input);
    case "list_bunqme_tabs":        return listBunqmeTabs(ctx);
    case "cancel_bunqme_tab":       return cancelBunqmeTab(ctx, input);
    // Webhooks
    case "list_webhooks":           return listWebhooks(ctx);
    case "set_webhooks":            return setWebhooks(ctx, input);
    case "clear_webhooks":          return clearWebhooks(ctx);
    case "list_webhook_failures":   return listWebhookFailures(ctx);
    case "retry_webhook_failure":   return retryWebhookFailure(ctx, input);
    // OAuth
    case "list_oauth_clients":      return listOauthClients(ctx);
    case "create_oauth_client":     return createOauthClient(ctx);
    // Events + sandbox
    case "get_events":              return getEvents(ctx, input);
    case "sandbox_topup":           return sandboxTopup(ctx, input);
    default:
      throw new Error(`Unknown tool: ${name}`);
  }
}

// =============================================================================
// AGENT LOOP
// =============================================================================

const SYSTEM_PROMPT = `You are a helpful voice banking assistant for bunq.
You help users check balances, send money, manage cards, create payment links, and review transactions.

Guidelines:
- Be concise and clear — responses may be read aloud.
- For sending money: ALWAYS use create_draft_payment first, read back the details ("Sending €X to Y for Z — confirm?"), and only call confirm_draft_payment after the user says yes/confirm/send it.
- Format amounts as "€X.XX" in responses.
- For splitting bills with multiple people: use create_request_inquiry_batch.
- If a tool fails, explain the error plainly and suggest what to do.
- Never invent account or payment details — always call the right tool.
- The user is on the SANDBOX environment — sugardaddy@bunq.com is a test recipient that always works.`;

async function chat(messages, anthropic, ctx) {
  while (true) {
    const response = await anthropic.messages.create({
      model: LLM_MODEL,
      max_tokens: 4096,
      system: SYSTEM_PROMPT,
      tools: TOOLS,
      messages,
    });

    messages.push({ role: "assistant", content: response.content });

    if (response.stop_reason === "end_turn") {
      const text = response.content.find((b) => b.type === "text")?.text || "";
      return text;
    }

    if (response.stop_reason === "tool_use") {
      const toolUseBlocks = response.content.filter((b) => b.type === "tool_use");
      const toolResults = [];

      for (const block of toolUseBlocks) {
        console.log(`  → [tool] ${block.name}(${JSON.stringify(block.input)})`);
        try {
          const result = await runTool(block.name, block.input, ctx);
          toolResults.push({
            type: "tool_result",
            tool_use_id: block.id,
            content: JSON.stringify(result),
          });
        } catch (err) {
          console.log(`  ✗ [tool error] ${err.message}`);
          toolResults.push({
            type: "tool_result",
            tool_use_id: block.id,
            content: `Error: ${err.message}`,
            is_error: true,
          });
        }
      }

      messages.push({ role: "user", content: toolResults });
      continue;
    }

    break;
  }

  return messages.at(-1)?.content?.find?.((b) => b.type === "text")?.text || "";
}

// =============================================================================
// MAIN
// =============================================================================

async function main() {
  if (!ANTHROPIC_API_KEY) {
    console.error("Missing ANTHROPIC_API_KEY in .env");
    process.exit(1);
  }

  const state = loadSession();
  const { sessionToken, userId, privateKey } = state;

  const accountsRes = await bunq("GET", `/user/${userId}/monetary-account`, null, sessionToken);
  const firstRaw = (accountsRes.Response || [])[0];
  const firstAccount = firstRaw?.MonetaryAccountBank || firstRaw?.MonetaryAccountSavings;
  if (!firstAccount) throw new Error("No monetary account found.");

  const ctx = { sessionToken, userId, accountId: firstAccount.id, privateKey };

  const anthropic = new Anthropic({ apiKey: ANTHROPIC_API_KEY });
  const messages = [];

  const rl = readline.createInterface({ input: process.stdin, output: process.stdout });

  console.log("\n━━━ bunq Voice Agent (" + TOOLS.length + " tools) ━━━━━━━━━━━━━━━━━━━");
  console.log(`  Model  : ${LLM_MODEL}`);
  console.log(`  Account: ${firstAccount.description} (id: ${firstAccount.id})`);
  console.log(`  Balance: €${firstAccount.balance?.value}`);
  console.log("  Type 'quit' to exit, 'tools' to list available tools.\n");

  const ask = () => {
    rl.question("You: ", async (input) => {
      input = input.trim();
      if (!input) return ask();
      if (input.toLowerCase() === "quit") { rl.close(); return; }
      if (input.toLowerCase() === "tools") {
        console.log("\nAvailable tools:");
        TOOLS.forEach((t) => console.log(`  • ${t.name} — ${t.description.split(".")[0]}`));
        console.log();
        return ask();
      }

      messages.push({ role: "user", content: input });

      try {
        const reply = await chat(messages, anthropic, ctx);
        console.log(`\nAssistant: ${reply}\n`);
      } catch (err) {
        console.error(`\nError: ${err.message}\n`);
        messages.pop();
      }

      ask();
    });
  };

  ask();
}

main().catch((err) => { console.error("Fatal:", err.message); process.exit(1); });
