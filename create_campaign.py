#!/usr/bin/env python3
"""
Google Ads Search Campaign Automation Script
============================================

Creates a complete Google Ads search campaign from JSON config using Google Ads API v14.

Requirements:
    pip install google-ads==21.3.0

Authentication:
    Create google-ads.yaml with your credentials:
    
    developer_token: YOUR_DEVELOPER_TOKEN
    client_id: YOUR_CLIENT_ID.apps.googleusercontent.com
    client_secret: YOUR_CLIENT_SECRET
    refresh_token: YOUR_REFRESH_TOKEN
    login_customer_id: 1234567890

Usage:
    # Dry-run (validation only):
    python create_campaign.py --config campaign-config.json --dry-run
    
    # Execute:
    python create_campaign.py --config campaign-config.json
    
    # With custom credentials:
    python create_campaign.py --config campaign-config.json --credentials custom-google-ads.yaml
"""

import argparse
import json
import sys
import re
from typing import Dict, List, Any
from datetime import datetime

try:
    from google.ads.googleads.client import GoogleAdsClient
    from google.ads.googleads.errors import GoogleAdsException
    from google.api_core import protobuf_helpers
except ImportError:
    print("ERROR: google-ads library not installed")
    print("Run: pip install google-ads==21.3.0")
    sys.exit(1)


