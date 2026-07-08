#!/usr/bin/env bash

# scripts/test_run-tests.sh

set -euo pipefail

TEST_SCRIPT="scripts/run-tests.sh"
DOCKER_COMPOSE=".docker/docker-compose.gh.yml"

echo "Test: Checking if $TEST_SCRIPT exists and is executable..."
if [[ ! -x "$TEST_SCRIPT" ]]; then
    echo "FAIL: $TEST_SCRIPT is not executable or missing."
    exit 1
fi
echo "PASS: $TEST_SCRIPT is executable."

echo "Test: Checking if $DOCKER_COMPOSE exists..."
if [[ ! -f "$DOCKER_COMPOSE" ]]; then
    echo "FAIL: $DOCKER_COMPOSE is missing."
    exit 1
fi
echo "PASS: $DOCKER_COMPOSE exists."

echo "Test: Running $TEST_SCRIPT with dummy environment variables (dry run)..."
export PLANET_USER="dummyuser"
export PLANET_PASSWORD="dummypass"

# Mock docker-compose to avoid running containers
mock_path="$(mktemp -d)"
export PATH="$mock_path:$PATH"
cat >"$(command -v docker-compose)" <<'EOF'
#!/usr/bin/env bash
echo "MOCK docker-compose $@"
exit 0
EOF
chmod +x "$(command -v docker-compose)"

if "$TEST_SCRIPT" --help 2>&1 | grep -q "MOCK docker-compose"; then
    echo "PASS: docker-compose was called (mocked)."
else
    echo "FAIL: docker-compose was not called as expected."
    exit 1
fi

echo "Test: Checking script fails gracefully if PLANET_USER is unset..."
unset PLANET_USER
if "$TEST_SCRIPT" 2>&1 | grep -qi "PLANET_USER"; then
    echo "PASS: Script warns about missing PLANET_USER."
else
    echo "FAIL: Script did not warn about missing PLANET_USER."
    exit 1
fi

echo "Test: Running shellcheck on $TEST_SCRIPT..."
if shellcheck "$TEST_SCRIPT"; then
    echo "PASS: shellcheck found no issues."
else
    echo "FAIL: shellcheck found issues."
    exit 1
fi

echo "All tests passed."
exit 0
