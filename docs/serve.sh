#!/usr/bin/env bash
# Run the documentation site from any working directory, without stopping other servers.
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
port=4000
while [[ $# -gt 0 ]]; do
    case "$1" in
        --port)
            [[ $# -ge 2 ]] || { echo "Missing value for --port." >&2; exit 2; }
            port="$2"
            shift 2
            ;;
        -h|--help)
            echo "Usage: bash docs/serve.sh [--port PORT]"
            echo "Serve the docs at http://127.0.0.1:4000/ (default). Ctrl+C stops the server."
            exit 0
            ;;
        *) echo "Unknown option: $1. Use --help." >&2; exit 2 ;;
    esac
done
case "$port" in ''|*[!0-9]*) echo "Port must be a number from 1 to 65535." >&2; exit 2 ;; esac
if [[ ${#port} -gt 5 ]] || (( 10#$port < 1 || 10#$port > 65535 )); then
    echo "Port must be a number from 1 to 65535." >&2
    exit 2
fi

# Prefer supported Homebrew Ruby on Apple Silicon or Intel Macs; otherwise use PATH.
for ruby_bin in /opt/homebrew/opt/ruby@3.3/bin /usr/local/opt/ruby@3.3/bin; do
    if [[ -x "$ruby_bin/ruby" ]]; then
        export PATH="$ruby_bin:$PATH"
        break
    fi
done
if ! command -v ruby >/dev/null || ! ruby -e 'exit(Gem::Version.new(RUBY_VERSION) >= Gem::Version.new("3.3") ? 0 : 1)'; then
    echo "Ruby 3.3 or newer is required. On macOS: brew install ruby@3.3" >&2
    exit 1
fi
if ! command -v bundle >/dev/null; then
    echo "Bundler is missing. Install it with: gem install bundler" >&2
    exit 1
fi

# Explain a busy port instead of killing an unrelated site or failing deep inside Jekyll.
if ! ruby -rsocket -e 'TCPServer.new("127.0.0.1", Integer(ARGV[0], 10)).close' "$port" 2>/dev/null; then
    echo "Cannot listen on 127.0.0.1:$port. Another server may be using this port." >&2
    echo "Stop that server, or choose another port: bash docs/serve.sh --port 4001" >&2
    exit 1
fi

cd "$script_dir"
# A lockfile specifies versions; bundle check verifies that the gems are actually installed.
if ! bundle check; then
    bundle install
fi
export ENABLE_ANALYTICS="${ENABLE_ANALYTICS:-false}"
echo "Docs: http://127.0.0.1:$port/"
echo "Wait for 'Server running', then open the URL. Changes rebuild automatically; refresh your browser."
echo "Press Ctrl+C to stop."
exec bundle exec jekyll serve --host 127.0.0.1 --port "$port" --baseurl ""
