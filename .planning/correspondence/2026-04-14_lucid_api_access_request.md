# Lucid Trading Support — R|API+ Access Request

**To:** (Lucid Trading support / trader-services channel — use the address in your funded-trader welcome email)
**From:** michael.gonzalez5@gmail.com
**Subject:** R|API+ access request for LT-45N3KIV8 (Rithmic conformance granted)

---

Hi Lucid Trading Support,

I'd like to request R|API+ / Rithmic API access for my funded trader account so I can connect to Rithmic Paper Trading (and later Rithmic 01) via R|Protocol API.

**Account details:**
- Lucid Trading user id: **LT-45N3KIV8**
- Platform: Rithmic Paper Trading (for initial validation), Rithmic 01 (live, after 30-day paper gate)

**Rithmic conformance is already granted.** On 2026-04-14, Kashyap Upadhyay at Rithmic (rprotocolapi@rithmic.com) confirmed my application passed conformance testing and assigned the required `migo:` app_name prefix. My application logs in with:

- `app_name`: `migo:DEEP6`
- `app_version`: `2.0.0`
- `template_version`: `3.9`
- Client library: async-rithmic 1.5.9 (Python R|Protocol)

**Current blocker:**
Logging in to Rithmic Paper Trading (`wss://rprotocol.rithmic.com:443`) with LT-45N3KIV8 returns `rpCode=13 permission denied` on `RequestLogin`. This typically indicates the prop firm has not yet enabled API/plugin mode on the user id — conformance approves the application, but each firm must separately authorize the user for R|API+ access.

**What I need to know:**
1. Does Lucid Trading allow funded traders to access their account via R|API+ / Rithmic API?
2. If yes, what's the process to enable API/plugin mode on LT-45N3KIV8? Is there paperwork to sign, additional fees, or a technical review?
3. Is there a specific Rithmic `system_name` Lucid uses (e.g. "Rithmic Paper Trading", "Rithmic 01", or a Lucid-branded system name)?
4. Are there any restrictions on automated trading from R|API+ I should be aware of (e.g. order types, position limits, rate limits)?

**About the application:**
- Personal use only — proprietary trading tool for my own funded account
- Single instance (no redistribution, no proxying, no downstream customers)
- CME NQ futures only
- Plants needed: TICKER_PLANT, ORDER_PLANT, HISTORY_PLANT, PNL_PLANT
- Python 3.12 on macOS
- All risk limits (daily loss, consecutive loss pause, max position size) are enforced client-side in accordance with standard prop-firm rules

Happy to provide any additional documentation required.

Thanks,
Michael Gonzalez
michael.gonzalez5@gmail.com
