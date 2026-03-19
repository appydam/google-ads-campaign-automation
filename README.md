# Google Ads Campaign Automation

Complete technical setup package for creating Google Ads search campaigns via API.

## Package Contents

1. **Campaign Config Template** (`campaign-config.json`) - Complete JSON spec with all Google Ads API parameters
2. **Automation Script** (`create_campaign.py`) - Python script to create campaigns via Google Ads API v14
3. **Setup Guide** - Step-by-step platform connection instructions (separate deliverable)
4. **Validation Checklist** - 58-item pre-launch checklist (in setup guide)

## Quick Start

### Prerequisites

```bash
# Install Google Ads API client
pip install google-ads==21.3.0

# Create credentials file (google-ads.yaml)
cat > google-ads.yaml << EOF
developer_token: YOUR_DEVELOPER_TOKEN
client_id: YOUR_CLIENT_ID.apps.googleusercontent.com
client_secret: YOUR_CLIENT_SECRET
refresh_token: YOUR_REFRESH_TOKEN
login_customer_id: 1234567890
EOF
```

### Usage

Step 1: Edit configuration

```bash
# Replace placeholders in campaign-config.json:
# - customer_id
# - final_urls (landing page)
# - headlines, descriptions, keywords (from Ghost ad copy deliverables)
```

Step 2: Validate (dry-run)

```bash
python create_campaign.py --config campaign-config.json --dry-run
```

Step 3: Create campaign

```bash
python create_campaign.py --config campaign-config.json
```

## Configuration Schema

See `campaign-config.json` for the complete specification.

Key Settings:
- Budget: $50/day (50,000,000 micros)
- Bidding: Maximize Conversions (no target CPA)
- Network: Google Search only (no Display, no Search Partners)
- Geo: United States (location ID 2840)
- Language: English (constant 1000)
- Status: PAUSED (review before enabling)

Ad Group Structure:
- 1 ad group: "Core Product Keywords"
- Keywords: 5 exact/phrase match (placeholders - replace with Ghost deliverables)
- Negative keywords: 20 pre-configured quality filters
- Ads: 2 responsive search ads (15 headlines, 4 descriptions each - placeholders)
- Extensions: Sitelinks (4), Callouts (6), Structured Snippets (1)

## Critical Steps Before Launch

1. Complete All Placeholders - Replace with Ghost ad copy deliverables
2. Install Conversion Tracking - Google Ads tag on website
3. Verify Tracking Works - Complete 1+ test conversion
4. Review Campaign Settings - In Google Ads UI before enabling

## Dry-Run Validation

The automation script validates config before execution, checking for:
- Placeholder detection
- Required fields
- Budget reasonability
- Ad group structure
- Keyword/ad count

## Resources

- Google Ads API Docs: https://developers.google.com/google-ads/api/docs/start
- API Reference (v14): https://developers.google.com/google-ads/api/reference/rpc/v14/overview
- OAuth Setup: https://developers.google.com/google-ads/api/docs/oauth/overview

## Configuration Notes

Blockers (from config):
1. Awaiting Ghost ad copy deliverables for headlines, descriptions, keywords, sitelinks, callouts
2. Final landing page URL needs confirmation
3. Conversion tracking code must be installed on website before launch

Campaign starts in PAUSED state. Review all settings in Google Ads UI before enabling.

## License

MIT License - Created by Forge (Mission Control AI Agent)

Last Updated: 2026-03-19
Google Ads API Version: v14
Python Version: 3.8+
