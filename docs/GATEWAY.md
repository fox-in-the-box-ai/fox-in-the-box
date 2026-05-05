# FITB AI Gateway: One-Click LLM Access with Stripe

**Status:** Ready for 1-week implementation (Mon May 12 – Fri May 16)  
**Owners:** Stan (product), Cursor (dev), Hermes (review)  
**Revenue Model:** 5% surcharge on all inference costs  
**Stack:** ngrok AI Gateway (BYOK) + Stripe + MakerKit

---

## Problem

Users need LLM access without managing multiple provider accounts. FITB provides unified access, handles billing, and keeps 5% margin.

---

## Solution

**Three-layer architecture:**

```
┌─────────────────────────────────────────────┐
│        FITB Web App (MakerKit)              │
│  1. Modal on first LLM use                  │
│  2. User selects provider from .env         │
│  3. Starts using LLM                        │
└────────────┬────────────────────────────────┘
             │
┌────────────▼────────────────────────────────┐
│      FITB Backend (Node/MakerKit)           │
│  POST /api/inference                        │
│  ├─ Check user has credits                  │
│  ├─ Route to ngrok                          │
│  ├─ Deduct cost (+ 5% markup)               │
│  └─ Check auto-refill threshold             │
└────────────┬────────────────────────────────┘
             │
┌────────────▼────────────────────────────────┐
│   ngrok AI Gateway (BYOK, free)             │
│  ├─ OpenAI (via user's key)                 │
│  ├─ Anthropic (via user's key)              │
│  └─ Automatic failover + caching            │
└─────────────────────────────────────────────┘
```

**Stripe handles all billing** — purchases, auto-refill, webhooks, receipts.

---

## Features

### 1. Provider Selection (First Use)

Modal on first LLM request:
```
"Choose your LLM provider:
   
  ☑ OpenAI (Recommended)
  ☐ Anthropic
  ☐ ChatGPT (OAuth login)
  ☐ Local LLM
  
  [Continue]"
```

- Reads available providers from `/api/providers` (based on .env)
- Stores selection in localStorage
- Routes all requests through ngrok + selected provider

### 2. Credit Purchase (Lazy Setup)

First LLM call without credits → modal:
```
"Buy LLM Credits
  
  Current Balance: $0.00
  
  [Buy $10]  [Buy $50]  [Buy $100]
  
  [Skip for now]"
```

- Stripe Checkout (one-time, simple)
- Instant verification via webhook
- Credits appear in UI within seconds
- Stored in `users.gateway_credits`

### 3. Auto-Refill (Bulletproof)

User sets in Settings:
- ✓ Enable auto-refill
- ✓ Refill when balance < $[threshold]
- ✓ Refill amount = $[amount]

**How it works:**
- Every inference request checks: `balance < threshold`?
- If yes + enabled + not charged in last 15 mins → charge card on file
- Stripe webhook adds credits within seconds
- Silently fails if card declined (user can manual refill)

**No queue, no cron, no background job:**
- Triggered on natural request flow
- 15-min deduplication cooldown
- Fire-and-forget async charge

### 4. Billing History

Settings page shows:
- Current balance
- Last 30 transactions (date, model, cost, provider)
- CSV export
- Stripe receipt links

---

## Architecture

### Backend (.env provisioning)

```bash
# Provider keys (FITB manages)
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...

# ngrok gateway
NGROK_AI_GATEWAY_URL=https://your-gateway.ngrok.app
NGROK_AI_GATEWAY_KEY=ng-xxxxx

# Stripe
STRIPE_SECRET_KEY=sk_live_...
STRIPE_WEBHOOK_SECRET=whsec_...

# FITB markup
FITB_MARKUP_PERCENT=5
```

### Database Schema

**Users table (new columns):**
```sql
ALTER TABLE users ADD COLUMN gateway_credits DECIMAL(10, 2) DEFAULT 0;
ALTER TABLE users ADD COLUMN gateway_enabled BOOLEAN DEFAULT FALSE;
ALTER TABLE users ADD COLUMN auto_refill_threshold DECIMAL(10, 2) DEFAULT 0;
ALTER TABLE users ADD COLUMN auto_refill_amount DECIMAL(10, 2) DEFAULT 0;
ALTER TABLE users ADD COLUMN auto_refill_enabled BOOLEAN DEFAULT FALSE;
ALTER TABLE users ADD COLUMN last_auto_refill_attempt_at TIMESTAMP;
ALTER TABLE users ADD COLUMN stripe_customer_id TEXT;
```

