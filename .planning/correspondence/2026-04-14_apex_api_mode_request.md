# Apex Support — API/Plugin Mode Request

**To:** support@apextraderfunding.com (or the support channel Apex directs API requests to)
**From:** michael.gonzalez5@gmail.com
**Subject:** Enable R|API+ / API plugin mode for APEX-262674 (Rithmic conformance granted)

---

Hi Apex Support,

I'd like to request that API/plugin mode be enabled on my funded trader account so I can connect to Rithmic Paper Trading via R|Protocol API.

**Account details:**
- Apex user id: **APEX-262674**
- Broker: Apex Trader Funding
- Platform: Rithmic Paper Trading (moving to Rithmic 01 after 30-day paper validation)

**Rithmic conformance is already granted.** On 2026-04-14, Kashyap Upadhyay at Rithmic (rprotocolapi@rithmic.com) confirmed my application passed conformance and assigned the required `migo:` app_name prefix. My application logs in with:

- `app_name`: `migo:DEEP6`
- `app_version`: `2.0.0`
- `template_version`: `3.9`
- Client library: async-rithmic 1.5.9 (Python R|Protocol)

**Current blocker:**
When I attempt to log in to Rithmic Paper Trading (`wss://rprotocol.rithmic.com:443`) with my APEX-262674 credentials, Rithmic returns `rpCode=13 permission denied` on `RequestLogin` (template 10). Rithmic conformance alone is insufficient — I understand Apex must separately enable API/plugin mode on my user id. Your support team previously confirmed this is a two-step process: (1) Rithmic conformance, (2) Apex-side API mode enabled.

**What I'm asking:**
Please enable API/plugin mode for APEX-262674 so the login will succeed. Once enabled, I'll verify connectivity against Paper Trading immediately and confirm back to you.

**About the application:**
- Personal use only — proprietary trading tool for my own funded account
- Single instance (no redistribution, no proxying, no downstream customers)
- CME NQ futures only
- Plants needed: TICKER_PLANT, ORDER_PLANT, HISTORY_PLANT, PNL_PLANT
- Python 3.12 on macOS

Please let me know if there's any additional information you need, or any Apex-specific paperwork to sign before API mode can be enabled. Happy to provide anything required.

Thanks,
Michael Gonzalez
michael.gonzalez5@gmail.com
