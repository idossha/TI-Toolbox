#!/usr/bin/env python3
"""
Check for high-severity bandit issues and exit with appropriate code
"""
import json
import sys

def main():
    """Check for high-severity issues and return appropriate exit code."""
    try:
        with open('bandit-results.json', 'r') as f:
            data = json.load(f)
            results = data.get('results', [])
            high_issues = [issue for issue in results if issue.get('issue_severity', '').upper() == 'HIGH']

            high_count = len(high_issues)
            print(f"Found {high_count} high-severity security issues")

            if high_count > 0:
                print("❌ High-severity security issues found! Failing the build.")
                print("Please review the Bandit results above and fix these issues.")
                sys.exit(1)
            else:
                print("✅ No high-severity security issues found.")
                sys.exit(0)

    except FileNotFoundError:
        print("⚠️  Bandit results file not found")
        sys.exit(0)
    except Exception as e:
        print(f"Error checking severity: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()