class CampaignCreator:
    """Creates Google Ads campaigns from JSON configuration."""
    
    def __init__(self, credentials_path: str = "google-ads.yaml"):
        """Initialize Google Ads API client."""
        try:
            self.client = GoogleAdsClient.load_from_storage(credentials_path)
        except FileNotFoundError:
            print(f"ERROR: Credentials file not found: {credentials_path}")
            print("\nCreate google-ads.yaml with your credentials:")
            print("  developer_token: YOUR_TOKEN")
            print("  client_id: YOUR_ID.apps.googleusercontent.com")
            print("  client_secret: YOUR_SECRET")
            print("  refresh_token: YOUR_REFRESH")
            print("  login_customer_id: 1234567890")
            sys.exit(1)
        except Exception as e:
            print(f"ERROR: Failed to load credentials: {e}")
            sys.exit(1)
    
    def load_config(self, config_path: str) -> Dict:
        """Load and validate campaign configuration from JSON."""
        try:
            with open(config_path, 'r') as f:
                config = json.load(f)
            return config
        except FileNotFoundError:
            print(f"ERROR: Config file not found: {config_path}")
            sys.exit(1)
        except json.JSONDecodeError as e:
            print(f"ERROR: Invalid JSON in config file: {e}")
            sys.exit(1)
    
    def validate_config(self, config: Dict) -> List[str]:
        """Validate configuration and return list of errors/warnings."""
        issues = []
        
        # Check for placeholders
        config_str = json.dumps(config)
        placeholder_pattern = r'\[PLACEHOLDER[^\]]*\]|\[REPLACE[^\]]*\]'
        placeholders = re.findall(placeholder_pattern, config_str)
        
        if placeholders:
            issues.append(f"⚠️  BLOCKER: Found {len(placeholders)} placeholder(s) in config:")
            for p in set(placeholders[:5]):  # Show first 5 unique
                issues.append(f"   - {p}")
            if len(set(placeholders)) > 5:
                issues.append(f"   ... and {len(set(placeholders)) - 5} more")
        
        # Required fields
        if not config.get('account', {}).get('customer_id'):
            issues.append("❌ Missing: account.customer_id")
        
        if not config.get('campaign', {}).get('budget', {}).get('amount_micros'):
            issues.append("❌ Missing: campaign.budget.amount_micros")
        
        if not config.get('campaign', {}).get('name'):
            issues.append("❌ Missing: campaign.name")
        
        # Check ad groups
        ad_groups = config.get('ad_groups', [])
        if not ad_groups:
            issues.append("❌ No ad groups defined")
        
        for idx, ag in enumerate(ad_groups):
            if not ag.get('keywords'):
                issues.append(f"⚠️  Ad group {idx+1} has no keywords")
            
            if not ag.get('responsive_search_ads'):
                issues.append(f"❌ Ad group {idx+1} has no ads")
        
        # Budget validation
        budget_micros = config.get('campaign', {}).get('budget', {}).get('amount_micros', 0)
        if budget_micros < 10000000:  # $10/day minimum
            issues.append(f"⚠️  Budget ${budget_micros/1000000:.2f}/day is very low (recommended: $30-50/day)")
        
        return issues
    
    def create_campaign_budget(self, customer_id: str, config: Dict, dry_run: bool = False) -> str:
        """Create campaign budget and return resource name."""
        budget_service = self.client.get_service("CampaignBudgetService")
        
        budget_operation = self.client.get_type("CampaignBudgetOperation")
        budget = budget_operation.create
        budget.name = config['campaign']['budget']['name']
        budget.amount_micros = config['campaign']['budget']['amount_micros']
        budget.delivery_method = self.client.enums.BudgetDeliveryMethodEnum[
            config['campaign']['budget']['delivery_method']
        ]
        
        if dry_run:
            print(f"[DRY-RUN] Would create budget: {budget.name} = ${budget.amount_micros/1000000:.2f}/day")
            return f"customers/{customer_id}/campaignBudgets/dry_run_123"
        
        try:
            response = budget_service.mutate_campaign_budgets(
                customer_id=customer_id,
                operations=[budget_operation]
            )
            budget_resource_name = response.results[0].resource_name
            print(f"✅ Created budget: {budget_resource_name}")
            return budget_resource_name
        except GoogleAdsException as ex:
            print(f"❌ Budget creation failed: {ex}")
            for error in ex.failure.errors:
                print(f"   Error: {error.message}")
            raise
    
    def create_campaign(self, customer_id: str, budget_resource_name: str, config: Dict, dry_run: bool = False) -> str:
        """Create campaign and return resource name."""
        campaign_service = self.client.get_service("CampaignService")
        
        campaign_operation = self.client.get_type("CampaignOperation")
        campaign = campaign_operation.create
        
        campaign.name = config['campaign']['name']
        campaign.status = self.client.enums.CampaignStatusEnum[config['campaign']['status']]
        campaign.advertising_channel_type = self.client.enums.AdvertisingChannelTypeEnum[
            config['campaign']['advertising_channel_type']
        ]
        campaign.campaign_budget = budget_resource_name
        
        # Bidding strategy
        bidding = config['campaign']['bidding_strategy']
        if bidding['type'] == 'MAXIMIZE_CONVERSIONS':
            campaign.maximize_conversions.target_cpa_micros = bidding.get('target_cpa_micros')
        
        # Network settings
        ns = config['campaign']['network_settings']
        campaign.network_settings.target_google_search = ns['target_google_search']
        campaign.network_settings.target_search_network = ns['target_search_network']
        campaign.network_settings.target_content_network = ns['target_content_network']
        campaign.network_settings.target_partner_search_network = ns['target_partner_search_network']
        
        # Geo targeting
        geo_type = config['campaign']['geo_target_type_setting']['positive_geo_target_type']
        campaign.geo_target_type_setting.positive_geo_target_type = \
            self.client.enums.PositiveGeoTargetTypeEnum[geo_type]
        
        # Dates
        if config['campaign'].get('start_date'):
            campaign.start_date = config['campaign']['start_date'].replace('-', '')
        if config['campaign'].get('end_date'):
            campaign.end_date = config['campaign']['end_date'].replace('-', '')
        
        if dry_run:
            print(f"[DRY-RUN] Would create campaign: {campaign.name}")
            print(f"   Status: {config['campaign']['status']}")
            print(f"   Type: {config['campaign']['advertising_channel_type']}")
            print(f"   Bidding: {bidding['type']}")
            return f"customers/{customer_id}/campaigns/dry_run_456"
        
        try:
            response = campaign_service.mutate_campaigns(
                customer_id=customer_id,
                operations=[campaign_operation]
            )
            campaign_resource_name = response.results[0].resource_name
            print(f"✅ Created campaign: {campaign_resource_name}")
            return campaign_resource_name
        except GoogleAdsException as ex:
            print(f"❌ Campaign creation failed: {ex}")
            for error in ex.failure.errors:
                print(f"   Error: {error.message}")
            raise
    
    def create_campaign_criteria(self, customer_id: str, campaign_resource_name: str, 
                                 config: Dict, dry_run: bool = False):
        """Add geo and language targeting to campaign."""
        criterion_service = self.client.get_service("CampaignCriterionService")
        operations = []
        
        # Geo targeting
        for location_id in config['campaign']['geo_targeting']['location_ids']:
            criterion_operation = self.client.get_type("CampaignCriterionOperation")
            criterion = criterion_operation.create
            criterion.campaign = campaign_resource_name
            criterion.location.geo_target_constant = f"geoTargetConstants/{location_id}"
            operations.append(criterion_operation)
        
        # Language targeting
        for language_constant in config['campaign']['language_targeting']['language_constants']:
            criterion_operation = self.client.get_type("CampaignCriterionOperation")
            criterion = criterion_operation.create
            criterion.campaign = campaign_resource_name
            criterion.language.language_constant = language_constant
            operations.append(criterion_operation)
        
        if dry_run:
            print(f"[DRY-RUN] Would add {len(operations)} targeting criteria")
            return
        
        try:
            response = criterion_service.mutate_campaign_criteria(
                customer_id=customer_id,
                operations=operations
            )
            print(f"✅ Added {len(response.results)} targeting criteria")
        except GoogleAdsException as ex:
            print(f"⚠️  Targeting criteria warning: {ex}")
    
    def create_ad_group(self, customer_id: str, campaign_resource_name: str, 
                       ag_config: Dict, dry_run: bool = False) -> str:
        """Create ad group and return resource name."""
        ad_group_service = self.client.get_service("AdGroupService")
        
        ag_operation = self.client.get_type("AdGroupOperation")
        ad_group = ag_operation.create
        
        ad_group.name = ag_config['name']
        ad_group.status = self.client.enums.AdGroupStatusEnum[ag_config['status']]
        ad_group.campaign = campaign_resource_name
        ad_group.type_ = self.client.enums.AdGroupTypeEnum[ag_config['type']]
        ad_group.cpc_bid_micros = ag_config['cpc_bid_micros']
        
        if dry_run:
            print(f"[DRY-RUN] Would create ad group: {ad_group.name}")
            return f"{campaign_resource_name}/adGroups/dry_run_789"
        
        try:
            response = ad_group_service.mutate_ad_groups(
                customer_id=customer_id,
                operations=[ag_operation]
            )
            ad_group_resource_name = response.results[0].resource_name
            print(f"✅ Created ad group: {ad_group_resource_name}")
            return ad_group_resource_name
        except GoogleAdsException as ex:
            print(f"❌ Ad group creation failed: {ex}")
            for error in ex.failure.errors:
                print(f"   Error: {error.message}")
            raise
    
    def create_keywords(self, customer_id: str, ad_group_resource_name: str, 
                       keywords: List[Dict], dry_run: bool = False):
        """Add keywords to ad group."""
        criterion_service = self.client.get_service("AdGroupCriterionService")
        operations = []
        
        for kw in keywords:
            # Skip placeholders
            if '[PLACEHOLDER' in kw['text'] or '[REPLACE' in kw['text']:
                continue
            
            criterion_operation = self.client.get_type("AdGroupCriterionOperation")
            criterion = criterion_operation.create
            criterion.ad_group = ad_group_resource_name
            criterion.status = self.client.enums.AdGroupCriterionStatusEnum.ENABLED
            criterion.keyword.text = kw['text']
            criterion.keyword.match_type = self.client.enums.KeywordMatchTypeEnum[kw['match_type']]
            operations.append(criterion_operation)
        
        if not operations:
            print("⚠️  No valid keywords to add (all placeholders)")
            return
        
        if dry_run:
            print(f"[DRY-RUN] Would add {len(operations)} keywords")
            for op in operations[:3]:
                print(f"   - {op.create.keyword.text} ({op.create.keyword.match_type})")
            return
        
        try:
            response = criterion_service.mutate_ad_group_criteria(
                customer_id=customer_id,
                operations=operations
            )
            print(f"✅ Added {len(response.results)} keywords")
        except GoogleAdsException as ex:
            print(f"❌ Keywords creation failed: {ex}")
            for error in ex.failure.errors:
                print(f"   Error: {error.message}")
    
    def create_negative_keywords(self, customer_id: str, ad_group_resource_name: str, 
                                neg_keywords: List[Dict], dry_run: bool = False):
        """Add negative keywords to ad group."""
        criterion_service = self.client.get_service("AdGroupCriterionService")
        operations = []
        
        for kw in neg_keywords:
            criterion_operation = self.client.get_type("AdGroupCriterionOperation")
            criterion = criterion_operation.create
            criterion.ad_group = ad_group_resource_name
            criterion.negative = True
            criterion.keyword.text = kw['text']
            criterion.keyword.match_type = self.client.enums.KeywordMatchTypeEnum[kw['match_type']]
            operations.append(criterion_operation)
        
        if dry_run:
            print(f"[DRY-RUN] Would add {len(operations)} negative keywords")
            return
        
        try:
            response = criterion_service.mutate_ad_group_criteria(
                customer_id=customer_id,
                operations=operations
            )
            print(f"✅ Added {len(response.results)} negative keywords")
        except GoogleAdsException as ex:
            print(f"⚠️  Negative keywords warning: {ex}")
    
    def create_responsive_search_ad(self, customer_id: str, ad_group_resource_name: str, 
                                   ad_config: Dict, dry_run: bool = False):
        """Create responsive search ad."""
        ad_group_ad_service = self.client.get_service("AdGroupAdService")
        
        # Skip if placeholders present
        all_text = ' '.join(ad_config['headlines'] + ad_config['descriptions'])
        if '[PLACEHOLDER' in all_text or '[REPLACE' in all_text:
            print("⚠️  Skipping RSA with placeholders")
            return
        
        ad_operation = self.client.get_type("AdGroupAdOperation")
        ad_group_ad = ad_operation.create
        ad_group_ad.ad_group = ad_group_resource_name
        ad_group_ad.status = self.client.enums.AdGroupAdStatusEnum.ENABLED
        
        rsa = ad_group_ad.ad.responsive_search_ad
        
        # Headlines (max 15)
        for headline in ad_config['headlines'][:15]:
            headline_asset = self.client.get_type("AdTextAsset")
            headline_asset.text = headline[:30]  # Max 30 chars
            rsa.headlines.append(headline_asset)
        
        # Descriptions (max 4)
        for desc in ad_config['descriptions'][:4]:
            desc_asset = self.client.get_type("AdTextAsset")
            desc_asset.text = desc[:90]  # Max 90 chars
            rsa.descriptions.append(desc_asset)
        
        # Final URLs
        ad_group_ad.ad.final_urls.extend(ad_config['final_urls'])
        
        # Display path
        if ad_config.get('path1'):
            rsa.path1 = ad_config['path1'][:15]
        if ad_config.get('path2'):
            rsa.path2 = ad_config['path2'][:15]
        
        if dry_run:
            print(f"[DRY-RUN] Would create RSA with {len(rsa.headlines)} headlines, {len(rsa.descriptions)} descriptions")
            return
        
        try:
            response = ad_group_ad_service.mutate_ad_group_ads(
                customer_id=customer_id,
                operations=[ad_operation]
            )
            print(f"✅ Created responsive search ad: {response.results[0].resource_name}")
        except GoogleAdsException as ex:
            print(f"❌ Ad creation failed: {ex}")
            for error in ex.failure.errors:
                print(f"   Error: {error.message}")
    
    def create_full_campaign(self, config: Dict, dry_run: bool = False) -> Dict:
        """Create complete campaign from configuration."""
        customer_id = config['account']['customer_id']
        
        print(f"\n{'='*60}")
        print(f"Google Ads Campaign Creation {'[DRY-RUN MODE]' if dry_run else '[LIVE MODE]'}")
        print(f"{'='*60}\n")
        print(f"Customer ID: {customer_id}")
        print(f"Campaign: {config['campaign']['name']}")
        print(f"Budget: ${config['campaign']['budget']['amount_micros']/1000000:.2f}/day")
        print(f"\n{'='*60}\n")
        
        result = {
            'success': False,
            'campaign_resource_name': None,
            'ad_groups': [],
            'errors': []
        }
        
        try:
            # Step 1: Create budget
            budget_resource_name = self.create_campaign_budget(customer_id, config, dry_run)
            
            # Step 2: Create campaign
            campaign_resource_name = self.create_campaign(
                customer_id, budget_resource_name, config, dry_run
            )
            result['campaign_resource_name'] = campaign_resource_name
            
            # Step 3: Add targeting criteria
            self.create_campaign_criteria(customer_id, campaign_resource_name, config, dry_run)
            
            # Step 4: Create ad groups
            for ag_config in config.get('ad_groups', []):
                print(f"\n--- Creating ad group: {ag_config['name']} ---")
                
                ad_group_resource_name = self.create_ad_group(
                    customer_id, campaign_resource_name, ag_config, dry_run
                )
                result['ad_groups'].append(ad_group_resource_name)
                
                # Add keywords
                if ag_config.get('keywords'):
                    self.create_keywords(
                        customer_id, ad_group_resource_name, ag_config['keywords'], dry_run
                    )
                
                # Add negative keywords
                if ag_config.get('negative_keywords'):
                    self.create_negative_keywords(
                        customer_id, ad_group_resource_name, ag_config['negative_keywords'], dry_run
                    )
                
                # Create ads
                for ad_config in ag_config.get('responsive_search_ads', []):
                    self.create_responsive_search_ad(
                        customer_id, ad_group_resource_name, ad_config, dry_run
                    )
            
            result['success'] = True
            
            print(f"\n{'='*60}")
            if dry_run:
                print("✅ DRY-RUN VALIDATION COMPLETE")
                print("\nNo changes were made to your Google Ads account.")
                print("Remove --dry-run flag to execute campaign creation.")
            else:
                print("✅ CAMPAIGN CREATED SUCCESSFULLY")
                print(f"\nCampaign: {campaign_resource_name}")
                print(f"Status: {config['campaign']['status']} (enable in Google Ads UI)")
                print("\nNext steps:")
                print("1. Review campaign settings in Google Ads UI")
                print("2. Verify conversion tracking is installed")
                print("3. Change campaign status to ENABLED")
            print(f"{'='*60}\n")
            
        except Exception as e:
            result['errors'].append(str(e))
            print(f"\n❌ CAMPAIGN CREATION FAILED: {e}")
        
        return result


