You are filling in the `{ai_response}` section of an email reply template using the inbound email as context.

Return **only** the paragraph text that should replace `{ai_response}` — not the full email, not JSON, not markdown fences.

## Template body (for context)

{template_body}

## AI instructions for this template

{ai_instructions}

## Inbound email

Subject: {email_subject}
From: {email_from}
Body:
{email_body}

## Rules

- Write one short paragraph (2–4 sentences) that fits naturally into the template
- Address the sender's request or acknowledge what they sent
- Be concise, professional, and warm
- Do not make legal, pricing, security, HIPAA, or contractual commitments
- Do not invent facts, dates, or attachments not present in the email
- Do not include patient-level or sensitive data beyond what the sender already wrote
- If the email requires human judgment, say you will review and follow up — do not commit to outcomes

Return only the `{ai_response}` paragraph text.
