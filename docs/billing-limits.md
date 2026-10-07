# Setting a monthly spending limit with each maker

This is a backstop. The run controls already show you the cost before a run and pause
at +25% over what you approved. A monthly limit on each maker's own billing page
catches anything that slips past them. Checked against each maker's docs on
2026-09-19; the pages may move.

Pick a limit comfortably above what you expect to spend in a month. A full 141-drawing
run across three models was estimated at $25–$130 (SPEC 2.7).

## Anthropic (Claude)

1. Go to platform.claude.com → **Settings → Billing**.
2. Under **Spend limits**, click **Set limit** (or **Adjust limit**) and enter the amount.

**It stops requests.** At the limit, calls are refused until next month or until you
raise the limit. Your usage tier also has its own ceiling. Source:
platform.claude.com/docs/en/api/rate-limits

## OpenAI (GPT)

1. Go to platform.openai.com → **Settings → Organization limits**.
2. Under **Spend**, click **Edit spend limit** and enter the amount.
3. **Tick "Enforce a hard limit".** Without this tick it only sends email alerts and
   never stops spending.

It can go slightly over the limit, because OpenAI doesn't enforce it instantly.
Source: developers.openai.com/api/docs/guides/spend-limits

## Google (Gemini)

1. Go to aistudio.google.com/spend (the **Spend** page in AI Studio).
2. Under **Monthly spend cap**, click **Edit spend cap** and enter the amount.

Google labels this "Experimental". It takes about 10 minutes to catch up, so spending
can run past it in that window. Leave some room. Google's docs don't say exactly what
happens to a request once your own cap is reached. Google also has an automatic
ceiling on the whole billing account, set by your tier, that pauses everything when
reached. Source: ai.google.dev/gemini-api/docs/billing
