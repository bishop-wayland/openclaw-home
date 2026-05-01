// Hook transform: refurb-tracker email → direct iMessage to Dave.
//
// Architecture: this is a deterministic short-circuit. The transform
// inspects the inbound webhook, recognizes a refurb-tracker email
// (either as outer From or as forwarded-from in the body), and sends
// the alert iMessage directly via BlueBubbles' HTTP API. Returning null
// tells OpenClaw to skip the agent path entirely — no LLM in the
// delivery loop.
//
// Why this exists: putting agent instructions in messageTemplate gets
// wrapped as untrusted content, and the agent's independent decisions
// about whether/how to deliver have proven unreliable. A transform
// runs as plain JS in the gateway runtime and can call BB directly,
// which is the only path we've found that delivers deterministically
// for hook-triggered alerts.

const BB_URL = "http://localhost:1234";
const BB_PASSWORD = "get away from her you bitch";
// Bishop's BlueBubbles Mac is logged into iMessage as bishopunit937@gmail.com,
// so chat_guids to Dave are keyed by his email handle, not his phone.
// Confirmed via the agent message tool: result.messageId = "iMessage;-;otte.dave@gmail.com".
const DAVE_CHAT_GUID = "iMessage;-;otte.dave@gmail.com";
const DAVE_ADDRESS = "otte.dave@gmail.com";  // fallback if chat_guid path fails
const REFURB_SENDER = "info@refurb-tracker.com";

function isRefurbAlert(payload) {
  const msg = payload?.messages?.[0];
  if (!msg) return false;
  const haystack = `${msg.from ?? ""}\n${msg.body ?? ""}`.toLowerCase();
  return haystack.includes(REFURB_SENDER);
}

function originalSubject(msg) {
  const subject = (msg?.subject ?? "").trim();
  // Strip leading "Fwd:" / "Fw:" prefixes Gmail adds when forwarding.
  return subject.replace(/^((Fwd?|FWD?):\s*)+/i, "");
}

async function sendBlueBubbles(text) {
  const url = new URL("/api/v1/message/text", BB_URL);
  url.searchParams.set("password", BB_PASSWORD);
  const tempGuid = `refurb-alert-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
  const body = {
    chatGuid: DAVE_CHAT_GUID,
    tempGuid,
    message: text
    // Don't set "method" — "apple-script" requires the BlueBubbles Private
    // API helper which isn't installed on this Mac. Default mode (omit
    // method) works fine via the public API.
  };
  const requestBody = JSON.stringify(body);
  console.log(`[refurb-alert-transform] POST ${url.toString().replace(BB_PASSWORD, "***")}`);
  console.log(`[refurb-alert-transform] body: ${requestBody}`);
  const res = await fetch(url.toString(), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: requestBody
  });
  const responseText = await res.text();
  console.log(`[refurb-alert-transform] response status=${res.status} body=${responseText.slice(0,500)}`);
  if (!res.ok) {
    throw new Error(`BlueBubbles send (chatGuid path) failed (${res.status}): ${responseText}`);
  }
  return { status: res.status, body: responseText, tempGuid, path: "chatGuid" };
}

export default async function refurbAlertTransform(ctx) {
  const payload = ctx?.payload ?? {};
  if (!isRefurbAlert(payload)) {
    // Not a refurb alert — let the base mapping action run (e.g. triage).
    return undefined;
  }

  const subject = originalSubject(payload.messages[0]);
  const alertText = `🚨 Mac mini alert: ${subject} → https://www.apple.com/shop/refurbished/mac/mac-mini`;

  try {
    const result = await sendBlueBubbles(alertText);
    console.log(`[refurb-alert-transform] delivered tempGuid=${result.tempGuid} status=${result.status}`);
  } catch (err) {
    // Log but don't throw — log goes to gateway.err.log for forensic trace.
    console.error(`[refurb-alert-transform] BB send failed:`, err.message);
    // Returning null still skips the agent. We chose deterministic
    // alert delivery over agent-fallback because the agent path adds
    // unpredictable behavior. If BB is down, surface via gateway error
    // log + the trace script.
  }

  // Return null = skip the rest of the mapping (no agent run, no auto-deliver).
  return null;
}