def main():
    parser = argparse.ArgumentParser(
        description="Create Google Ads search campaign from JSON config",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Dry-run validation:
  python create_campaign.py --config campaign-config.json --dry-run
  
  # Create campaign:
  python create_campaign.py --config campaign-config.json
  
  # Custom credentials:
  python create_campaign.py --config campaign-config.json --credentials prod.yaml
        """
    )
    parser.add_argument('--config', required=True, help='Path to campaign-config.json')
    parser.add_argument('--credentials', default='google-ads.yaml', help='Path to Google Ads credentials')
    parser.add_argument('--dry-run', action='store_true', help='Validate config without creating campaign')
    
    args = parser.parse_args()
    
    # Initialize creator
    creator = CampaignCreator(args.credentials)
    
    # Load config
    config = creator.load_config(args.config)
    
    # Validate config
    print("\n=== Configuration Validation ===\n")
    issues = creator.validate_config(config)
    
    if issues:
        print("Configuration issues found:\n")
        for issue in issues:
            print(issue)
        
        # Block execution if critical issues
        blockers = [i for i in issues if '❌' in i or 'BLOCKER' in i]
        if blockers:
            print(f"\n❌ {len(blockers)} blocker(s) found. Fix config before proceeding.")
            sys.exit(1)
        
        if not args.dry_run:
            print("\n⚠️  Warnings found but proceeding...")
    else:
        print("✅ Configuration valid\n")
    
    # Create campaign
    result = creator.create_full_campaign(config, dry_run=args.dry_run)
    
    # Exit code
    sys.exit(0 if result['success'] else 1)


if __name__ == '__main__':
    main()
