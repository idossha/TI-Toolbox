#!/usr/bin/env python3
"""
Generate Bandit Security Scan Report for GitHub Actions
"""
import json
import sys

def main():
    """Generate a summary report from bandit results."""
    try:
        with open('bandit-results.json', 'r') as f:
            data = json.load(f)
            results = data.get('results', [])
            metrics = data.get('metrics', {})

        print('📊 **Summary:**')
        print(f'- Files scanned: {metrics.get("_totals", {}).get("loc", 0)} lines')
        print(f'- Total issues found: {len(results)}')

        severity_counts = {}
        confidence_counts = {}
        for issue in results:
            sev = issue.get('issue_severity', 'unknown')
            conf = issue.get('issue_confidence', 'unknown')
            severity_counts[sev] = severity_counts.get(sev, 0) + 1
            confidence_counts[conf] = confidence_counts.get(conf, 0) + 1

        print(f'- By severity: {severity_counts}')
        print(f'- By confidence: {confidence_counts}')
        print('')

        if results:
            print('🚨 **Issues found:**')
            for issue in results[:10]:  # Show first 10 issues
                filename = issue.get('filename', 'unknown')
                line = issue.get('line_number', 'unknown')
                severity = issue.get('issue_severity', 'unknown')
                confidence = issue.get('issue_confidence', 'unknown')
                test_id = issue.get('test_id', 'unknown')
                print(f'- {severity}/{confidence}: {test_id} in {filename}:{line}')
            if len(results) > 10:
                print(f'... and {len(results) - 10} more issues')
        else:
            print('✅ No security issues found!')

    except Exception as e:
        print(f'Error parsing results: {e}')
        sys.exit(1)

if __name__ == '__main__':
    main()
