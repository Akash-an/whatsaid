#!/usr/bin/env bash

BACKEND_PORT=8000
FRONTEND_PORT=5173

echo "Cleaning up previous server instances..."

kill_port() {
  local port=$1
  local pids=$(lsof -ti tcp:$port || true)
  if [ -n "$pids" ]; then
    echo "Killing processes on port $port: $(echo $pids | tr '\n' ' ')"
    kill -9 $pids 2>/dev/null || true
  fi
}

kill_port $BACKEND_PORT
kill_port $FRONTEND_PORT

echo "Starting backend server on port $BACKEND_PORT..."
if [ -f ".venv/bin/activate" ]; then
  source .venv/bin/activate
fi

# Run the API in the background
whatsaid-api &
BACKEND_PID=$!

echo "Starting frontend server on port $FRONTEND_PORT..."
cd ui
npm run dev &
FRONTEND_PID=$!

echo ""
echo "🚀 Both servers are running!"
echo "   Backend API: http://localhost:$BACKEND_PORT"
echo "   Frontend UI: http://localhost:$FRONTEND_PORT"
echo "   Press Ctrl+C to stop both servers."
echo ""

# Handle termination to clean up child processes
cleanup() {
    echo ""
    echo "Shutting down servers..."
    kill $BACKEND_PID $FRONTEND_PID 2>/dev/null || true
    exit 0
}

trap cleanup SIGINT SIGTERM

# Wait for background jobs
wait $BACKEND_PID $FRONTEND_PID
