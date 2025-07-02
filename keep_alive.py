import threading
import time
import requests
from flask import Flask, jsonify
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

@app.route('/')
def home():
    """Health check endpoint"""
    return jsonify({
        "status": "alive",
        "message": "YouTube Downloader Bot is running!",
        "timestamp": time.time()
    })

@app.route('/health')
def health():
    """Detailed health check"""
    return jsonify({
        "status": "healthy",
        "uptime": time.time(),
        "service": "YouTube Downloader Bot",
        "version": "1.0.0"
    })

@app.route('/ping')
def ping():
    """Simple ping endpoint"""
    return "pong"

def run_flask():
    """Run Flask server in a separate thread"""
    try:
        app.run(host='0.0.0.0', port=8080, debug=False, use_reloader=False)
    except Exception as e:
        logger.error(f"Flask server error: {e}")

def keep_alive():
    """Start the keep-alive web server"""
    logger.info("Starting keep-alive server on port 8080...")
    
    # Start Flask server in a daemon thread
    server_thread = threading.Thread(target=run_flask, daemon=True)
    server_thread.start()
    
    logger.info("Keep-alive server started successfully!")
    return server_thread

def self_ping(url="http://localhost:8080", interval=300):
    """
    Ping the server periodically to keep it alive
    Args:
        url: The URL to ping
        interval: Ping interval in seconds (default: 5 minutes)
    """
    def ping_server():
        while True:
            try:
                time.sleep(interval)
                response = requests.get(url, timeout=10)
                if response.status_code == 200:
                    logger.info(f"Self-ping successful: {response.status_code}")
                else:
                    logger.warning(f"Self-ping returned: {response.status_code}")
            except requests.exceptions.RequestException as e:
                logger.error(f"Self-ping failed: {e}")
            except Exception as e:
                logger.error(f"Unexpected error in self-ping: {e}")
    
    # Start self-ping in a daemon thread
    ping_thread = threading.Thread(target=ping_server, daemon=True)
    ping_thread.start()
    logger.info(f"Self-ping started with {interval}s interval")
    return ping_thread

class KeepAliveManager:
    """Manager class for keep-alive functionality"""
    
    def __init__(self, port=8080, ping_interval=300):
        self.port = port
        self.ping_interval = ping_interval
        self.server_thread = None
        self.ping_thread = None
        self.is_running = False
    
    def start(self, enable_self_ping=True):
        """Start the keep-alive system"""
        try:
            logger.info("Initializing keep-alive system...")
            
            # Start Flask server
            self.server_thread = keep_alive()
            
            # Wait a moment for server to start
            time.sleep(2)
            
            # Start self-ping if enabled
            if enable_self_ping:
                self.ping_thread = self_ping(
                    url=f"http://localhost:{self.port}",
                    interval=self.ping_interval
                )
            
            self.is_running = True
            logger.info("Keep-alive system started successfully!")
            
        except Exception as e:
            logger.error(f"Failed to start keep-alive system: {e}")
            raise
    
    def stop(self):
        """Stop the keep-alive system"""
        self.is_running = False
        logger.info("Keep-alive system stopped")
    
    def status(self):
        """Get status of keep-alive system"""
        return {
            "running": self.is_running,
            "server_thread_alive": self.server_thread.is_alive() if self.server_thread else False,
            "ping_thread_alive": self.ping_thread.is_alive() if self.ping_thread else False,
            "port": self.port,
            "ping_interval": self.ping_interval
        }

# Global instance
keep_alive_manager = KeepAliveManager()

if __name__ == "__main__":
    # Test the keep-alive system
    print("Testing keep-alive system...")
    
    try:
        keep_alive_manager.start()
        
        # Keep the main thread alive for testing
        while True:
            time.sleep(30)
            status = keep_alive_manager.status()
            print(f"Keep-alive status: {status}")
            
    except KeyboardInterrupt:
        print("Stopping keep-alive system...")
        keep_alive_manager.stop()
    except Exception as e:
        print(f"Error: {e}"
