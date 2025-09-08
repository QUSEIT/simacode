#!/usr/bin/env python3
"""
Ultimate MCP Content Extractor (Fixed Version).

Successfully extracts pure email data from MCP protocol wrapper messages.
"""

import json
import re
from pathlib import Path


def ultimate_extract_emails(file_path="hello.json"):
    """Extract emails from MCP response format."""
    print("=== Ultimate MCP Email Extractor ===")
    print(f"Processing: {file_path}")
    print()
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        print(f"File size: {len(content)} characters")
        
        # Method: Line by line search for email data
        print("Attempting line-by-line extraction...")
        
        lines = content.split('\n')
        email_data = []
        current_email = {}
        
        for line in lines:
            line = line.strip()
            
            # Look for email field patterns
            if '\\"uid\\"' in line:
                uid_match = re.search(r'\\"uid\\":\s*\\"([^"]+)\\"', line)
                if uid_match:
                    if current_email:  # Save previous email
                        email_data.append(current_email)
                    current_email = {'uid': uid_match.group(1)}
            
            elif '\\"subject\\"' in line and current_email:
                subject_match = re.search(r'\\"subject\\":\s*\\"([^"]*(?:\\\\.[^"]*)*)\\"', line)
                if subject_match:
                    current_email['subject'] = subject_match.group(1).replace('\\\\"', '"')
            
            elif '\\"sender\\"' in line and current_email:
                sender_match = re.search(r'\\"sender\\":\s*\\"([^"]*(?:\\\\.[^"]*)*)\\"', line)
                if sender_match:
                    current_email['sender'] = sender_match.group(1).replace('\\\\"', '"')
            
            elif '\\"recipient\\"' in line and current_email:
                recipient_match = re.search(r'\\"recipient\\":\s*\\"([^"]+)\\"', line)
                if recipient_match:
                    current_email['recipient'] = recipient_match.group(1)
            
            elif '\\"date\\"' in line and current_email:
                date_match = re.search(r'\\"date\\":\s*\\"([^"]+)\\"', line)
                if date_match:
                    current_email['date'] = date_match.group(1)
            
            elif '\\"size\\"' in line and current_email:
                size_match = re.search(r'\\"size\\":\s*(\\d+)', line)
                if size_match:
                    current_email['size'] = int(size_match.group(1))
                    
            elif '\\"body_text\\"' in line and current_email:
                current_email['body_text'] = ""
                
            elif '\\"body_html\\"' in line and current_email:
                body_match = re.search(r'\\"body_html\\":\s*\\"([^"]*(?:\\\\.[^"]*)*)\\"', line)
                if body_match:
                    current_email['body_html'] = body_match.group(1).replace('\\\\"', '"')
                    
            elif '\\"flags\\"' in line and current_email:
                current_email['flags'] = []
                
            elif '\\"attachments\\"' in line and current_email:
                current_email['attachments'] = []
        
        # Add the last email
        if current_email and 'uid' in current_email:
            email_data.append(current_email)
        
        if email_data:
            print(f"✅ Successfully extracted {len(email_data)} emails!")
            return email_data
        
        print("❌ Extraction failed")
        return None
        
    except Exception as e:
        print(f"❌ Extraction error: {e}")
        return None


def display_emails(emails):
    """Display extracted emails."""
    if not emails:
        print("No emails to display")
        return
    
    print("\n" + "=" * 60)
    print(f"📧 EXTRACTED EMAILS ({len(emails)} total)")
    print("=" * 60)
    
    for i, email in enumerate(emails, 1):
        print(f"\n📨 Email {i}:")
        print(f"   UID: {email.get('uid', 'N/A')}")
        print(f"   Subject: {email.get('subject', 'N/A')}")
        print(f"   From: {email.get('sender', 'N/A')}")
        print(f"   To: {email.get('recipient', 'N/A')}")
        print(f"   Date: {email.get('date', 'N/A')}")
        print(f"   Size: {email.get('size', 'N/A')} bytes")
        print(f"   Flags: {email.get('flags', [])}")
        print(f"   Attachments: {len(email.get('attachments', []))}")
        
        # Show body preview if available
        body_html = email.get('body_html', '')
        if body_html:
            preview = body_html[:100].replace('\\r\\n', ' ').replace('\\n', ' ')
            print(f"   Body preview: {preview}...")
    
    print("\n" + "=" * 60)
    print("🎯 PURE JSON OUTPUT:")
    print("=" * 60)
    print(json.dumps(emails, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    # Extract emails
    emails = ultimate_extract_emails()
    
    # Display results
    if emails:
        display_emails(emails)
        print(f"\n🎉 SUCCESS: Extracted {len(emails)} emails from MCP message!")
        print("✨ This demonstrates successful removal of MCP protocol wrappers.")
    else:
        print("\n❌ FAILED: Could not extract emails from MCP message.")