**Request log:**
```sql
CREATE TABLE gateway_requests (
  id UUID PRIMARY KEY,
  user_id UUID REFERENCES users(id),
  provider TEXT,
  model TEXT,
  input_tokens INT,
  output_tokens INT,
  cost DECIMAL(10, 4),
  markup_cost DECIMAL(10, 4),
  status TEXT,                  -- 'success' | 'insufficient_balance' | 'failed'
  created_at TIMESTAMP
);
```

### API Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/providers` | GET | List available providers (based on .env) → `['openai', 'anthropic', ...]` |
| `/api/inference` | POST | Route LLM request → ngrok → deduct balance → handle auto-refill |
| `/api/gateway/balance` | GET | Return `{ credits, recent_transactions, auto_refill_config }` |
| `/api/gateway/purchase` | POST | Create Stripe Checkout session → `{ redirect_url, session_id }` |
| `/api/gateway/auto-refill/update` | POST | Set threshold/amount/enabled → `{ ok }` |
| `/webhooks/stripe` | POST | Handle charge.succeeded → add credits to user |

---

## Implementation (5-Day Sprint)

### Day 1: Database + Stripe Setup

- [ ] Run migrations (users columns + gateway_requests table)
- [ ] Create Stripe products: `fitb-credits-10`, `fitb-credits-50`, `fitb-credits-100`
- [ ] Set Stripe webhook endpoint → `/webhooks/stripe`
- [ ] Test Stripe test mode locally

### Day 2: Core Backend (Inference + Balance)

- [ ] Implement `/api/providers` (reads from .env, returns list)
- [ ] Implement `/api/inference` with:
  - [ ] Check `user.gateway_enabled`
  - [ ] Route to ngrok based on provider
  - [ ] Deduct cost + 5% to `gateway_credits`
  - [ ] Log to `gateway_requests`
  - [ ] Check auto-refill threshold
  - [ ] Return LLM response
- [ ] Implement `/api/gateway/balance` (return credits + last 10 transactions)
- [ ] Test end-to-end locally

### Day 3: Stripe Integration

- [ ] Implement `/api/gateway/purchase` (Stripe Checkout session)
- [ ] Implement `/webhooks/stripe` (charge.succeeded → add credits)
- [ ] Implement auto-refill charge logic (inside `/api/inference`)
- [ ] Test purchase flow in Stripe test mode

### Day 4: Frontend + Settings

- [ ] Provider selection modal (fetches `/api/providers`, stores in localStorage)
- [ ] Buy credits modal (calls `/api/gateway/purchase`, redirects to Stripe)
- [ ] Status card in nav (shows balance, low-balance warning)
- [ ] Settings page:
  - [ ] Display balance + recent transactions
  - [ ] CSV export
  - [ ] Auto-refill toggle + threshold/amount inputs
  - [ ] Link to Stripe receipts

### Day 5: Testing + Ship

- [ ] End-to-end test: signup → modal → purchase → inference → deduct
- [ ] Test auto-refill (trigger manually, verify charge + credit add)
- [ ] Security audit: Stripe webhook signing, no API key leaks
- [ ] Performance review (inference latency through ngrok)
- [ ] Ship to production

---

## Key Implementation Details

### Inference Request Flow

```typescript
// POST /api/inference
async function handleInference(req) {
  const { provider, model, messages } = req.body;
  const user = req.user;
  
  // 1. Check enabled + balance
  if (!user.gateway_enabled) return 402;
  
  // 2. Route to ngrok
  const response = await fetch(`${process.env.NGROK_AI_GATEWAY_URL}/chat/completions`, {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${process.env.NGROK_AI_GATEWAY_KEY}`,
      'X-Provider': provider,
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({ model, messages })
  }).then(r => r.json());
  
  // 3. Calculate cost
  const providerCost = calculateCost(provider, model, response.usage);
  const totalCost = providerCost * 1.05;  // 5% markup
  
  // 4. Atomic deduction + log
  await db.transaction(async (tx) => {
    await tx.query(
      'UPDATE users SET gateway_credits = gateway_credits - $1 WHERE id = $2 AND gateway_credits >= $1',
      [totalCost, user.id]
    );
    
    await tx.query(
      `INSERT INTO gateway_requests 
       (user_id, provider, model, input_tokens, output_tokens, cost, markup_cost, status, created_at)
       VALUES ($1, $2, $3, $4, $5, $6, $7, 'success', NOW())`,
      [user.id, provider, model, response.usage.prompt_tokens, response.usage.completion_tokens, providerCost, totalCost * 0.05]
    );
  });
  
  // 5. Auto-refill check
  const updatedUser = await getUser(user.id);
  const timeSinceLastAttempt = Date.now() - (updatedUser.last_auto_refill_attempt_at || 0);
  const fifteenMinsMs = 15 * 60 * 1000;
  
  if (
    updatedUser.gateway_credits < updatedUser.auto_refill_threshold &&
    updatedUser.auto_refill_enabled &&
    timeSinceLastAttempt > fifteenMinsMs
  ) {
    // Fire async, don't wait
    triggerAutoRefillAsync(user.id, updatedUser.auto_refill_amount).catch(console.error);
    await db.query(
      'UPDATE users SET last_auto_refill_attempt_at = NOW() WHERE id = $1',
      [user.id]
    );
  }
  
  return response;
}

