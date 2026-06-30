#!/usr/bin/env python3
"""Flask web application for subscription and Clash dashboard management."""

import json
import os
import sys
from pathlib import Path

# Add lib directory to Python path
sys.path.insert(0, str(Path(__file__).parent.parent / "lib"))

from flask import Flask, render_template, jsonify, request, Response
from config import load_config, ConfigError
from subscription import Subscription
from health import HealthCheck
import requests

app = Flask(__name__)

# Load configuration
try:
    config = load_config()
except ConfigError as e:
    print(f"Configuration error: {e}")
    sys.exit(1)

# Get paths from config
install_root = config.get('clash.install_root', '/opt/lab-remote-stack')
subscriptions_file = f"{install_root}/clash/subscriptions.json"
config_file = f"{install_root}/clash/config.yaml"

# Get project root for templates
project_root = Path(__file__).parent.parent
template_dir = str(project_root / "assets" / "clash" / "templates")

# Clash API endpoint
clash_api_host = config.get('web.bind', '127.0.0.1')
clash_api_port = config.get('clash.api_port', 9090)
clash_api_url = f"http://{clash_api_host}:{clash_api_port}"


@app.route('/')
def index():
    """Render main page."""
    return render_template('index.html')


@app.route('/api/subscriptions', methods=['GET'])
def get_subscriptions():
    """Get all subscriptions."""
    try:
        sub_manager = Subscription(subscriptions_file)
        subs = sub_manager.list()
        active = sub_manager.data.get('active')

        return jsonify({
            'success': True,
            'subscriptions': subs,
            'active': active
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/subscriptions', methods=['POST'])
def add_subscription():
    """Add a new subscription."""
    try:
        data = request.json
        name = data.get('name')
        url = data.get('url')
        template = data.get('template', 'balanced')

        if not name or not url:
            return jsonify({
                'success': False,
                'error': 'Name and URL are required'
            }), 400

        sub_manager = Subscription(subscriptions_file)
        sub = sub_manager.add(name, url, template)

        return jsonify({
            'success': True,
            'subscription': sub
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/subscriptions/<name>', methods=['DELETE'])
def remove_subscription(name):
    """Remove a subscription."""
    try:
        sub_manager = Subscription(subscriptions_file)
        sub_manager.remove(name)

        return jsonify({
            'success': True
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/subscriptions/<name>/activate', methods=['POST'])
def activate_subscription(name):
    """Activate a subscription."""
    try:
        sub_manager = Subscription(subscriptions_file)
        sub_manager.activate(name)

        return jsonify({
            'success': True
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/subscriptions/<name>/update', methods=['POST'])
def update_subscription(name):
    """Update a subscription."""
    try:
        sub_manager = Subscription(subscriptions_file)
        sub_type, node_count = sub_manager.update(name, template_dir, config_file)

        return jsonify({
            'success': True,
            'type': sub_type,
            'node_count': node_count
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/health', methods=['GET'])
def get_health():
    """Get system health status."""
    try:
        checker = HealthCheck(config)
        results = checker.run_all(check_connectivity=True)

        return jsonify({
            'success': True,
            'health': results
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/clash/<path:path>', methods=['GET', 'POST', 'PUT', 'DELETE', 'PATCH'])
def clash_proxy(path):
    """Proxy requests to Clash API."""
    try:
        url = f"{clash_api_url}/{path}"

        # Forward request
        if request.method == 'GET':
            resp = requests.get(url, params=request.args, timeout=10)
        elif request.method == 'POST':
            resp = requests.post(url, json=request.json, timeout=10)
        elif request.method == 'PUT':
            resp = requests.put(url, json=request.json, timeout=10)
        elif request.method == 'DELETE':
            resp = requests.delete(url, timeout=10)
        elif request.method == 'PATCH':
            resp = requests.patch(url, json=request.json, timeout=10)

        # Return response
        return Response(
            resp.content,
            status=resp.status_code,
            content_type=resp.headers.get('Content-Type', 'application/json')
        )
    except requests.exceptions.RequestException as e:
        return jsonify({
            'success': False,
            'error': f'Clash API error: {str(e)}'
        }), 503


@app.route('/api/config', methods=['GET'])
def get_config():
    """Get configuration."""
    try:
        return jsonify({
            'success': True,
            'config': {
                'clash_api_port': clash_api_port,
                'clash_http_port': config.get('clash.http_port', 7890),
                'clash_socks_port': config.get('clash.socks_port', 7891),
                'install_root': install_root
            }
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


if __name__ == '__main__':
    # Get host and port from config
    host = config.get('web.bind', '127.0.0.1')
    port = config.get('web.port', 5000)

    print(f"Starting web interface on http://{host}:{port}")
    app.run(host=host, port=port, debug=False)
