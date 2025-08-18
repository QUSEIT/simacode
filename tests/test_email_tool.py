"""
Test script for EmailSend tool functionality.

This script tests the email tool configuration loading, validation,
and basic functionality without actually sending emails.
"""

import asyncio
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from simacode.tools.email_send import EmailSendTool, EmailSendInput
from simacode.config import Config


async def test_email_tool_config():
    """Test email tool configuration loading."""
    print("=== Testing Email Tool Configuration ===")
    
    try:
        # Load configuration
        config = Config.load()
        print(f"✓ Configuration loaded successfully")
        
        # Check email config
        email_config = config.email
        print(f"✓ Email configuration found")
        print(f"  SMTP Server: {email_config.smtp.server}")
        print(f"  SMTP Port: {email_config.smtp.port}")
        print(f"  Use TLS: {email_config.smtp.use_tls}")
        print(f"  Username: {email_config.smtp.username}")
        print(f"  Password: {'***' if email_config.smtp.password else 'Not set'}")
        print(f"  Max Recipients: {email_config.security.max_recipients}")
        print(f"  Allowed Domains: {email_config.security.allowed_domains}")
        print(f"  From Name: {email_config.defaults.from_name}")
        
        # Create email tool
        email_tool = EmailSendTool(config)
        print(f"✓ Email tool created successfully")
        print(f"  Tool name: {email_tool.name}")
        print(f"  Tool version: {email_tool.version}")
        
        return True
        
    except Exception as e:
        print(f"✗ Configuration test failed: {e}")
        return False


async def test_email_input_validation():
    """Test email input validation."""
    print("\n=== Testing Email Input Validation ===")
    
    try:
        # Test valid input
        valid_input = {
            "to": "test@example.com",
            "subject": "Test Subject",
            "body": "Test message body",
            "content_type": "text"
        }
        
        email_input = EmailSendInput(**valid_input)
        print(f"✓ Valid input accepted")
        print(f"  To: {email_input.to}")
        print(f"  Subject: {email_input.subject}")
        print(f"  Content Type: {email_input.content_type}")
        
        # Test multiple recipients
        multi_input = {
            "to": ["user1@example.com", "user2@example.com"],
            "cc": "manager@example.com",
            "subject": "Multi-recipient test",
            "body": "Test message for multiple recipients",
            "attachments": ["/tmp/test.txt"]
        }
        
        multi_email = EmailSendInput(**multi_input)
        print(f"✓ Multi-recipient input accepted")
        print(f"  To count: {len(multi_email.to)}")
        print(f"  CC: {multi_email.cc}")
        print(f"  Attachments: {multi_email.attachments}")
        
        return True
        
    except Exception as e:
        print(f"✗ Input validation test failed: {e}")
        return False


async def test_email_address_validation():
    """Test email address validation functionality."""
    print("\n=== Testing Email Address Validation ===")
    
    try:
        config = Config.load()
        email_tool = EmailSendTool(config)
        
        # Test valid emails
        valid_emails = [
            "user@example.com",
            "test.email+tag@domain.co.uk",
            "firstname.lastname@company.org"
        ]
        
        for email in valid_emails:
            is_valid, result = email_tool._validate_email_address(email)
            if is_valid:
                print(f"✓ Valid email: {email}")
            else:
                print(f"✗ Email validation failed: {email} - {result}")
        
        # Test invalid emails
        invalid_emails = [
            "invalid.email",
            "@domain.com",
            "user@",
            "user..double.dot@domain.com"
        ]
        
        for email in invalid_emails:
            is_valid, result = email_tool._validate_email_address(email)
            if not is_valid:
                print(f"✓ Invalid email correctly rejected: {email}")
            else:
                print(f"✗ Invalid email incorrectly accepted: {email}")
        
        return True
        
    except Exception as e:
        print(f"✗ Email validation test failed: {e}")
        return False


async def test_permission_checks():
    """Test permission checking functionality."""
    print("\n=== Testing Permission Checks ===")
    
    try:
        config = Config.load()
        email_tool = EmailSendTool(config)
        
        # Test basic input without attachments
        basic_input = EmailSendInput(
            to="test@example.com",
            subject="Permission test",
            body="Testing permissions"
        )
        
        has_permission = await email_tool.check_permissions(basic_input)
        print(f"✓ Basic permission check: {'Granted' if has_permission else 'Denied'}")
        
        if not has_permission:
            if not config.email.smtp.server:
                print("  Reason: No SMTP server configured")
            elif not config.email.smtp.username:
                print("  Reason: No SMTP username configured")
            elif not config.email.smtp.password:
                print("  Reason: No SMTP password configured")
        
        return True
        
    except Exception as e:
        print(f"✗ Permission check test failed: {e}")
        return False


async def test_rate_limiting():
    """Test rate limiting functionality."""
    print("\n=== Testing Rate Limiting ===")
    
    try:
        config = Config.load()
        email_tool = EmailSendTool(config)
        
        # Check initial rate limits
        rate_ok, rate_msg = email_tool._check_rate_limits()
        print(f"✓ Rate limit check: {'OK' if rate_ok else 'Limited'}")
        if not rate_ok:
            print(f"  Reason: {rate_msg}")
        
        print(f"  Max emails per hour: {config.email.rate_limiting.max_emails_per_hour}")
        print(f"  Max emails per day: {config.email.rate_limiting.max_emails_per_day}")
        
        return True
        
    except Exception as e:
        print(f"✗ Rate limiting test failed: {e}")
        return False


async def main():
    """Run all email tool tests."""
    print("SimaCode Email Tool Test Suite")
    print("=" * 40)
    
    tests = [
        test_email_tool_config,
        test_email_input_validation,
        test_email_address_validation,
        test_permission_checks,
        test_rate_limiting
    ]
    
    passed = 0
    total = len(tests)
    
    for test in tests:
        try:
            result = await test()
            if result:
                passed += 1
        except Exception as e:
            print(f"✗ Test {test.__name__} failed with exception: {e}")
    
    print(f"\n=== Test Results ===")
    print(f"Passed: {passed}/{total}")
    print(f"Success Rate: {(passed/total)*100:.1f}%")
    
    if passed == total:
        print("🎉 All tests passed!")
    else:
        print("⚠️  Some tests failed. Check configuration and dependencies.")
    
    print("\n=== Setup Instructions ===")
    print("To use the email tool:")
    print("1. Install dependencies: pip install aiosmtplib email-validator bleach")
    print("2. Configure SMTP settings in .simacode/config.yaml")
    print("3. Set environment variables SIMACODE_SMTP_USER and SIMACODE_SMTP_PASS")
    print("   or configure them directly in the config file")


if __name__ == "__main__":
    asyncio.run(main())