async function triggerAutoRefillAsync(userId, amount) {
  try {
    const user = await getUser(userId);
    await stripe.paymentIntents.create({
      amount: amount * 100,
      currency: 'usd',
      customer: user.stripe_customer_id,
      confirm: true,
      metadata: { user_id: userId, auto_refill: true }
    });
  } catch (err) {
    console.error(`Auto-refill failed for ${userId}:`, err.message);
    // Silently fail — user can manual refill
  }
}
```

### Token Cost Calculation

```typescript
const COSTS = {
  'openai/gpt-4o': { input: 0.003, output: 0.012 },          // per 1K tokens
  'anthropic/opus': { input: 0.005, output: 0.025 },
  'anthropic/sonnet': { input: 0.003, output: 0.015 },
};

function calculateCost(provider, model, usage) {
  const key = `${provider}/${model}`;
  const rates = COSTS[key];
  if (!rates) throw new Error(`Unknown model: ${key}`);
  
  const inputCost = (usage.prompt_tokens / 1000) * rates.input;
  const outputCost = (usage.completion_tokens / 1000) * rates.output;
  return inputCost + outputCost;
}
```

### Stripe Webhook

```typescript
// POST /webhooks/stripe
async function handleStripeWebhook(req) {
  const sig = req.headers['stripe-signature'];
  const event = stripe.webhooks.constructEvent(
    req.rawBody,
    sig,
    process.env.STRIPE_WEBHOOK_SECRET
  );
  
  if (event.type === 'charge.succeeded') {
    const charge = event.data.object;
    const userId = charge.metadata?.user_id;
    
    if (!userId) return; // Not an auto-refill charge
    
    const amount = charge.amount / 100;
    
    // Idempotent: only add once (prevent duplicate webhooks)
    const existing = await db.query(
      'SELECT * FROM gateway_requests WHERE stripe_charge_id = $1',
      [charge.id]
    );
    
    if (existing.length === 0) {
      await db.query(
        'UPDATE users SET gateway_credits = gateway_credits + $1 WHERE id = $2',
        [amount, userId]
      );
      
      await db.query(
        `INSERT INTO gateway_requests 
         (user_id, status, stripe_charge_id, created_at)
         VALUES ($1, 'refill', $2, NOW())`,
        [userId, charge.id]
      );
    }
  }
}
```

---

## Startup Checklist

- [ ] ngrok account + AI Gateway enabled
- [ ] BYOK keys configured (OpenAI + Anthropic)
- [ ] Stripe account + products created
- [ ] .env keys ready (all 5 providers above)
- [ ] MakerKit database updated
- [ ] Hermes review of implementation

---

## Success Metrics (Friday Ship)

✓ End-to-end test: buy credits → use LLM → balance deducts  
✓ Auto-refill triggers correctly (15-min cooldown works)  
✓ Stripe webhook adds credits within 5 seconds  
✓ No double charges (webhook idempotency tested)  
✓ Multiple providers work (OpenAI + Anthropic tested)  
✓ Settings UI shows transactions + auto-refill config  

---

## Known Constraints

- ngrok BYOK is free; you pay providers directly (OpenAI/Anthropic)
- Card on file required for auto-refill (add during onboarding)
- 15-min cooldown prevents rapid repeats (acceptable)
- Failover managed by ngrok (invisible to user)

---

## References

- [ngrok AI Gateway BYOK](https://ngrok.com/docs/ai-gateway/guides/managing-provider-keys/)
- [Stripe PaymentIntent Docs](https://stripe.com/docs/api/payment_intents)
- [MakerKit Setup](https://makerkit.dev/docs)
